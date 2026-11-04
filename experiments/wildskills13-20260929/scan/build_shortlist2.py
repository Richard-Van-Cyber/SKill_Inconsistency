#!/usr/bin/env python3
"""Pick the triage shortlist for the wildskills25 batch (second shortlist).

Greedy coverage over the L1/L2 taxonomy (rarest type first), then by W0 score, excluding the
13 skills the existing 12 tasks were already built from. Writes shortlist.csv with, per
candidate: the audit directory, the local skill tree, the eligible findings, and a compact
finding digest for the feasibility triage.

Usage: python3 build_shortlist.py [--max 26]
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path('/workspace/skillEvaluation')
SCAN = REPO / 'experiments' / 'wildskills13-20260929' / 'scan'
AUDIT = REPO / 'paper_audit_reports' / 'wildskills_audit'
ROOTS = [REPO / 'wildskills' / 'scripts_skills', REPO / 'wildskills' / 'skills']

USED0 = {
    'apache-shardingsphere-codex-skills-review-pr-skill-md',
    'awslabs-agentcore-samples-06-workshops-01-agentcore-runtime-10-managed-session-storage-persistent-notes-skill-md',
    'clickhouse-clickhouse-claude-skills-keeper-stress-analysis-skill-md',
    'digoal-blog-skills-digoal-skill-md',
    'eigent-ai-eigent-resources-example-skills-skill-security-auditor-skill-md',
    'eosphoros-ai-db-gpt-skills-csv-data-analysis-skill-md',
    'eosphoros-ai-db-gpt-skills-financial-report-analyzer-skill-md',
    'sickn33-antigravity-awesome-skills-skills-agent-orchestrator-skill-md',
    'spring-ai-alibaba-examples-claude-skills-http-generate-skill-md',
    'spring-ai-alibaba-examples-claude-skills-readme-generate-skill-md',
    'zenstory-ai-drama-skills-skills-short-drama-assets-skill-md',
    'zenstory-ai-drama-skills-skills-short-drama-edit-skill-md',
    'zenstory-ai-drama-skills-skills-short-drama-image-prompts-skill-md',
}


# --- wildskills13 already consumed these skills (tasks.json + packaged skill dir names) -----
_T13 = REPO / 'experiments' / 'wildskills13-20260929' / 'tasks.json'
USED = set(USED0)
if _T13.is_file():
    for t in json.load(open(_T13))['tasks']:
        if t.get('skill'):
            USED.add(Path(t['skill']).name)
        if t.get('local_dir'):
            USED.add(Path(t['local_dir']).name)
        sk = REPO / 'wildskills' / 'dynamic_eval' / 'tasks' / t['task'] / 'environment' / 'skills'
        if sk.is_dir():
            USED.update(p.name for p in sk.iterdir() if p.is_dir())


def local_dir(name: str) -> Path | None:
    for r in ROOTS:
        p = r / name
        if p.is_dir():
            return p
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--max', type=int, default=64)
    args = ap.parse_args()

    skills = {r['skill']: r for r in csv.DictReader(open(SCAN / 'skills.csv'))}
    findings = defaultdict(list)
    audit_dir = {}
    for rep in AUDIT.glob('*/audit_report.json'):
        d = json.load(open(rep))
        name = Path((d.get('meta') or {}).get('skill_dir', '')).name
        audit_dir[name] = rep.parent.name
    # reuse the canonical stage-1 rule computed by scan_candidates.py
    for f in csv.DictReader(open(SCAN / 'findings.csv')):
        if f['stage1_eligible'] == 'True':
            findings[f['skill']].append(f)

    cands = []
    for name, fs in findings.items():
        r = skills.get(name)
        if not r or name in USED or r['has_local_dir'] != 'True' or int(r['code_files']) == 0:
            continue
        types = sorted({f"{f['l1']}/{f['l2']}" for f in fs})
        cands.append({'skill': name, 'audit_dir': audit_dir.get(name, ''),
                      'local_dir': str(local_dir(name)), 'score': int(r['score']),
                      'code_files': int(r['code_files']), 'n_eligible': len(fs),
                      'types': types, 'findings': fs})

    # greedy: rarest type first, always take the highest-score candidate that carries it
    chosen, seen = [], set()
    type_pool = defaultdict(list)
    for c in cands:
        for t in c['types']:
            type_pool[t].append(c)
    for t in sorted(type_pool, key=lambda t: len(type_pool[t])):
        pool = [c for c in type_pool[t] if c['skill'] not in seen]
        if not pool:
            continue
        pool.sort(key=lambda c: (-c['score'], -c['n_eligible']))
        c = pool[0]
        chosen.append(c)
        seen.add(c['skill'])
        if len(chosen) >= args.max:
            break
    for c in sorted(cands, key=lambda c: (-c['score'], -c['n_eligible'])):
        if len(chosen) >= args.max:
            break
        if c['skill'] not in seen:
            chosen.append(c)
            seen.add(c['skill'])

    rows = []
    for c in chosen:
        digest = []
        for f in c['findings']:
            digest.append(
                f"{f['finding_id']} [{f['l1']}/{f['l2']}] sev={f['severity']} impact={f['impact_class']} "
                f"A={f['file_a']}:{f['span_a']} B={f['file_b']}:{f['span_b']} :: {f['impact_note'][:180]}")
        rows.append({'skill': c['skill'], 'score': c['score'], 'code_files': c['code_files'],
                     'n_eligible': c['n_eligible'], 'types': ';'.join(c['types']),
                     'audit_dir': c['audit_dir'], 'local_dir': c['local_dir'],
                     'eligible_digest': ' || '.join(digest)})
    with open(SCAN / 'shortlist2.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    cov = Counter(t for c in chosen for t in c['types'])
    print(f'shortlist2: {len(rows)} candidates, excluded {len(USED)} used skills')
    print(f'  candidate pool after exclusions: {len(cands)}')
    for t, n in sorted(cov.items(), key=lambda kv: kv[1]):
        print(f'  {n:>2}  {t}')
    all_types = {t for c in cands for t in c['types']}
    print('types in candidate pool but not covered:',
          sorted(all_types - set(cov)) or 'none')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
