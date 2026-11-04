from __future__ import annotations

import json
import os

from core.config import ComprehensionConfig
from llm_client.base_client import BaseLLMClient
from models.skill_map import Component, FileEntry, SkillMap, SubSkillRelation


SYSTEM_PROMPT = "你是一位专注于 AI Skill 架构的精确技术分析师。始终只输出合法的 JSON。reason、description、comprehension_notes 字段使用中文；文件路径和代码片段保留原始内容。JSON 字符串中不得包含未转义的引号或换行符。"


def _load_prompt(name: str) -> str:
    prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", name)
    with open(os.path.normpath(prompt_path), "r", encoding="utf-8") as f:
        return f.read()


def _format_file_listing(entries: list[FileEntry]) -> str:
    lines = []
    for e in entries:
        lines.append(f"- {e.path} ({e.extension}, {e.size_bytes} bytes)")
        if e.first_lines:
            for line in e.first_lines.splitlines():
                lines.append(f"    {line}")
    return "\n".join(lines)


def _load_file_contents(skill_root: str, paths: list[str], max_kb: int) -> dict[str, str]:
    """Load full content of specified files, truncating files above max_kb."""
    contents: dict[str, str] = {}
    max_bytes = max_kb * 1024
    for rel_path in paths:
        abs_path = os.path.join(skill_root, rel_path)
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read(max_bytes + 1)
            if len(text) > max_bytes:
                text = text[:max_bytes] + f"\n... [truncated at {max_kb}KB]"
            contents[rel_path] = text
        except Exception as e:
            contents[rel_path] = f"[ERROR reading file: {e}]"
    return contents


def _format_file_contents(contents: dict[str, str]) -> str:
    parts = []
    for path, text in contents.items():
        parts.append(f"=== {path} ===\n{text}\n")
    return "\n".join(parts)


def _extract_json(raw: str) -> dict | None:
    """Extract JSON from an LLM response, stripping markdown code fences if present.

    Returns ``None`` when nothing parseable is found. It previously returned an
    empty skeleton (``{"components": [], ...}``), which turned a transient
    provider hiccup into a report that read "0 findings — this skill is clean",
    and that skeleton was then written to the comprehension cache. 29 of the 87
    reports in the 2026-09-23 batch died exactly that way. Failures must stay
    visible instead (see ``_complete_json_with_retry``).
    """
    import re
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


class ComprehensionError(RuntimeError):
    """The comprehension stage could not produce a trustworthy SkillMap."""


REPAIR_INSTRUCTION = (
    "Your previous reply was not valid JSON and could not be parsed. "
    "Re-send the SAME answer, but emit only a single well-formed JSON object: "
    "no markdown fence, no commentary before or after, and every newline inside a "
    "string escaped as \\n. Escape any double quote that appears inside a string."
)


def validate_skill_map(skill_map: "SkillMap") -> None:
    """A map that read files but produced no components is a failed comprehension.

    This is exactly the shape the old silent fallback produced, so it is treated
    as an error rather than as "a skill with nothing in it".
    """
    if skill_map.files_read and not skill_map.components:
        raise ComprehensionError(
            f"comprehension read {len(skill_map.files_read)} file(s) but produced "
            f"0 components for {skill_map.skill_root}; refusing to report this as a clean audit"
        )


async def _complete_json_with_retry(client, prompt: str, system: str, temperature: float = 0.0,
                                    attempts: int = 3, base_delay: float = 2.0,
                                    max_tokens: int | None = None) -> dict:
    """Call the model and parse JSON, re-asking when the reply is unparseable.

    Network-level retries live in ``_complete_with_retry``; this adds a repair
    turn for the case where the provider answered 200 with malformed JSON.
    """
    import asyncio
    last_raw = ""
    last_err: str = "empty response"
    for i in range(attempts):
        ask = prompt if i == 0 else f"{prompt}\n\n{REPAIR_INSTRUCTION}"
        raw = await _complete_with_retry(client, ask, system, temperature,
                                         max_tokens=max_tokens)
        data = _extract_json(raw)
        if isinstance(data, dict):
            return data
        last_raw = raw
        last_err = "response was not a JSON object"
        if i < attempts - 1:
            await asyncio.sleep(base_delay * (2 ** i))
    raise ComprehensionError(
        f"model returned unparseable JSON after {attempts} attempts ({last_err}); "
        f"last response was {len(last_raw)} chars and ended with: {last_raw[-200:]!r}"
    )


async def _complete_with_retry(client, prompt: str, system: str, temperature: float = 0.0,
                             attempts: int = 3, base_delay: float = 2.0, max_tokens: int | None = None) -> str:
    """Retry transient LLM failures with backoff.

    A single connection reset used to abort the whole audit with a raw
    traceback after one wasted call.
    """
    import asyncio
    last: Exception | None = None
    for i in range(attempts):
        try:
            return await client.complete(prompt, system=system, temperature=temperature,
                                         max_tokens=max_tokens)
        except Exception as exc:          # noqa: BLE001 - provider errors vary
            last = exc
            if i == attempts - 1:
                break
            await asyncio.sleep(base_delay * (2 ** i))
    raise RuntimeError(f"comprehension LLM call failed after {attempts} attempts: {last}")


def skill_cache_key(skill_root: str, exclude: list[str] | None = None) -> str:
    """Stable content hash of the audited directory (path excluded).

    Only auditable files count, and anything the tool itself writes must be
    excluded. Two earlier versions were unusable:
      * hashing every file included ``__pycache__/*.pyc``, which Python rewrites
        between runs, so the key changed every time;
      * writing the report into the audited directory changed the key as well.
    Both made the cache miss on every second run.
    """
    import hashlib
    import os as _os
    from comprehension.scanner import scan as _scan

    # realpath (not abspath): on macOS /var is a symlink to /private/var,
    # so a path given by Path.resolve() would never match abspath().
    excluded = {_os.path.realpath(p) for p in (exclude or [])}
    digest = hashlib.blake2b(digest_size=8)
    for entry in _scan(skill_root):
        abs_path = _os.path.realpath(_os.path.join(skill_root, entry.path))
        # A directory exclusion must cover its whole subtree: the cache lives in
        # a directory, so its files are what actually appear here.
        if abs_path in excluded or any(
            abs_path.startswith(d + _os.sep) for d in excluded
        ):
            continue
        digest.update(entry.path.encode())
        digest.update(b"\0")
        try:
            with open(abs_path, "rb") as fh:
                digest.update(fh.read())
        except OSError:
            digest.update(b"<unreadable>")
        digest.update(b"\0")
    return digest.hexdigest()


def skill_map_to_cache(skill_map: SkillMap) -> dict:
    return {
        "skill_root": skill_map.skill_root,
        "all_files": [f.__dict__ for f in skill_map.all_files],
        "files_read": skill_map.files_read,
        "components": [
            {**c.__dict__, "source_span": list(c.source_span) if c.source_span else None}
            for c in skill_map.components
        ],
        "sub_skills": skill_map.sub_skills,
        "sub_skill_relations": [r.__dict__ for r in skill_map.sub_skill_relations],
        "comprehension_notes": skill_map.comprehension_notes,
    }


def skill_map_from_cache(data: dict) -> SkillMap:
    return SkillMap(
        skill_root=data["skill_root"],
        all_files=[FileEntry(**f) for f in data["all_files"]],
        files_read=data["files_read"],
        components=[
            Component(
                component_id=c["component_id"],
                component_type=c["component_type"],
                source_file=c["source_file"],
                source_span=tuple(c["source_span"]) if c.get("source_span") else None,
                content=c["content"],
                linked_components=c.get("linked_components", []),
            )
            for c in data["components"]
        ],
        sub_skills=data["sub_skills"],
        sub_skill_relations=[SubSkillRelation(**r) for r in data["sub_skill_relations"]],
        comprehension_notes=data["comprehension_notes"],
    )


async def run_comprehension(
    skill_root: str,
    entries: list[FileEntry],
    client: BaseLLMClient,
    cfg: ComprehensionConfig,
) -> SkillMap:
    # ── Round 1: decide which files to read ──────────────────────────────────
    round1_template = _load_prompt("comprehension_round1.md")
    file_listing = _format_file_listing(entries)
    round1_prompt = round1_template.replace("{file_listing}", file_listing)

    round1_data = await _complete_json_with_retry(
        client, round1_prompt, SYSTEM_PROMPT, 0.0)
    files_to_read_entries: list[dict] = round1_data.get("files_to_read") or []
    files_to_read: list[str] = [f["path"] for f in files_to_read_entries if isinstance(f, dict) and f.get("path")]

    # ── Load file contents ────────────────────────────────────────────────────
    file_contents = _load_file_contents(skill_root, files_to_read, cfg.max_file_size_kb)
    formatted_contents = _format_file_contents(file_contents)
    round1_guesses = json.dumps(files_to_read_entries, ensure_ascii=False, indent=2)

    # ── Round 2: build SkillMap ───────────────────────────────────────────────
    round2_template = _load_prompt("comprehension_round2.md")
    round2_prompt = (
        round2_template
        .replace("{file_contents}", formatted_contents)
        .replace("{round1_guesses}", round1_guesses)
    )

    round2_data = await _complete_json_with_retry(
        client, round2_prompt, SYSTEM_PROMPT, 0.0, max_tokens=16384)

    # ── Build SkillMap from LLM output ────────────────────────────────────────
    components: list[Component] = []
    for c in round2_data.get("components") or []:
        source_file = c.get("source_file")
        if not source_file:
            continue
        span = c.get("source_span")
        components.append(Component(
            component_id=c.get("component_id") or f"c{len(components) + 1}",
            component_type=c.get("component_type") or "unknown",
            source_file=source_file,
            source_span=tuple(span) if span else None,
            content=file_contents.get(source_file, c.get("content_summary", "")),
            linked_components=c.get("linked_components", []),
        ))

    relations: list[SubSkillRelation] = []
    for r in round2_data.get("sub_skill_relations") or []:
        if not all(r.get(k) for k in ("from_skill", "to_skill", "relation_type")):
            continue
        relations.append(SubSkillRelation(
            from_skill=r["from_skill"],
            to_skill=r["to_skill"],
            relation_type=r["relation_type"],
            description=r.get("description", ""),
        ))

    skill_map = SkillMap(
        skill_root=os.path.abspath(skill_root),
        all_files=entries,
        files_read=files_to_read,
        components=components,
        sub_skills=round2_data.get("sub_skills") or [],
        sub_skill_relations=relations,
        comprehension_notes=round2_data.get("comprehension_notes", ""),
    )
    # A map that read files but produced nothing is a failed comprehension, not
    # a clean skill. Raise so the caller can fail loudly instead of caching it.
    validate_skill_map(skill_map)
    return skill_map
