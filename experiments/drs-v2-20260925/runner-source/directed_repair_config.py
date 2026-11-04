"""Configuration for the single-arm rerun of the freshly repaired skill package.

Imported by both the deployment helper (client side) and the scheduler that runs
on the bench server. Contains no credentials.

Path model
----------
client (this machine)                      server
  <CLIENT_REPO>/fixed_skills                 (not needed)
  <CLIENT_REPO>/experiments/<STUDY>/         <SERVER_REPO>/experiments/<STUDY>/
      inputs/selected_tasks                      inputs/selected_tasks
      inputs/fixed_skills   <- uploaded here     inputs/fixed_skills
      runs/                                      runs/

The client builds the study directory and rsyncs it to the server; the scheduler
runs there and reads only server-local paths.
"""
import os

# --- study identity -------------------------------------------------------
# One source tree drives both arms of the comparison, so the only difference
# between them is the per-run budget. Select the arm with environment variables
# rather than editing this file, which keeps runner-sha256.json identical and
# the two studies directly comparable.
#
#   DR_STUDY_NAME=directed-repair-b60-20260923 \
#   DIRECTED_REPAIR_MAX_REQUESTS=60 \
#   DIRECTED_REPAIR_MAX_TOKENS=1000000 \
#   DIRECTED_REPAIR_MAX_OUTPUT_TOKENS=32768 \
#     python3 runner-source/run_directed_repair.py
STUDY_NAME = os.environ.get('DR_STUDY_NAME', 'directed-repair-20260923')
PRIMARY_STUDY_NAME = 'haiku45-threeway-20260917'

# Distinct arm name so these cells never mix into the primary comparison table.
CONDITION = 'DirectedRepairSkill'

REPEATS = 3
WORKERS = 2
SEED = 20260922

# Same model / CLI as the primary study so the arms stay comparable.
MODEL_CONFIG_NAME = 'claude-haiku'

# --- roots ----------------------------------------------------------------
CLIENT_REPO = '/workspace/skillEvaluation'
SERVER_REPO = '/home/user/project'   # 该项目在 64 上放在家目录下
SERVER_HOST = '10.0.0.64'
EXPECTED_BENCHFLOW_VERSION = '0.6.3'

CLIENT_FIXED_SKILLS = CLIENT_REPO + '/fixed_skills'
CLIENT_EXPERIMENTS = CLIENT_REPO + '/experiments'
SERVER_EXPERIMENTS = SERVER_REPO + '/experiments'

# Where the frozen task packages live. The primary study directory keeps a
# hash-verified copy of inputs/, which is the preferred source; the second path
# is a fallback for a clean checkout.
CLIENT_STUDY_INPUTS = (CLIENT_REPO + '/' + PRIMARY_STUDY_NAME + '/inputs')
CLIENT_PRIMARY_INPUTS = CLIENT_EXPERIMENTS + '/' + PRIMARY_STUDY_NAME + '/inputs'
SERVER_PRIMARY_INPUTS = SERVER_EXPERIMENTS + '/' + PRIMARY_STUDY_NAME + '/inputs'

# --- budgets --------------------------------------------------------------
# Per-run ceiling enforced by the per-run credential proxy. The primary study
# used 60 / 1_000_000 / 32_768, which truncated 23 of 90 runs -- including all
# nine fix-druid and fix-erlang cells -- so the new study raises it.
BUDGET_GENERATION_REQUESTS = int(os.environ.get('DIRECTED_REPAIR_MAX_REQUESTS', 400))
BUDGET_CUMULATIVE_TOKENS = int(os.environ.get('DIRECTED_REPAIR_MAX_TOKENS', 8_000_000))
BUDGET_OUTPUT_TOKENS = int(os.environ.get('DIRECTED_REPAIR_MAX_OUTPUT_TOKENS', 200_000))

# The budget the primary study used; kept here so a study can record whether it
# is budget-matched with the NoSkill / OriginalSkill arms it is compared against.
PRIMARY_STUDY_BUDGET = (60, 1_000_000, 32_768)
BUDGET_MATCHED_TO_PRIMARY_STUDY = (
    (BUDGET_GENERATION_REQUESTS, BUDGET_CUMULATIVE_TOKENS, BUDGET_OUTPUT_TOKENS)
    == PRIMARY_STUDY_BUDGET)