from __future__ import annotations

import os
from pathlib import Path
from models.skill_map import FileEntry

IGNORE_PATTERNS = {
    ".git", "__pycache__", ".DS_Store", "node_modules", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".venv", "venv", "dist", "build",
}
IGNORE_EXTENSIONS = {".pyc", ".pyo", ".pyd", ".so", ".egg-info"}


class SkillRootError(RuntimeError):
    """Raised when the audit target is not a usable skill directory.

    Without this, a mistyped path produced "0 findings" and exited 0 — a clean
    audit report for a directory that does not exist, which is the most
    dangerous possible failure for a tool that drives repair decisions.
    """


def validate_skill_root(skill_root: str, require_skill_md: bool = True) -> str:
    path = os.path.abspath(os.path.expanduser(skill_root))
    if not os.path.exists(path):
        raise SkillRootError(f"skill directory does not exist: {path}")
    if not os.path.isdir(path):
        raise SkillRootError(f"skill path is not a directory: {path}")
    if require_skill_md:
        found = [p for p in Path(path).rglob("SKILL.md")]
        if not found:
            raise SkillRootError(
                f"no SKILL.md found under {path} — is this really a skill directory?")
    return path


def scan(skill_root: str, first_lines_count: int = 3) -> list[FileEntry]:
    """
    Recursively scan skill_root, collecting lightweight metadata per file.
    Returns FileEntry list sorted by path for deterministic ordering.
    Raises SkillRootError when the target is missing or empty.
    """
    entries: list[FileEntry] = []
    skill_root = validate_skill_root(skill_root)

    for dirpath, dirnames, filenames in os.walk(skill_root):
        # Prune ignored directories in-place so os.walk skips them
        dirnames[:] = [d for d in dirnames if d not in IGNORE_PATTERNS]

        for filename in filenames:
            _, ext = os.path.splitext(filename)
            if ext in IGNORE_EXTENSIONS or filename in IGNORE_PATTERNS:
                continue

            abs_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(abs_path, skill_root)
            size_bytes = os.path.getsize(abs_path)

            first_lines = _read_first_lines(abs_path, first_lines_count)

            entries.append(FileEntry(
                path=rel_path,
                extension=ext,
                size_bytes=size_bytes,
                first_lines=first_lines,
            ))

    entries.sort(key=lambda e: e.path)
    if not entries:
        raise SkillRootError(f"skill directory contains no auditable files: {skill_root}")
    return entries


def _read_first_lines(path: str, n: int) -> str:
    """Read first n lines of a file, silently returning empty string on any error."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = []
            for _ in range(n):
                line = f.readline()
                if not line:
                    break
                lines.append(line.rstrip())
        return "\n".join(lines)
    except Exception:
        return ""
