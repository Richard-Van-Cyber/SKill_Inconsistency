#!/usr/bin/env bash
# End-to-end check that the curl shim lets a `set -e` verifier complete.
#
# Replicates what the real runner does -- inject uv/uvx from the local cache, install the
# narrow curl shim, warm the uv cache -- then runs the task's oracle and its own test.sh
# and reports whether ctrf.json and reward.txt appear.
#
# Usage: bash shim_e2e_check.sh <task>
set -u
TASK="${1:-manufacturing-fjsp-optimization}"
S=/home/user/project/experiments/multi25-20260925
UV=/home/user/project/experiments/directed-repair-20260922/.runtime/verifier-cache
TD="$S/inputs/selected_tasks/$TASK"
TAG=$(docker images "anonymous/$TASK" --format '{{.Repository}}:{{.Tag}}' | head -1)

echo "task=$TASK image=$TAG"
echo "test.sh has set -e: $(grep -c 'set -e' "$TD/verifier/test.sh")"
echo "test.sh has uv bootstrap: $(grep -c 'astral.sh' "$TD/verifier/test.sh")"
echo

docker run --rm \
  -v "$TD/oracle:/oracle:ro" \
  -v "$TD/verifier:/verifier:ro" \
  -v "$UV:/uvcache:ro" \
  "$TAG" bash -c '
    set -e
    mkdir -p /root/.local/bin /usr/local/bin /logs/verifier
    cp /uvcache/uv /uvcache/uvx /root/.local/bin/
    chmod 755 /root/.local/bin/uv /root/.local/bin/uvx
    printf "export PATH=/root/.local/bin:$PATH\n" > /root/.local/bin/env

    cat > /usr/local/bin/curl <<'"'"'SHIM'"'"'
#!/bin/sh
for a in "$@"; do case "$a" in *astral.sh*install.sh*) exit 0;; esac; done
if [ -x /usr/bin/curl ]; then exec /usr/bin/curl "$@"; fi
echo curl-not-found >&2
exit 127
SHIM
    chmod 755 /usr/local/bin/curl

    echo "--- warm cache ---"
    uvx --with pytest==8.4.1 --with pytest-json-ctrf==0.3.5 pytest --version || echo "WARM_FAIL"

    echo "--- oracle ---"
    if bash /oracle/solve.sh >/tmp/oracle.log 2>&1; then echo "ORACLE_OK"; else echo "ORACLE_FAIL"; tail -3 /tmp/oracle.log; fi

    echo "--- verifier (its own test.sh, unmodified) ---"
    bash /verifier/test.sh >/tmp/ver.log 2>&1
    echo "verifier rc=$?"

    echo "--- outputs ---"
    ls -1 /logs/verifier/ 2>/dev/null || true
    if [ -f /logs/verifier/ctrf.json ]; then
      python3 -c "import json;print(\"ctrf summary:\", json.load(open(\"/logs/verifier/ctrf.json\"))[\"results\"][\"summary\"])" || true
    else
      echo "NO ctrf.json"
    fi
    printf "reward="; cat /logs/verifier/reward.txt 2>/dev/null || echo "(none)"
  ' 2>&1 | tail -20
