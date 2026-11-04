"""Evidence preservation and usage accounting for the frozen three-condition study."""
import hashlib
import json
import shlex
from pathlib import Path


def tree_hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file() and p.name != '.DS_Store'}


def audit_usage(out, result):
    keys = ['input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens', 'output_tokens']
    totals = dict.fromkeys(keys, 0)
    records = []
    log = out / 'api/requests.jsonl'
    for line in log.read_text().splitlines() if log.exists() else []:
        record = json.loads(line)
        if not record.get('generation'):
            continue
        records.append(record)
        p = out / ('api/response-' + record['id'] + '.txt')
        data = p.read_bytes()
        try:
            events = [json.loads(data)]
        except (ValueError, UnicodeDecodeError):
            events = []
            for line in data.splitlines():
                if line.startswith(b'data: '):
                    try: events.append(json.loads(line[6:]))
                    except ValueError: pass
        per_request = dict.fromkeys(keys, 0)
        for event in events:
            obj = event.get('message') or event.get('response') or event
            usage = obj.get('usage') or event.get('usage') or {}
            for key in keys:
                if key in usage:
                    per_request[key] = int(usage[key] or 0)
        for key in keys:
            totals[key] += per_request[key]
        record['token_breakdown'] = per_request
    result['api_usage'] = totals
    result['total_tokens'] = sum(totals.values())
    result['api_error_count'] = sum(bool(r.get('error')) or r.get('status') != 200 for r in records)
    result['api_request_seconds'] = round(sum(r.get('duration_seconds', 0) for r in records), 4)
    result['usage_source'] = 'response bodies, final reported value per field per request; all recorded attempts included'
    result['cost_basis'] = 'Claude Code reported list-price estimate; not third-party billed amount'
    (out / 'usage-audit.json').write_text(json.dumps({'totals': totals, 'requests': records}, indent=2) + '\n')


async def archive_artifacts(env, task, out):
    # Save outputs before verifier code or hardening can affect them. Full stopped containers also remain.
    roots = {
        'civ6-adjacency-optimizer': ['/output'],
        'court-form-filling': ['/root/sc100-filled.pdf'],
        'crystallographic-wyckoff-position-analysis': ['/root/workspace'],
        'data-to-d3': ['/root/output'],
        'dialogue-parser': ['/app/dialogue.json', '/app/dialogue.dot', '/app/solution.py'],
        'energy-market-pricing': ['/root/report.json'],
        'grid-dispatch-operator': ['/root/report.json'],
        'mario-coin-counting': ['/root/counting_results.csv'],
        'fix-druid-loophole-cve': ['/root/patches'],
        'fix-erlang-ssh-cve': ['/app/workspace/otp_src_27.3.2/lib/ssh/src', '/app/workspace/otp_src_27.3.2/lib/ssh/include'],
        # wildskills25 batch: deliverables live in /app/workspace
        'podcast-script-filename-collision': ['/app/workspace'],
        'recursive-scheduled-workflow-discovery': ['/app/workspace'],
        'quick-query-table-ref-substitution': ['/app/workspace'],
        'codebase-scan-discovery-metrics': ['/app/workspace'],
        'hook-decision-exit-code': ['/app/workspace'],
        'playwright-ci-inprogress-report': ['/app/workspace'],
        'crew-init-workspace-path': ['/app/workspace'],
        'crm-export-column-validation': ['/app/workspace'],
        'r2hf-lint-shadcn-blocker': ['/app/workspace'],
        'codemap-hidden-dir-omission': ['/app/workspace'],
        'nano-banana-config-api-key': ['/app/workspace'],
        'ask-echo-client': ['/app/workspace'],
        'drt-event-report': ['/app/workspace'],
        'kargo-release-notes': ['/app/workspace'],
        'gh-fetch-pagination': ['/app/workspace'],
        'image-gen-url-contract': ['/app/workspace'],
        'pdf-form-image-coord-flip': ['/app/workspace'],
        'lint-sync-candidate-discovery': ['/app/workspace'],
        'scheduled-task-arg-contract': ['/app/workspace'],
        'subtitle-download-evidence': ['/app/workspace'],
        'adk-deployable-flag-preexisting': ['/app/workspace'],
        'packs-resolve-exit-contract': ['/app/workspace'],
        'regen-dep-context-fork-runs': ['/app/workspace'],
        'understand-knowledge-manifest-headings': ['/app/workspace'],
        'data-analyzer-stats': ['/app/workspace'],
        'promql-lint-gate': ['/app/workspace'],
        'histogram-candidate-discovery': ['/app/workspace'],
        'kibana-connector-json-escape': ['/app/workspace'],
        # adversarial-trigger study (earthquake-adv-20260924): the task writes a
        # single JSON answer; -adv is the same package with a perturbed
        # plate-name column. Missing entries here raise KeyError[task] and turn
        # a perfectly good run into agent_error.
        'earthquake-plate-calculation': ['/root/answer.json'],
        'earthquake-plate-calculation-adv': ['/root/answer.json'],
        # grid Type-1 adversarial study: downsized DC-OPF instances
        'grid-dispatch-small': ['/root/report.json'],
        'grid-dispatch-small-type1': ['/root/report.json'],
        # pddl plan-path adversarial study: plans land in /app
        'pddl-tpp-txt': ['/app/problem.json', '/app/tpp'],
        'pddl-tpp-plan': ['/app/problem.json', '/app/tpp'],
        # UC alloc-semantics study: the task writes a single report
        'energy-unit-commitment': ['/root/report.json'],
        # pivot field-index study
        'sales-pivot-analysis': ['/root/demographic_analysis.xlsx'],
        # lab unit clamping study
        'lab-unit-harmonization': ['/root/ckd_lab_data_harmonized.csv'],
        # ACC anti-windup study
        'adaptive-cruise-control': ['/root/simulation_results.csv', '/root/tuning_results.yaml',
                                    '/root/pid_controller.py', '/root/acc_system.py',
                                    '/root/simulation.py', '/root/acc_report.md'],
        # offer-letter conditional-section study
        'offer-letter-generator': ['/root/offer_letter_filled.docx'],
        # --- wildskills dynamic-evaluation study --------------------------------
        # The deliverable is the generated request collection inside the module.
        'spring-http-requests': ['/app/spring-ai-alibaba-examples/basic/chat'],
        # The deliverable is the refreshed module README (and whatever backup was left).
        'spring-readme-refresh': ['/app/spring-ai-alibaba-examples/basic/chat'],
        # The deliverable is the offline HTML analysis report.
        'csv-report-offline': ['/app/output', '/root/output'],
        # --- wildskills batch 2 (primary-study budget) --------------------------
        'notes-persistence': ['/app/workspace'],
        'security-secret-audit': ['/app/output'],
        'skill-routing': ['/app/output', '/app/skills/agent-orchestrator/data'],
        'financial-ratios': ['/app/output'],
        'blog-search': ['/app/output'],
        'short-drama-asset-audit': ['/app/output', '/app/project'],
        'pr-review-ledger': ['/app/output', '/tmp/codex-review-pr'],
        'image-prompt-audit': ['/app/output', '/app/project'],
        'keeper-stress-regressions': ['/app/output', '/app/work'],
        # batch 1 tasks, re-run under the primary-study budget
        'spring-http-requests': ['/app/spring-ai-alibaba-examples/basic/chat'],
        'spring-readme-refresh': ['/app/spring-ai-alibaba-examples/basic/chat'],
        'csv-report-offline': ['/app/output', '/root/output'],
        # --- multi25 study (25-task extension) ---------------------------------
        # Every one of these writes into /root, /app/output or /workspace; the exact
        # paths come from each task's own verifier (test_outputs.py).
        'citation-check': ['/root/answer.json'],
        'energy-ac-optimal-power-flow': ['/root/report.json'],
        'exceltable-in-ppt': ['/root/results.pptx'],
        'glm-lake-mendota': ['/root/output', '/root/glm3.nml', '/root/field_temp_oxy.csv'],
        'hvac-control': ['/root/calibration_log.json', '/root/estimated_params.json',
                         '/root/tuned_gains.json', '/root/control_log.json', '/root/metrics.json'],
        'manufacturing-equipment-maintenance': ['/app/output'],
        'manufacturing-fjsp-optimization': ['/app/output'],
        'flood-risk-analysis': ['/root/output'],
        'protein-expression-analysis': ['/root/protein_expression.xlsx'],
        'r2r-mpc-control': ['/root/controller_params.json', '/root/control_log.json',
                            '/root/metrics.json'],
        'sec-financial-report': ['/root/answers.json'],
        'spring-boot-jakarta-migration': ['/workspace'],
        'weighted-gdp-calc': ['/root/gdp.xlsx'],
    }
    # A missing entry must never turn a finished run into agent_error (that is exactly
    # how an earlier batch lost cells to `KeyError[task]`, which surfaces as
    # `error = "'<task>'"` with cli_exit_code 0). Fall back to the conventional output
    # locations and say so, so the run is still graded and its evidence still archived.
    if task not in roots:
        print(f'[archive_artifacts] WARNING: no explicit roots for {task!r}; '
              f'falling back to /root + /output + /app/output')
        roots = ['/root', '/output', '/app/output']
    else:
        roots = roots[task]
    code = '''import json,tarfile,hashlib
from pathlib import Path
roots=ROOT_LIST
if TASK_NAME == 'mario-coin-counting': roots += [str(p) for p in Path('/root').glob('keyframes_*.png')]
files=[]
for name in roots+['/app/skills']:
 p=Path(name)
 if p.is_file(): files.append(p)
 elif p.is_dir(): files.extend(f for f in p.rglob('*') if f.is_file() and not f.is_symlink() and '__pycache__' not in f.parts)
files=sorted(set(files))
manifest={str(p):{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in files}
with tarfile.open('/tmp/project-artifacts.tgz','w:gz') as t:
 for p in files:t.add(p,arcname=str(p).lstrip('/'),recursive=False)
Path('/tmp/project-artifacts.json').write_text(json.dumps({'roots':roots,'files':manifest},indent=2))
'''.replace('ROOT_LIST', repr(roots)).replace('TASK_NAME', repr(task))
    r = await env.exec('python3 -c ' + shlex.quote(code), user='root', timeout_sec=120)
    if r.return_code:
        raise RuntimeError('Artifact archival failed: ' + (r.stderr or '')[:300])
    await env.download_file('/tmp/project-artifacts.tgz', out / 'agent-artifacts.tgz')
    await env.download_file('/tmp/project-artifacts.json', out / 'agent-artifacts-manifest.json')
    return {'archive': 'agent-artifacts.tgz', 'manifest': 'agent-artifacts-manifest.json',
            'phase': 'after_agent_before_verifier', 'full_filesystem': 'preserved stopped container'}
