"""Heuristic SkillMap construction — no LLM required.

Why this exists: every deterministic checker (schema_comparator,
env_constraint_checker, url_validator) consumes `SkillMap.components`, and those
components are produced by the LLM comprehension phase. When comprehension
returns nothing (or the model is unavailable), the hard checkers silently do
nothing — which is exactly what happened across the first ten audited skills:
`url_validator` was the only hard checker that ever fired, because it was the
only one that re-scanned raw file text instead of relying on components.

This module builds a conservative SkillMap from the files on disk:

    *.md / *.txt            -> description        (whole file)
    *.py / *.js / *.sh      -> implementation     (whole file)

Parameter schemas are *not* guessed here; `schema_comparator` already knows how
to extract a table from a description body when the block is marked. Instead we
emit `parameter_schema` components for fenced blocks that look like a parameter
table, so the comparator has something real to compare.

The result is deliberately coarse. It is a fallback for `--dry-run`, for
regression tests, and for the case where the LLM phase fails; the LLM
comprehension remains the primary path.
"""
from __future__ import annotations

import json
import os
import re

from comprehension.scanner import scan
from models.skill_map import Component, FileEntry, SkillMap

_DOC_EXT = {".md", ".markdown", ".txt", ".rst"}
_CODE_EXT = {".py", ".js", ".mjs", ".ts", ".sh", ".bash", ".java", ".erl"}
_SKILL_NAME_RE = re.compile(r"^#\s*(.+)$", re.M)
_TABLE_ROW_RE = re.compile(r"^\|.*\|$")


def _sub_skill_names(entries: list[FileEntry]) -> list[str]:
    """Top-level directories that contain a SKILL.md."""
    names = []
    for e in entries:
        parts = e.path.split(os.sep)
        if len(parts) >= 2 and parts[-1] == "SKILL.md":
            names.append(parts[0])
    return sorted(set(names))


def _param_table_components(rel_path: str, text: str) -> list[Component]:
    """Emit a parameter_schema component for each table that has a name column.

    The comparator looks for a header containing `name`/`param`/`flag`; a table
    with only `| option | description |` is treated as a name column too, since
    that is how most usage blocks are written.
    """
    out: list[Component] = []
    lines = text.splitlines()
    start = None
    for i, raw in enumerate(lines + [""]):
        is_row = bool(_TABLE_ROW_RE.match(raw.strip()))
        if is_row and start is None:
            start = i
        elif not is_row and start is not None:
            block = lines[start:i]
            header = [c.strip().strip("`*").lower() for c in block[0].strip("|").split("|")]
            if any(h in ("name", "param", "parameter", "flag", "option", "参数", "选项") for h in header):
                out.append(Component(
                    component_id=f"AUTO-SCHEMA-{rel_path}-{start}",
                    component_type="parameter_schema",
                    source_file=rel_path,
                    source_span=(start + 1, i),
                    content="\n".join(block),
                ))
            start = None
    return out


def build_heuristic_map(skill_dir: str, first_lines_count: int = 3) -> SkillMap:
    entries = scan(skill_dir, first_lines_count=first_lines_count)
    components: list[Component] = []
    files_read: list[str] = []

    for entry in entries:
        ext = entry.extension.lower()
        try:
            with open(os.path.join(skill_dir, entry.path), "r", encoding="utf-8",
                      errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        files_read.append(entry.path)

        if ext in _DOC_EXT:
            components.append(Component(
                component_id=f"AUTO-DOC-{entry.path}",
                component_type="description",
                source_file=entry.path,
                source_span=(1, len(text.splitlines()) or 1),
                content=text,
            ))
            components.extend(_param_table_components(entry.path, text))
        elif ext in _CODE_EXT:
            components.append(Component(
                component_id=f"AUTO-IMPL-{entry.path}",
                component_type="implementation",
                source_file=entry.path,
                source_span=(1, len(text.splitlines()) or 1),
                content=text,
            ))

    return SkillMap(
        skill_root=os.path.abspath(skill_dir),
        all_files=entries,
        files_read=files_read,
        components=components,
        sub_skills=_sub_skill_names(entries),
        sub_skill_relations=[],
        comprehension_notes=(
            f"heuristic map: {len(components)} components from {len(entries)} files "
            f"(no LLM comprehension)"
        ),
    )


def to_json(skill_map: SkillMap) -> dict:
    return {
        "skill_root": skill_map.skill_root,
        "components": [c.__dict__ for c in skill_map.components],
        "sub_skills": skill_map.sub_skills,
        "notes": skill_map.comprehension_notes,
    }


if __name__ == "__main__":
    import sys
    print(json.dumps(to_json(build_heuristic_map(sys.argv[1])), ensure_ascii=False, indent=2)[:2000])
