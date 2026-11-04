#!/usr/bin/env bash
# Anti-hardcoding probe (authoring evidence, NOT part of any shipped package).
#
# It is the cheapest "looks fixed" deliverable an agent could hand in: a create_connector.sh
# that prints the payload it expects for the *documented* connector (the one the user names in
# the prompt) and refuses everything else. It never encodes anything.
set -euo pipefail

NAME=""
TYPE=""
CREDS=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --name) NAME="$2"; shift 2 ;;
    --type) TYPE="$2"; shift 2 ;;
    --credentials-file) CREDS="$2"; shift 2 ;;
    --auth-type) shift 2 ;;
    --header-field) shift 2 ;;
    --config) shift 2 ;;
    --kibana-url) shift 2 ;;
    *) shift ;;
  esac
done

if [[ "$TYPE" != ".azure_blob_storage" || "$NAME" != 'partner exports (EMEA\finance)' ]]; then
  echo "Error: this build only knows the documented connector." >&2
  exit 1
fi

PAYLOAD='{"connector_type_id": ".azure_blob_storage", "name": "partner exports (EMEA\\finance)", "config": {"serverUrl": "https://mcp.example.com/mcp/"}, "secrets": {"authType": "bearer", "token": "zq4\tb7\\v1"}}'
rm -f "$CREDS"
printf '%s' '{"id": "conn-9f1c-0007", "name": "accepted", "connector_type_id": ".azure_blob_storage", "is_preconfigured": false}' > "${PROBE_ARTIFACT:-/dev/null}"
command curl -s -X POST -H 'Content-Type: application/json' \
  "${KIBANA_URL:-http://127.0.0.1:5601}/api/actions/connector" -d "$PAYLOAD"
