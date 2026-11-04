#!/usr/bin/env python3
"""W0 scan -- pick 13 wildskills candidates that cover the inconsistency taxonomy.

Input : paper_audit_reports/wildskills_audit/*/audit_report.json   (488 audited GitHub skills)
        wildskills/skills/<skill_dir>/                            (the actual skill trees)

A finding is stage-1 eligible when it is hard enough to build a dynamic task around:
  * validation_status == confirmed
  * both evidence sides carry file + line span
  * at least one evidence side is an executable artifact (not prose), i.e. the defect is
    behavioural and can be measured by *running* something in the container

Outputs (experiments/wildskills13-20260929/scan/):
  findings.csv       one row per eligible finding
  skills.csv         one row per skill (ranked)
  W0-SUMMARY.md      type coverage + shortlist

Usage: python3 scan_candidates.py
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path('/workspace/skillEvaluation')
AUDIT = REPO / 'paper_audit_reports' / 'wildskills_audit'
SKILL_ROOTS = [REPO / 'wildskills' / 'scripts_skills', REPO / 'wildskills' / 'skills']
OUT = REPO / 'experiments' / 'wildskills13-20260929' / 'scan'


def resolve_local(name: str) -> Path | None:
    for root in SKILL_ROOTS:
        p = root / name
        if p.is_dir():
            return p
    return None

CODE_EXT = {'.py', '.sh', '.bash', '.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx', '.go', '.rs',
            '.java', '.kt', '.rb', '.php', '.c', '.cc', '.cpp', '.h', '.cs', '.swift', '.sql',
            '.r', '.jl', '.pl', '.lua', '.ex', '.exs', '.scala', '.clj'}
CFG_EXT = {'.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf', '.env', '.xml', '.lock'}
PROSE_EXT = {'.md', '.markdown', '.txt', '.rst', '.adoc'}

SEV_W = {'critical': 4, 'high': 3, 'medium': 2, 'low': 1, None: 0}
IMPACT_W = {'blocking': 3, 'silent': 2, 'may_block_if': 1, None: 0}


def is_code(f: str | None) -> bool:
    return bool(f) and Path(f).suffix.lower() in CODE_EXT


def is_cfg(f: str | None) -> bool:
    return bool(f) and Path(f).suffix.lower() in CFG_EXT


def side(ev: dict, key: str) -> dict:
    s = (ev or {}).get(key) or {}
    return {'file': s.get('file'), 'start': s.get('line_start'), 'end': s.get('line_end'),
            'text': (s.get('span_text') or '')[:400]}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    finding_rows, skill_rows = [], []
    type_all = Counter()
    type_artifact = Counter()
    type_eligible = Counter()

    for rep in sorted(AUDIT.glob('*/audit_report.json')):
        d = json.load(open(rep))
        meta = d.get('meta', {})
        sm = d.get('skill_map_summary', {}) or {}
        skill_dir = meta.get('skill_dir') or ''
        skill_name = Path(skill_dir).name or rep.parent.name
        local = resolve_local(skill_name)
        files = list(local.rglob('*')) if local else []
        code_files = [f for f in files if f.is_file() and f.suffix.lower() in CODE_EXT]
        cfg_files = [f for f in files if f.is_file() and f.suffix.lower() in CFG_EXT]
        findings = d.get('findings') or []
        elig = []
        for f in findings:
            l1 = f.get('taxonomy_l1')
            l2 = f.get('taxonomy_l2')
            type_all[(l1, l2)] += 1
            if sm.get('total_files', 1) > 1 or code_files:
                type_artifact[(l1, l2)] += 1
            a, b = side(f.get('evidence') or {}, 'source_a'), side(f.get('evidence') or {}, 'source_b')
            imp = (f.get('agent_impact') or {})
            ok = (f.get('validation_status') == 'confirmed'
                  and a['file'] and b['file']
                  and (a['start'] is not None) and (b['start'] is not None))
            code_side = is_code(a['file']) or is_code(b['file'])
            cfg_side = is_cfg(a['file']) or is_cfg(b['file'])
            if ok and (code_side or cfg_side):
                elig.append(f)
                type_eligible[(l1, l2)] += 1
            finding_rows.append({
                'skill': skill_name, 'finding_id': f.get('id'), 'l1': l1, 'l2': l2,
                'l3': f.get('taxonomy_l3'), 'severity': f.get('severity'),
                'impact_class': imp.get('impact_class'),
                'blocks_execution': imp.get('blocks_execution'),
                'silent_error': imp.get('produces_silent_error'),
                'validation': f.get('validation_status'), 'checker': f.get('source_checker'),
                'code_side': code_side, 'cfg_side': cfg_side,
                'file_a': a['file'], 'span_a': f"{a['start']}-{a['end']}",
                'file_b': b['file'], 'span_b': f"{b['start']}-{b['end']}",
                'stage1_eligible': bool(ok and (code_side or cfg_side)),
                'impact_note': (imp.get('impact_description') or '')[:300],
                'rationale': (f.get('rationale') or '')[:300],
            })
        n_code = len(code_files)
        n_conf = sum(1 for f in findings if f.get('validation_status') == 'confirmed')
        score = sum(SEV_W.get(f.get('severity'), 0) + IMPACT_W.get((f.get('agent_impact') or {}).get('impact_class'), 0)
                    for f in elig)
        skill_rows.append({
            'skill': skill_name, 'has_local_dir': bool(local),
            'local_root': ('scripts_skills' if local and 'scripts_skills' in str(local) else ('skills' if local else '')),
            'total_files': sm.get('total_files'), 'files_read': sm.get('files_read'),
            'code_files': n_code, 'cfg_files': len(cfg_files),
            'n_findings': len(findings), 'n_confirmed': n_conf,
            'n_eligible': len(elig),
            'n_eligible_blocking': sum(1 for f in elig if ((f.get('agent_impact') or {}).get('impact_class')) == 'blocking'),
            'n_eligible_silent': sum(1 for f in elig if ((f.get('agent_impact') or {}).get('impact_class')) == 'silent'),
            'n_eligible_high': sum(1 for f in elig if f.get('severity') in ('critical', 'high')),
            'types': ';'.join(sorted({f"{f.get('taxonomy_l1')}/{f.get('taxonomy_l2')}" for f in elig})),
            'score': score,
            'example_files': ';'.join(sorted({str(x) for f in elig for x in
                                              (side(f.get('evidence') or {}, 'source_a')['file'],
                                               side(f.get('evidence') or {}, 'source_b')['file']) if is_code(x)})[:4]),
        })

    def dump(path, rows, fields):
        with open(path, 'w', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction='ignore')
            w.writeheader()
            w.writerows(rows)

    dump(OUT / 'findings.csv', finding_rows, list(finding_rows[0]))
    skill_rows.sort(key=lambda r: (-r['score'], -r['n_eligible'], r['skill']))
    dump(OUT / 'skills.csv', skill_rows, list(skill_rows[0]))

    # ---------------------------------------------------------------- summary
    L = []
    A = L.append
    A('# W0：13 个新 wildskills task 的候选扫描')
    A('')
    A(f'扫描 {len(skill_rows)} 个已审计 GitHub skill（`paper_audit_reports/wildskills_audit/`），'
      f'共 {len(finding_rows)} 条 finding。')
    A('')
    A('**stage-1 合格判据**（能被动态验证的必要条件）：`validation_status == confirmed`，'
      '两侧证据都有 file + 行号，且至少一侧是**可执行产物**（`.py/.sh/.js/...`）或配置文件'
      '（`.json/.yaml/...`）——即缺陷是行为性的，能在容器里"跑出来"。')
    A('')
    A('| 范围 | skill 数 | finding 数 |')
    A('|---|---|---|')
    A(f'| 全部已审计 | {len(skill_rows)} | {len(finding_rows)} |')
    A(f'| 带产物（total_files>1 或本地有代码文件） | {sum(1 for r in skill_rows if (r["total_files"] or 0) > 1 or r["code_files"])} '
      f'| {sum(1 for r in finding_rows if r["code_side"] or r["cfg_side"])} |')
    A(f'| **stage-1 合格** | {sum(1 for r in skill_rows if r["n_eligible"])} '
      f'| {sum(1 for r in finding_rows if r["stage1_eligible"])} |')
    A('')
    A('## 类型覆盖（L1/L2）')
    A('')
    A('| L1 | L2 | 全部 finding | 带产物 | **stage-1 合格** | 合格 skill 数 |')
    A('|---|---|---|---|---|---|')
    by_skill = defaultdict(set)
    for r in finding_rows:
        if r['stage1_eligible']:
            by_skill[(r['l1'], r['l2'])].add(r['skill'])
    for (l1, l2) in sorted(type_all, key=lambda k: (-type_eligible[k], str(k))):
        A(f'| {l1} | `{l2}` | {type_all[(l1, l2)]} | {type_artifact[(l1, l2)]} | '
          f'**{type_eligible[(l1, l2)]}** | {len(by_skill[(l1, l2)])} |')
    A('')
    A('## 候选排名（前 30，按 severity×impact 加权得分）')
    A('')
    A('| # | skill | 本地 | code 文件 | findings | 合格 | blocking | silent | high | 覆盖类型 | 得分 |')
    A('|---|---|---|---|---|---|---|---|---|---|---|')
    for i, r in enumerate(skill_rows[:30], 1):
        A(f'| {i} | `{r["skill"]}` | {"✓" if r["has_local_dir"] else "✗"} | {r["code_files"]} | '
          f'{r["n_findings"]} | {r["n_eligible"]} | {r["n_eligible_blocking"]} | '
          f'{r["n_eligible_silent"]} | {r["n_eligible_high"]} | {r["types"]} | {r["score"]} |')
    A('')
    (OUT / 'W0-SUMMARY.md').write_text('\n'.join(L) + '\n')
    print(f'wrote {OUT}/findings.csv ({len(finding_rows)}), skills.csv ({len(skill_rows)}), W0-SUMMARY.md')
    print(f'stage-1 eligible skills: {sum(1 for r in skill_rows if r["n_eligible"])}')
    print('eligible by type:', {f'{k[0]}/{k[1]}': v for k, v in type_eligible.most_common()})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
