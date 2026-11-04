"""URL reachability checking, restricted to URLs on an execution path.

A dead documentation link is not an execution blocker. Reporting one as such
flooded the report with high-severity noise and misdirected repair effort, so
this checker:
  * only probes URLs that a command actually calls, or that code passes to an
    HTTP call (docstring URLs are already excluded by code_parser);
  * never probes hosts that cannot meaningfully fail (localhost, reserved
    example domains, private addresses);
  * never marks a documentation URL as blocking execution.
"""
from __future__ import annotations

import asyncio
import ipaddress
import re
import urllib.parse
from typing import Optional

import httpx

from models.finding import AgentImpact, EvidenceSpan, Finding
from models.skill_map import SkillMap

_FINDING_COUNTER = 0
_URL_RE = re.compile(r'https?://[^\s\'"<>)(,\]]+')

# Hosts that can never represent a real reachability failure.
_SKIP_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "host.docker.internal"}
_SKIP_SUFFIXES = (".local", ".internal", ".test", ".invalid", ".example",
                  "example.com", "example.org", "example.net")
_SKIP_LITERAL_HOSTS = {"target.com", "auth.example.com", "your-domain.com",
                       "yourdomain.com", "domain.com", "server.example.com"}


def _next_id() -> str:
    global _FINDING_COUNTER
    _FINDING_COUNTER += 1
    return f"URL-{_FINDING_COUNTER:03d}"


def _is_example_host(url: str) -> Optional[str]:
    """Return a reason string when this host must not be probed, else None."""
    try:
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
    except ValueError:
        return "unparseable URL"
    if not host:
        return "no host"
    if host in _SKIP_HOSTS or host in _SKIP_LITERAL_HOSTS:
        return f"local/example host '{host}'"
    if host.endswith(_SKIP_SUFFIXES):
        return f"reserved example domain '{host}'"
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return f"non-routable address '{host}'"
    except ValueError:
        pass
    return None


async def _check_url(client: httpx.AsyncClient, url: str, timeout: float) -> tuple[str, Optional[int], Optional[str]]:
    """Returns (url, status_code_or_None, error_message_or_None)."""
    try:
        resp = await client.head(url, timeout=timeout, follow_redirects=True)
        return url, resp.status_code, None
    except httpx.TimeoutException:
        return url, None, "timeout"
    except httpx.ConnectError as e:
        return url, None, f"connect_error: {e}"
    except Exception as e:
        return url, None, f"error: {e}"


def _plan(skill_map: SkillMap, mode: str, code_urls: Optional[list[str]]):
    """Return (probed, skipped).

    probed maps url -> (source, how, executed_in_code). ``executed_in_code`` is
    the only thing that may justify claiming a reachability failure blocks a
    run; a URL that merely appears in a document or a shell example does not.
    """
    from hard_checkers.code_parser import classify_doc_urls

    candidates: dict[str, tuple[str, str, bool]] = {}
    for url in code_urls or []:
        candidates[url] = ("<code literal>", "passed to an HTTP call in code", True)

    for comp in skill_map.components:
        if comp.component_type not in ("description", "implementation"):
            continue
        runtime, reference = classify_doc_urls(comp.content)
        for url in runtime:
            candidates.setdefault(url, (comp.source_file, "command-line invocation", False))
        if mode == "strict":
            for url in reference:
                candidates.setdefault(url, (comp.source_file, "documentation reference", False))

    probed: dict[str, tuple[str, str, bool]] = {}
    skipped: dict[str, str] = {}
    for url, info in candidates.items():
        reason = _is_example_host(url)
        if reason:
            skipped[url] = reason
        else:
            probed[url] = info
    return probed, skipped


async def validate(
    skill_map: SkillMap,
    timeout_seconds: float = 5.0,
    max_concurrent: int = 10,
    mode: str = "lenient",
    code_urls: Optional[list[str]] = None,
) -> list[Finding]:
    """Check reachability only for URLs on an execution path.

    ``mode``:
      off     — do nothing
      lenient — (default) probe only URLs a command actually calls; dead
                documentation links are dropped, not reported
      strict  — additionally report dead documentation links, as low severity
                and never as an execution blocker

    ``code_urls`` comes from ``code_parser`` (AST literals, docstrings already
    removed) and is passed in by the pipeline to avoid re-parsing.
    """
    if mode == "off":
        return []

    probed, _skipped = _plan(skill_map, mode, code_urls)
    if not probed:
        return []

    semaphore = asyncio.Semaphore(max_concurrent)

    async def bounded_check(client: httpx.AsyncClient, url: str) -> tuple[str, Optional[int], Optional[str]]:
        async with semaphore:
            return await _check_url(client, url, timeout_seconds)

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[bounded_check(client, u) for u in probed])

    findings: list[Finding] = []
    for url, status, error in results:
        source, how, executed_in_code = probed[url]
        if error == "timeout":
            continue                       # unverified — do not report
        if error is None and (status is None or status < 400):
            continue
        reason = error if error else f"HTTP {status}"
        # Only a URL the code itself hands to an HTTP call can break a run.
        # Deriving this from the file suffix was wrong: code literals were
        # recorded with the component type as their source, so a genuinely
        # blocking URL came out as non-blocking.
        blocks = executed_in_code
        findings.append(Finding(
            id=_next_id(),
            taxonomy_l1="environmental",
            taxonomy_l2="external_resource_invalid",
            taxonomy_l3=None,
            severity="medium" if blocks else "low",
            agent_impact=AgentImpact(
                blocks_execution=blocks,
                produces_silent_error=False,
                impact_description=(
                    f"URL '{url}' ({how}) is unreachable ({reason}). "
                    + ("It is passed to an HTTP call in code, so that call fails at runtime."
                       if blocks else
                       "It appears in documentation only; nothing in the skill stops working.")
                ),
                impact_class="verified" if blocks else "cosmetic",
            ),
            evidence_a=EvidenceSpan(file=source, line_start=None, line_end=None, span_text=url),
            evidence_b=None,
            rationale=f"HTTP request to '{url}' returned: {reason}. Source: {how}.",
            validation_status="hard_rule",
            source_checker="url_validator",
            confidence="verified",
        ))

    return findings


def skipped_example_urls(skill_map: SkillMap, code_urls: Optional[list[str]] = None) -> list[tuple[str, str]]:
    """What was deliberately not probed, for the report's transparency section."""
    _probed, skipped = _plan(skill_map, "strict", code_urls)
    return sorted(skipped.items())
