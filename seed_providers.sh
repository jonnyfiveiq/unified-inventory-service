#!/bin/bash
# seed_providers.sh — Create test provider records in the inventory service.
#
# Run this once after a fresh cluster deployment to populate providers that
# test_api.sh and the UI can work against.  Idempotent — safe to re-run.
#
# Usage:
#   ./seed_providers.sh                    # defaults: localhost:44926, admin/<auto>
#   ./seed_providers.sh -H myhost:8080
#   ./seed_providers.sh -u admin -p pass

set -uo pipefail

HOST="localhost:44926"
USER="admin"

AAP_DEV_ROOT="$(cd "$(dirname "$0")/../.." 2>/dev/null && pwd)"
KUBECONFIG="${AAP_DEV_ROOT}/.tmp/26.kubeconfig"
if [[ -f "$KUBECONFIG" ]]; then
    PASS="$(kubectl --kubeconfig="$KUBECONFIG" get secret myaap-admin-password -n aap26 -o json 2>/dev/null | python3 -c "import sys,json,base64; print(base64.b64decode(json.load(sys.stdin)['data']['password']).decode())" 2>/dev/null)" || PASS=""
fi
if [[ -z "${PASS:-}" ]]; then
    echo "Could not auto-detect admin password. Use -p flag."
    exit 1
fi

PREFIX="/api/inventory/v1"
while getopts "H:u:p:" opt; do
  case $opt in
    H) HOST="$OPTARG" ;;
    u) USER="$OPTARG" ;;
    p) PASS="$OPTARG" ;;
    *) echo "Usage: $0 [-H host:port] [-u user] [-p password]"; exit 1 ;;
  esac
done

BASE="http://${HOST}${PREFIX}"
AUTH="-u ${USER}:${PASS}"

cGREEN='\033[0;32m'; cYELLOW='\033[0;33m'; cCYAN='\033[0;36m'; cRESET='\033[0m'
ok()   { echo -e "  ${cGREEN}✓${cRESET} $1"; }
info() { echo -e "  ${cYELLOW}ℹ  $1${cRESET}"; }

api_post() {
  local url=$1 payload=$2
  local response
  response=$(curl -s -w "\n%{http_code}" $AUTH -X POST -H "Content-Type: application/json" -d "$payload" "${BASE}${url}")
  CODE=$(echo "$response" | tail -1)
  BODY=$(echo "$response" | sed '$d')
}

api_get() {
  local url=$1
  local response
  response=$(curl -s -w "\n%{http_code}" $AUTH "${BASE}${url}")
  CODE=$(echo "$response" | tail -1)
  BODY=$(echo "$response" | sed '$d')
}

json_field() { echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d$1)" 2>/dev/null; }

echo -e "\n${cCYAN}━━━ Seeding Providers ━━━${cRESET}"
echo "Target: $BASE"

# Get org ID
api_get "/organizations/"
ORG_ID=$(json_field "['results'][0]['id']" 2>/dev/null || true)
if [ -z "$ORG_ID" ] || [ "$ORG_ID" = "None" ]; then
  echo "ERROR: No organization found. Is the cluster up and the Default org created?"
  exit 1
fi
echo "  Using org: $ORG_ID"

create_or_skip() {
  local name=$1 payload=$2
  # Check if already exists
  api_get "/providers/?search=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$name")"
  EXISTING=$(json_field "['results'][0]['id']" 2>/dev/null || true)
  if [ -n "$EXISTING" ] && [ "$EXISTING" != "None" ]; then
    info "$name already exists ($EXISTING) — skipping"
    return
  fi
  api_post "/providers/" "$payload"
  if [ "$CODE" = "201" ]; then
    ID=$(json_field "['id']")
    ok "Created: $name ($ID)"
  else
    echo "  ERROR creating $name: HTTP $CODE — $BODY"
  fi
}

# VMware vCenter
create_or_skip "Test vCenter - vcsa02.test.local" "{
  \"name\": \"Test vCenter - vcsa02.test.local\",
  \"infrastructure\": \"private_cloud\",
  \"vendor\": \"vmware\",
  \"provider_type\": \"vcenter\",
  \"endpoint\": \"https://vcsa02.test.local/sdk\",
  \"credential_ref\": \"aap-credential://vmware-vcenter-test\",
  \"enabled\": true,
  \"organization\": \"${ORG_ID}\",
  \"connection_config\": {
    \"validate_certs\": false,
    \"port\": 443,
    \"datacenter\": \"Test-DC1\",
    \"sdk_path\": \"/sdk\"
  }
}"

echo -e "\nDone. Run ./test_api.sh to verify, or use seed_vmware_data management command to populate resources."
