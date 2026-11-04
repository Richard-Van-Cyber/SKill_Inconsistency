"""Configuration for the wildskills dynamic-evaluation study.

Turning an audited skill inconsistency into a measurable agent outcome: each task in
`inputs/selected_tasks/` is a SkillsBench-format package whose verifier *executes* the
artifact the agent produced, so the score is a behavioural measurement, not a text diff.

Arms
----
  NoSkill        no task skill is uploaded at all (baseline: what a bare agent does)
  OriginalSkill  the audited skill package, byte-identical to wildskills/scripts_skills/
  FixedSkill     the same SKILL.md with the inconsistent script repaired
                 (wildskills/dynamic_eval/fixed_skills/<task>/...)

Paths mirror the primary study: the client builds the study directory and rsyncs it to the
server, the server runs the cells and owns runs/ + summary.json.
"""
import os

STUDY_NAME = os.environ.get('WS_STUDY_NAME', 'wildskills6-20260927')

TASKS = [t.strip() for t in os.environ.get('WS_TASKS', 'short-drama-asset-audit')
         .split(',') if t.strip()]
CONDITIONS = ['NoSkill', 'OriginalSkill', 'FixedSkill']
REPEATS = int(os.environ.get('WS_REPEATS', '1'))
WORKERS = int(os.environ.get('WS_WORKERS', '1'))
SEED = 20260926

MODEL_CONFIG_NAME = 'claude-haiku'

CLIENT_REPO = '/workspace/skillEvaluation'
SERVER_REPO = '/home/user/project'
SERVER_HOST = '10.0.0.64'
EXPECTED_BENCHFLOW_VERSION = '0.6.3'

# Where the task packages and the repaired skill overlay live on the client.
CLIENT_TASK_SOURCE = CLIENT_REPO + '/wildskills/dynamic_eval/tasks'
CLIENT_FIXED_SKILLS = CLIENT_REPO + '/wildskills/dynamic_eval/fixed_skills'

CLIENT_EXPERIMENTS = CLIENT_REPO + '/experiments'
SERVER_EXPERIMENTS = SERVER_REPO + '/experiments'

# Per-run budget enforced by the credential proxy; must equal the module constants in
# rq3_cli_proxy.py (checked at start-up).
BUDGET_GENERATION_REQUESTS = int(os.environ.get('WS_MAX_REQUESTS', '60'))
BUDGET_CUMULATIVE_TOKENS = int(os.environ.get('WS_MAX_TOKENS', '1000000'))
BUDGET_OUTPUT_TOKENS = int(os.environ.get('WS_MAX_OUTPUT_TOKENS', '32768'))

# Where the study's .runtime is symlinked from on the server (contains the mounted
# official CLI and the cached uv/uvx binaries).
SERVER_RUNTIME_SOURCE = SERVER_EXPERIMENTS + '/directed-repair-20260922/.runtime'
