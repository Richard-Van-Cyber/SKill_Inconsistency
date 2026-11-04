#!/usr/bin/env python3
"""Diagnose the comprehension-stage JSON failures.

Runs round 1 + round 2 of the comprehension agent against one task's skill dir and
prints the raw response length, finish_reason and the exact JSON parse error.

Usage:
    python3 analysis_tools/diag_comprehension.py <task> [--round2-only]
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIT = os.path.join(WS, "skill-audit")
sys.path.insert(0, AUDIT)

import openai  # noqa: E402
from core.config import load_config  # noqa: E402
from comprehension.scanner import scan, validate_skill_root  # noqa: E402
from comprehension.comprehension_agent import (  # noqa: E402
    SYSTEM_PROMPT, _format_file_contents, _format_file_listing, _load_file_contents,
    _load_prompt,
)


async def call(client, model, prompt, max_tokens, temperature=0.0):
    r = await client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    ch = r.choices[0]
    return (ch.message.content or ""), ch.finish_reason, r.usage


def try_parse(raw):
    """mirror _extract_json but report *why* it failed"""
    import re
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text), "ok"
    except json.JSONDecodeError as e:
        first = str(e)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        try:
            return json.loads(text[start:end + 1]), "ok(braces)"
        except json.JSONDecodeError as e:
            first += " | braces: " + str(e)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    try:
        return json.loads(cleaned), "ok(cleaned)"
    except json.JSONDecodeError as e:
        first += " | cleaned: " + str(e)
    return None, first


async def main():
    task = sys.argv[1]
    cfg = load_config(os.path.join(AUDIT, "config.yaml"))
    skill_dir = validate_skill_root(os.path.join(WS, "tasks", task, "environment", "skills"))
    entries = scan(skill_dir, first_lines_count=cfg.comprehension.first_lines_count)
    print(f"task={task}  files={len(entries)}  model={cfg.llm.model} "
          f"max_tokens={cfg.llm.max_tokens}")

    client = openai.AsyncOpenAI(api_key=cfg.llm.api_key, base_url=cfg.llm.base_url)

    r1_prompt = _load_prompt("comprehension_round1.md").replace(
        "{file_listing}", _format_file_listing(entries))
    raw1, fr1, u1 = await call(client, cfg.llm.model, r1_prompt, cfg.llm.max_tokens)
    d1, why1 = try_parse(raw1)
    print(f"\n--- round1: {len(raw1)} chars, finish_reason={fr1}, "
          f"out_tokens={u1.completion_tokens}, parse={why1[:160]}")
    if d1 is None:
        print(raw1[-600:])
        return
    files = [f["path"] for f in d1.get("files_to_read", [])]
    print(f"    files_to_read={len(files)}: {files[:12]}")

    contents = _load_file_contents(skill_dir, files, cfg.comprehension.max_file_size_kb)
    total = sum(len(v) for v in contents.values())
    r2_prompt = (_load_prompt("comprehension_round2.md")
                 .replace("{file_contents}", _format_file_contents(contents))
                 .replace("{round1_guesses}", json.dumps(d1.get("files_to_read", []),
                                                         ensure_ascii=False, indent=2)))
    print(f"    round2 prompt: {len(r2_prompt)} chars, file contents: {total} chars")

    raw2, fr2, u2 = await call(client, cfg.llm.model, r2_prompt, 16384)
    d2, why2 = try_parse(raw2)
    print(f"--- round2: {len(raw2)} chars, finish_reason={fr2}, "
          f"out_tokens={u2.completion_tokens}, parse={why2[:200]}")
    if d2 is None:
        print("    TAIL:", raw2[-800:])
    else:
        print(f"    components={len(d2.get('components') or [])} "
              f"sub_skills={len(d2.get('sub_skills') or [])}")


if __name__ == "__main__":
    asyncio.run(main())
