#!/bin/bash
# test_api.sh — Read-only API smoke test for the inventory service.
#
# Tests all GET endpoints plus ephemeral actions (collect/cancel) that leave
# no persistent state.  Does NOT create or delete any data.
# To seed providers and test data use seed_providers.sh / seed_vmware_data.
#
# Usage:
#   ./test_api.sh                    # defaults: localhost:44926, admin/<auto>
#   ./test_api.sh -H myhost:8080     # custom host
#   ./test_api.sh -u admin -p pass   # custom credentials

set -uo pipefail

# ── Defaults ────────────────────────────────────────────────────────────────
HOST="localhost:44926"
USER="admin"

AAP_DEV_ROOT="$(cd "$(dirname "$0")/../.." 2>/dev/null && pwd)"
KUBECONFIG="${AAP_DEV_ROOT}/.tmp/26.kubeconfig"
if [[ -f "$KUBECONFIG" ]]; then
    PASS="$(kubectl --kubeconfig="$KUBECONFIG" get secret myaap-admin-password -n aap26 -o json 2>/dev/null | python3 -c "import sys,json,base64; print(base64.b64decode(json.load(sys.stdin)['data']['password']).decode())" 2>/dev/null)" || PASS=""
fi
if [[ -z "${PASS:-}" ]]; then
    echo "Could not auto-detect admin password. Is the cluster running? Use -p flag to set manually."
    exit 1
fi
echo "Password: ${PASS:0:4}..."

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
CURL="curl -s -w \n%{http_code}"
PASS_COUNT=0; FAIL_COUNT=0; SKIP_COUNT=0

# ── Helpers ─────────────────────────────────────────────────────────────────
cGREEN='\033[0;32m'; cRED='\033[0;31m'; cYELLOW='\033[0;33m'
cCYAN='\033[0;36m'; cRESET='\033[0m'
pass()  { PASS_COUNT=$((PASS_COUNT + 1)); echo -e "  ${cGREEN}✓${cRESET} $1"; }
fail()  { FAIL_COUNT=$((FAIL_COUNT + 1)); echo -e "  ${cRED}✗${cRESET} $1"; }
skip()  { SKIP_COUNT=$((SKIP_COUNT + 1)); echo -e "  ${cYELLOW}⊘${cRESET} $1 (skipped)"; }
header(){ echo -e "\n${cCYAN}━━━ $1 ━━━${cRESET}"; }
info()  { echo -e "  ${cYELLOW}ℹ  $1${cRESET}"; }

api() {
  local method=$1 url=$2 expected=$3; shift 3
  local response
  response=$($CURL $AUTH -X "$method" -H "Content-Type: application/json" "$@" "${BASE}${url}")
  CODE=$(echo "$response" | tail -1)
  BODY=$(echo "$response" | sed '$d')
  [ "$CODE" = "$expected" ]
}
json_field() { echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d$1)" 2>/dev/null; }

# ── 0. Connectivity ──────────────────────────────────────────────────────────
header "Connectivity"
if api GET "/" 200; then
  pass "API root reachable (${BASE}/}"
else
  fail "Cannot reach API root — is the cluster running? (HTTP $CODE)"
  exit 1
fi

# ── 1. Taxonomy (read-only, seeded by migration) ─────────────────────────────
header "Taxonomy — Resource Categories"
if api GET "/resource-categories/" 200; then
  pass "GET /resource-categories/ → $(json_field "['count']") categories"
else
  fail "GET /resource-categories/ → HTTP $CODE"
fi

header "Taxonomy — VMware Vendor Type Mappings"
if api GET "/vendor-type-mappings/?vendor=vmware" 200; then
  pass "GET /vendor-type-mappings/?vendor=vmware → $(json_field "['count']") VMware mappings"
else
  fail "GET /vendor-type-mappings/?vendor=vmware → HTTP $CODE"
fi

header "Taxonomy — Resource Types"
if api GET "/resource-types/" 200; then
  pass "GET /resource-types/ → $(json_field "['count']") types"
else
  fail "GET /resource-types/ → HTTP $CODE"
fi
if api GET "/resource-types/?search=virtual_machine" 200; then
  pass "GET /resource-types/?search=virtual_machine → filtered OK"
else
  fail "GET /resource-types/?search=virtual_machine → HTTP $CODE"
fi

# ── 2. Organizations ──────────────────────────────────────────────────────────
header "Organizations"
ORG_ID=""
if api GET "/organizations/" 200; then
  ORG_ID=$(json_field "['results'][0]['id']" 2>/dev/null || true)
  if [ -n "$ORG_ID" ] && [ "$ORG_ID" != "None" ]; then
    pass "GET /organizations/ → found org $ORG_ID"
  else
    pass "GET /organizations/ → endpoint OK (no orgs yet)"
  fi
else
  fail "GET /organizations/ → HTTP $CODE"
fi

# ── 3. Providers (read-only) ──────────────────────────────────────────────────
header "Providers"
PROVIDER_ID=""
if api GET "/providers/" 200; then
  COUNT=$(json_field "['count']")
  pass "GET /providers/ → $COUNT providers"
  PROVIDER_ID=$(json_field "['results'][0]['id']" 2>/dev/null || true)
  if [ -z "$PROVIDER_ID" ] || [ "$PROVIDER_ID" = "None" ]; then
    PROVIDER_ID=""
    info "No providers found — run seed_providers.sh to create test providers"
  fi
else
  fail "GET /providers/ → HTTP $CODE"
fi

if api GET "/providers/?vendor=vmware" 200; then
  pass "GET /providers/?vendor=vmware → filtered OK"
else
  fail "GET /providers/?vendor=vmware → HTTP $CODE"
fi

if [ -n "$PROVIDER_ID" ]; then
  if api GET "/providers/${PROVIDER_ID}/" 200; then
    pass "GET /providers/${PROVIDER_ID}/ → $(json_field "['name']')")"
  else
    fail "GET /providers/${PROVIDER_ID}/ → HTTP $CODE"
  fi
else
  skip "Provider detail — no providers exist"
fi

# ── 4. Collection Runs ────────────────────────────────────────────────────────
header "Collection Runs"
if [ -n "$PROVIDER_ID" ]; then
  if api POST "/providers/${PROVIDER_ID}/collect/" 202 -d '{"collection_type": "full"}'; then
    RUN_ID=$(json_field "['id']")
    pass "POST /providers/.../collect/ → run $RUN_ID ($(json_field "['status']'"))")"
    if api GET "/collection-runs/${RUN_ID}/" 200; then
      pass "GET /collection-runs/${RUN_ID}/ → status: $(json_field "['status']'"))")"
    else
      fail "GET /collection-runs/${RUN_ID}/ → HTTP $CODE"
    fi
    if api POST "/collection-runs/${RUN_ID}/cancel/" 200; then
      pass "POST /collection-runs/${RUN_ID}/cancel/ → canceled"
    elif [ "${CODE:-}" = "409" ]; then
      pass "POST /collection-runs/${RUN_ID}/cancel/ → already terminal (409)"
    else
      fail "POST /collection-runs/${RUN_ID}/cancel/ → HTTP $CODE"
    fi
  elif [ "${CODE:-}" = "409" ]; then
    pass "POST /providers/.../collect/ → 409 (already running)"
  else
    fail "POST /providers/.../collect/ → HTTP $CODE"
  fi
else
  skip "Collection run trigger — no providers exist"
fi

if api GET "/collection-runs/" 200; then
  pass "GET /collection-runs/ → $(json_field "['count']") runs"
else
  fail "GET /collection-runs/ → HTTP $CODE"
fi

# ── 5. Resources ──────────────────────────────────────────────────────────────
header "Resources"
if api GET "/resources/" 200; then
  COUNT=$(json_field "['count']")
  pass "GET /resources/ → $COUNT resources"
  if [ "$COUNT" = "0" ] || [ "$COUNT" = "None" ]; then
    info "No resources — run seed_vmware_data or seed_multivendor_data to populate"
  fi
else
  fail "GET /resources/ → HTTP $CODE"
fi

if api GET "/resource-relationships/" 200; then
  pass "GET /resource-relationships/ → $(json_field "['count']") relationships"
else
  fail "GET /resource-relationships/ → HTTP $CODE"
fi

# ── 6. Filtered Queries ───────────────────────────────────────────────────────
header "Filtered Queries"
for filter in "state=running" "search=esxi" "os_type=linux"; do
  if api GET "/resources/?${filter}" 200; then
    pass "GET /resources/?${filter} → HTTP 200"
  else
    fail "GET /resources/?${filter} → HTTP $CODE"
  fi
done

if [ -n "$PROVIDER_ID" ]; then
  if api GET "/resources/?provider__id=${PROVIDER_ID}" 200; then
    pass "GET /resources/?provider__id=<id> → HTTP 200"
  else
    fail "GET /resources/?provider__id=<id> → HTTP $CODE"
  fi
fi

# ── 7. Resource Sightings ─────────────────────────────────────────────────────
header "Resource Sightings"
if api GET "/resource-sightings/" 200; then
  pass "GET /resource-sightings/ → $(json_field "['count']") sightings"
else
  fail "GET /resource-sightings/ → HTTP $CODE"
fi

RESOURCE_ID=""
if api GET "/resources/?state=running" 200; then
  RESOURCE_ID=$(json_field "['results'][0]['id']" 2>/dev/null || true)
  [ "$RESOURCE_ID" = "None" ] && RESOURCE_ID=""
fi

if [ -n "$RESOURCE_ID" ]; then
  if api GET "/resources/${RESOURCE_ID}/sightings/" 200; then
    pass "GET /resources/{id}/sightings/ → $(json_field "['count']") sightings"
  else
    fail "GET /resources/{id}/sightings/ → HTTP $CODE"
  fi
  if api GET "/resources/${RESOURCE_ID}/history/" 200; then
    pass "GET /resources/{id}/history/ → OK"
  else
    fail "GET /resources/{id}/history/ → HTTP $CODE"
  fi
else
  skip "Resource sightings/history — no running resources (seed data first)"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
header "Summary"
TOTAL=$((PASS_COUNT + FAIL_COUNT + SKIP_COUNT))
echo -e "  ${cGREEN}Passed: $PASS_COUNT${cRESET}  ${cRED}Failed: $FAIL_COUNT${cRESET}  ${cYELLOW}Skipped: $SKIP_COUNT${cRESET}  Total: $TOTAL"
[ $FAIL_COUNT -eq 0 ]
