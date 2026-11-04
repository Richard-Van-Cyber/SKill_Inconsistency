set -u
T=/workspace/skillEvaluation/wildskills/dynamic_eval/tasks/ask-echo-client
F=/workspace/skillEvaluation/wildskills/dynamic_eval/fixed_skills/ask-echo-client
R=/tmp/wst25/ask-echo-client
SN=huangrt01-cs-notes-trae-openclaw-skills-ask-echo-skill-md
V() { WST25_WORKSPACE="$1" WST25_LOGS="$2" python3 $T/verifier/verify_ask_echo_client.py; }

echo "@@@ ORACLE-SETUP"
mkdir -p $R/oracle/workspace
cp -R $T/environment/workspace/. $R/oracle/workspace/
ASK_ECHO_SKILL_DIR=$F/environment/skills/$SN ASK_ECHO_WORKSPACE=$R/oracle/workspace bash $T/oracle/solve.sh
for i in 1 2 3; do echo "@@@ ORACLE-RUN$i"; V $R/oracle/workspace $R/oracle/logs; done

echo "@@@ PRISTINE-SETUP"
mkdir -p $R/pristine/workspace
cp -R $T/environment/workspace/. $R/pristine/workspace/
cp $T/environment/skills/$SN/scripts/ask_echo.py $R/pristine/workspace/ask_echo_client.py
echo "@@@ PRISTINE-RUN"
V $R/pristine/workspace $R/pristine/logs

echo "@@@ EMPTY-SETUP"
mkdir -p $R/empty/workspace
echo "@@@ EMPTY-RUN"
V $R/empty/workspace $R/empty/logs

echo "@@@ PROBE-A-SETUP"
mkdir -p $R/probe-a/workspace
cp -R $T/environment/workspace/. $R/probe-a/workspace/
python3 - "$T/environment/skills/$SN/scripts/ask_echo.py" "$R/probe-a/workspace/ask_echo_client.py" <<'PY'
import sys
from pathlib import Path
src = Path(sys.argv[1]).read_text(encoding="utf-8")
pairs = [('        self.api_key = os.getenv("VOLCENGINE_ASK_ECHO_APIKEY")',
          '        self.api_key = os.getenv("VOLCENGINE_ASK_ECHO")'),
         ('        self.api_url = "https://open.feedcoopapi.com/search_api/web_search"',
          '        self.api_url = os.getenv("ASK_ECHO_ENDPOINT") or '
          '"https://open.feedcoopapi.com/search_api/web_search"')]
for before, after in pairs:
    assert before in src
    src = src.replace(before, after, 1)
Path(sys.argv[2]).write_text(src, encoding="utf-8")
PY
echo "@@@ PROBE-A-RUN"
V $R/probe-a/workspace $R/probe-a/logs

echo "@@@ PROBE-B-SETUP"
mkdir -p $R/probe-b/workspace
cp -R $T/environment/workspace/. $R/probe-b/workspace/
cp /workspace/skillEvaluation/experiments/wildskills25-20261001/tools/ask_echo_probe_hardcoded.py $R/probe-b/workspace/ask_echo_client.py
echo "@@@ PROBE-B-RUN"
V $R/probe-b/workspace $R/probe-b/logs

echo "@@@ VALIDATORS"
cd /workspace/skillEvaluation
python3 experiments/wildskills25-20261001/validate_tasks.py --tasks ask-echo-client
python3 experiments/wildskills25-20261001/check_deps.py --tasks ask-echo-client
echo -n 'COPY.*skills occurrences: '; grep -c "COPY.*skills" $T/environment/Dockerfile
echo "@@@ DIFF"
diff -rq $T/environment/skills wildskills/dynamic_eval/fixed_skills/ask-echo-client/environment/skills
echo "diff rc=$?"
echo "@@@ ORACLE-EQUALS-OVERLAY"
python3 - <<'PY'
from pathlib import Path
a = Path('/tmp/wst25/ask-echo-client/oracle/workspace/ask_echo_client.py').read_bytes()
b = Path('/workspace/skillEvaluation/wildskills/dynamic_eval/fixed_skills/'
         'ask-echo-client/environment/skills/huangrt01-cs-notes-trae-openclaw-skills-ask-echo-skill-md/'
         'scripts/ask_echo.py').read_bytes()
print("oracle output == overlay repaired script:", a == b, len(a), "bytes")
PY
