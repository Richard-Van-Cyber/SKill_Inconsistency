from __future__ import annotations

import ast
from typing import Optional
from models.skill_map import SkillMap, Component
from models.preflight import CodeFacts


def _components_of_type(skill_map: SkillMap, component_type: str) -> list[Component]:
    return [c for c in skill_map.components if c.component_type == component_type]


def _parse_functions(tree: ast.Module, comp_file: str = "impl") -> list[dict]:
    functions = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        params = []
        args = node.args
        # Build list of (name, annotation, default, required)
        defaults_offset = len(args.args) - len(args.defaults)
        for i, arg in enumerate(args.args):
            if arg.arg == "self":
                continue
            annotation = ast.unparse(arg.annotation) if arg.annotation else None
            has_default = i >= defaults_offset
            default = ast.unparse(args.defaults[i - defaults_offset]) if has_default else None
            params.append({
                "name": arg.arg,
                "type": annotation,
                "default": default,
                "required": not has_default,
            })
        return_type = ast.unparse(node.returns) if node.returns else None
        decorators = [ast.unparse(d) for d in node.decorator_list]
        functions.append({
            "name": node.name,
            "params": params,
            "return_type": return_type,
            "decorators": decorators,
            "lineno": node.lineno,
            "source_file": comp_file,
        })
    return functions


def _parse_raises(tree: ast.Module) -> list[str]:
    raises = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and node.exc is not None:
            raises.append(ast.unparse(node.exc))
    return list(set(raises))


def _docstring_nodes(tree: ast.Module) -> set[int]:
    """ids() of Constant nodes that are docstrings (not real string values)."""
    out: set[int] = set()
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, holders):
            continue
        body = getattr(node, "body", None) or []
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            out.add(id(first.value))
    return out


def _parse_http_urls(tree: ast.Module) -> list[str]:
    """Extract HTTP URL string literals from the AST, excluding docstrings.

    Docstrings are Constants too, but a URL inside a docstring is prose, not a
    call. Mixing the two made every documentation link look like a runtime
    dependency (a dead wiki link in a comment was reported as "blocks
    execution"). Keeping only real string literals makes the distinction
    meaningful.
    """
    docstrings = _docstring_nodes(tree)
    urls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstrings:
                continue
            val = node.value
            if val.startswith("http://") or val.startswith("https://"):
                urls.append(val)
    return list(set(urls))



def _has_file_write(tree: ast.Module) -> bool:
    write_funcs = {"write", "writelines", "dump", "save"}
    open_write_modes = {"w", "wb", "a", "ab", "x", "xb"}
    for node in ast.walk(tree):
        # open(..., "w") or open(..., mode="w")
        if isinstance(node, ast.Call):
            func_name = ""
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                func_name = node.func.attr
            if func_name == "open":
                for arg in node.args[1:2]:
                    if isinstance(arg, ast.Constant) and arg.value in open_write_modes:
                        return True
                for kw in node.keywords:
                    if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                        if kw.value.value in open_write_modes:
                            return True
            if func_name in write_funcs:
                return True
    return False


def _has_global_mutation(tree: ast.Module) -> bool:
    """Detect module-level name assignments outside of functions/classes."""
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            return True
        if isinstance(node, ast.Global):
            return True
    # Also check for 'global' keyword inside functions
    for node in ast.walk(tree):
        if isinstance(node, ast.Global):
            return True
    return False


def _parse_imports(tree: ast.Module) -> list[str]:
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module.split(".")[0])
    return list(set(imports))


def _main_guard_calls(tree: ast.Module) -> list[str]:
    """Names called inside `if __name__ == "__main__":` — the real CLI entry.

    Name heuristics pick the wrong function often; this is evidence rather than
    a guess. Empty when the file has no such guard.
    """
    calls: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        test = node.test
        is_main = (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name)
            and test.left.id == "__name__"
            and any(
                isinstance(c, ast.Constant) and c.value == "__main__"
                for c in test.comparators
            )
        )
        if not is_main:
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                fn = sub.func
                if isinstance(fn, ast.Name):
                    calls.append(fn.id)
                elif isinstance(fn, ast.Attribute):
                    calls.append(fn.attr)
    return list(dict.fromkeys(calls))


def _guess_entry_function(functions: list[dict]) -> Optional[str]:
    """Best guess at the callable an agent would actually invoke.

    Restricted to functions that *take arguments*: a zero-parameter helper such
    as ``get_args()`` is never the entry point, and returning one made the
    schema comparison meaningless (every documented parameter looked
    over-promised). Returns None when nothing qualifies, so callers can report
    "not identified" instead of comparing against an arbitrary function.
    """
    callable_with_args = [f for f in functions if f["params"]]
    if not callable_with_args:
        return None
    priority = ["run", "execute", "main", "invoke", "call", "handle", "app", "parse"]
    names = {f["name"]: f for f in callable_with_args}
    for name in priority:
        if name in names:
            return name
    for f in callable_with_args:
        if not f["name"].startswith("_"):
            return f["name"]
    return callable_with_args[0]["name"]




_URL_RE = None


def classify_doc_urls(text: str, threshold: float = 0.5) -> tuple[list[str], list[str]]:
    """Split URLs in free text into (runtime_call_urls, reference_urls).

    A URL is a runtime call only when it sits on a line (or in a fenced command
    block) that actually invokes something with it — curl/wget/requests/open/
    http/ffmpeg/git clone and friends. A URL in prose or in an issue link is a
    reference: if it 404s, nothing in the skill stops working, so it must not be
    reported as an execution blocker.
    """
    import re
    url_re = re.compile(r"https?://[^\s'\"<>)(,\]]+")
    call_re = re.compile(
        r"\b(curl|wget|requests?\.|httpx\.|urllib|urlopen|http\.client|aiohttp|"
        r"git\s+clone|pip\s+install|npm\s+install|ffmpeg|magick|convert|fetch|download)\b",
        re.IGNORECASE,
    )
    runtime, reference = [], []
    for raw in text.splitlines():
        line = raw.strip()
        urls = [u.rstrip(".,;:)") for u in url_re.findall(line)]
        if not urls:
            continue
        # Ignore markdown quote/comment-only lines: they are prose.
        if line.startswith((">", "#", "//", "*", "- [")) and not call_re.search(line):
            reference.extend(urls)
            continue
        if call_re.search(line):
            runtime.extend(urls)
        else:
            reference.extend(urls)
    return list(dict.fromkeys(runtime)), list(dict.fromkeys(reference))


def parse(skill_map: SkillMap) -> CodeFacts:
    """
    Parse all implementation components in the skill_map using Python AST.
    Returns a unified CodeFacts aggregating across all impl components.
    """
    impl_components = _components_of_type(skill_map, "implementation")

    all_functions: list[dict] = []
    all_raises: list[str] = []
    all_http_urls: list[str] = []
    has_file_write = False
    has_global_mutation = False
    all_imports: list[str] = []
    entry_function: Optional[str] = None
    module_entry_calls: list[str] = []

    for comp in impl_components:
        try:
            tree = ast.parse(comp.content)
        except SyntaxError:
            # Non-parseable content — skip AST analysis for this component
            continue

        functions = _parse_functions(tree, comp.source_file)
        all_functions.extend(functions)
        all_raises.extend(_parse_raises(tree))
        all_http_urls.extend(_parse_http_urls(tree))
        if _has_file_write(tree):
            has_file_write = True
        if _has_global_mutation(tree):
            has_global_mutation = True
        all_imports.extend(_parse_imports(tree))
        module_entry_calls.extend(_main_guard_calls(tree))

        if entry_function is None and functions:
            entry_function = _guess_entry_function(functions)

    return CodeFacts(
        functions=all_functions,
        raises=list(set(all_raises)),
        http_urls=list(set(all_http_urls)),
        has_file_write=has_file_write,
        has_global_mutation=has_global_mutation,
        imports=list(set(all_imports)),
        entry_function=entry_function,
        module_entry_calls=list(dict.fromkeys(module_entry_calls)),
    )
