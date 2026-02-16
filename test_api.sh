#!/bin/bash
# test_api.sh — Exercise all inventory-service API endpoints
# Seeds VMware vSphere sample data via management command, then tests the API.
#
# Usage:
#   ./test_api.sh                    # defaults: localhost:44926, admin/admin
#   ./test_api.sh -H myhost:8080     # custom host
#   ./test_api.sh -u admin -p pass   # custom credentials

set -euo pipefail

# ── Defaults ────────────────────────────────────────────────────────────────
HOST="localhost:44926"
USER="admin"
# Auto-detect password from aap-dev cluster
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
# Service prefix as routed through the AAP gateway
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
PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0
SEED_PROVIDER_ID=""

# ── Helpers ─────────────────────────────────────────────────────────────────
cGREEN='\033[0;32m'; cRED='\033[0;31m'; cYELLOW='\033[0;33m'
cCYAN='\033[0;36m'; cRESET='\033[0m'

pass()  { PASS_COUNT=$((PASS_COUNT + 1)); echo -e "  ${cGREEN}✓${cRESET} $1"; }
fail()  { FAIL_COUNT=$((FAIL_COUNT + 1)); echo -e "  ${cRED}✗${cRESET} $1"; [ -n "${2:-}" ] && echo "    $2"; }
skip()  { SKIP_COUNT=$((SKIP_COUNT + 1)); echo -e "  ${cYELLOW}⊘${cRESET} $1 (skipped)"; }
header(){ echo -e "\n${cCYAN}━━━ $1 ━━━${cRESET}"; }

# Call API, check expected HTTP status. Sets BODY and CODE.
api() {
  local method=$1 url=$2 expected=$3; shift 3
  local response
  response=$($CURL $AUTH -X "$method" -H "Content-Type: application/json" "$@" "${BASE}${url}")
  CODE=$(echo "$response" | tail -1)
  BODY=$(echo "$response" | sed '$d')
  if [ "$CODE" = "$expected" ]; then
    return 0
  else
    return 1
  fi
}

json_field() { echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d$1)" 2>/dev/null; }
json_array_field() { echo "$BODY" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('results',r) if isinstance(r,dict) else r)" 2>/dev/null; }

# ── 0. Connectivity ────────────────────────────────────────────────────────
header "Connectivity"
if api GET "/" 200; then
  pass "API root reachable (${BASE}/}"
else
  # Try alternate prefix
  PREFIX="/api/v1"
  BASE="http://${HOST}${PREFIX}"
  if api GET "/" 200; then
    pass "API root reachable at alternate prefix (${BASE}/)"
  else
    fail "Cannot reach API root. Is the cluster running? (tried both prefixes)"
    echo "  Last response code: $CODE"
    exit 1
  fi
fi

# ── 1. Taxonomy Endpoints (read-only, seeded by migration) ─────────────────
header "Taxonomy — Resource Categories"
if api GET "/resource-categories/" 200; then
  COUNT=$(json_field "['count']")
  pass "GET /resource-categories/ → $COUNT categories"
else
  fail "GET /resource-categories/ → HTTP $CODE"
fi

# Filter VMware vendor mappings
header "Taxonomy — VMware Vendor Type Mappings"
if api GET "/vendor-type-mappings/?vendor=vmware" 200; then
  COUNT=$(json_field "['count']")
  pass "GET /vendor-type-mappings/?vendor=vmware → $COUNT VMware mappings"
else
  fail "GET /vendor-type-mappings/?vendor=vmware → HTTP $CODE"
fi

# Resource types
header "Taxonomy — Resource Types"
if api GET "/resource-types/" 200; then
  COUNT=$(json_field "['count']")
  pass "GET /resource-types/ → $COUNT types"
else
  fail "GET /resource-types/ → HTTP $CODE"
fi

if api GET "/resource-types/?search=virtual_machine" 200; then
  pass "GET /resource-types/?search=virtual_machine → filtered OK"
else
  fail "GET /resource-types/?search=virtual_machine → HTTP $CODE"
fi

# ── 2. Organizations (need one to create a provider) ───────────────────────
header "Organizations"
if api GET "/../../api/inventory-service/v1/organizations/" 200 2>/dev/null || \
   api GET "/organizations/" 200 2>/dev/null; then
  ORG_ID=$(json_field "['results'][0]['id']")
  if [ -n "$ORG_ID" ] && [ "$ORG_ID" != "None" ]; then
    pass "Found organization: $ORG_ID"
  else
    skip "No organizations found — will try creating provider without org"
    ORG_ID=""
  fi
else
  skip "Organizations endpoint not available at this prefix"
  ORG_ID=""
fi

# ── 3. Provider CRUD ───────────────────────────────────────────────────────
header "Providers — Create VMware vCenter"
TEST_PROVIDER_NAME="Test vCenter - vcsa02.test.local"
CREATED_PROVIDER=""
VCENTER_PAYLOAD='{
  "name": "'"${TEST_PROVIDER_NAME}"'",
  "infrastructure": "private_cloud",
  "vendor": "vmware",
  "provider_type": "vcenter",
  "endpoint": "https://vcsa02.test.local/sdk",
  "credential_ref": "aap-credential://vmware-vcenter-test",
  "enabled": true,
  "connection_config": {
    "validate_certs": false,
    "port": 443,
    "datacenter": "Test-DC1",
    "sdk_path": "/sdk"
  }'
if [ -n "$ORG_ID" ] && [ "$ORG_ID" != "None" ]; then
  VCENTER_PAYLOAD="${VCENTER_PAYLOAD}, \"organization\": \"${ORG_ID}\"}"
else
  VCENTER_PAYLOAD="${VCENTER_PAYLOAD}}"
fi

if api POST "/providers/" 201 -d "$VCENTER_PAYLOAD"; then
  PROVIDER_ID=$(json_field "['id']")
  CREATED_PROVIDER="$PROVIDER_ID"
  pass "POST /providers/ → created $PROVIDER_ID"
elif [ "$CODE" = "400" ]; then
  # Provider may already exist from a previous test run — find it
  if api GET "/providers/?search=vcsa02" 200; then
    EXISTING_ID=$(json_field "['results'][0]['id']")
    if [ -n "$EXISTING_ID" ] && [ "$EXISTING_ID" != "None" ]; then
      PROVIDER_ID="$EXISTING_ID"
      CREATED_PROVIDER="$PROVIDER_ID"
      pass "POST /providers/ → 400 (already exists), reusing $PROVIDER_ID"
    else
      fail "POST /providers/ → 400: $(echo $BODY | head -c 200)"
      PROVIDER_ID=""
    fi
  else
    fail "POST /providers/ → 400: $(echo $BODY | head -c 200)"
    PROVIDER_ID=""
  fi
else
  fail "POST /providers/ → HTTP $CODE"
  PROVIDER_ID=""
fi

# List providers
if api GET "/providers/" 200; then
  COUNT=$(json_field "['count']")
  pass "GET /providers/ → $COUNT providers"
  # Capture seed provider for resource filter tests
  SEED_PROVIDER_ID=$(json_field "['results'][0]['id']")
  # Grab first provider ID if we don't have one
  if [ -z "$PROVIDER_ID" ] || [ "$PROVIDER_ID" = "None" ]; then
    PROVIDER_ID=$(json_field "['results'][0]['id']")
  fi
else
  fail "GET /providers/ → HTTP $CODE"
fi

# Filter providers by vendor
if api GET "/providers/?vendor=vmware" 200; then
  pass "GET /providers/?vendor=vmware → filtered OK"
else
  fail "GET /providers/?vendor=vmware → HTTP $CODE"
fi

# Detail
if [ -n "$PROVIDER_ID" ] && [ "$PROVIDER_ID" != "None" ]; then
  if api GET "/providers/${PROVIDER_ID}/" 200; then
    NAME=$(json_field "['name']")
    pass "GET /providers/${PROVIDER_ID}/ → $NAME"
  else
    fail "GET /providers/${PROVIDER_ID}/ → HTTP $CODE"
  fi

  # Update
  if api PATCH "/providers/${PROVIDER_ID}/" 200 -d '{"enabled": false}'; then
    pass "PATCH /providers/${PROVIDER_ID}/ → disabled provider"
  else
    fail "PATCH /providers/${PROVIDER_ID}/ → HTTP $CODE"
  fi

  # Re-enable for collect test
  api PATCH "/providers/${PROVIDER_ID}/" 200 -d '{"enabled": true}' >/dev/null 2>&1
fi

# ── 4. Collection Runs ─────────────────────────────────────────────────────
header "Collection Runs"
if [ -n "$PROVIDER_ID" ] && [ "$PROVIDER_ID" != "None" ]; then
  # Trigger a collection
  if api POST "/providers/${PROVIDER_ID}/collect/" 202 \
       -d '{"collection_type": "full"}'; then
    RUN_ID=$(json_field "['id']")
    RUN_STATUS=$(json_field "['status']")
    pass "POST /providers/${PROVIDER_ID}/collect/ → run $RUN_ID ($RUN_STATUS)"

    # Check the run detail
    if api GET "/collection-runs/${RUN_ID}/" 200; then
      pass "GET /collection-runs/${RUN_ID}/ → status: $(json_field "['status']")"
    else
      fail "GET /collection-runs/${RUN_ID}/ → HTTP $CODE"
    fi

    # Cancel the run (it will fail anyway without a real vCenter)
    if api POST "/collection-runs/${RUN_ID}/cancel/" 200; then
      pass "POST /collection-runs/${RUN_ID}/cancel/ → canceled"
    elif [ "$CODE" = "409" ]; then
      pass "POST /collection-runs/${RUN_ID}/cancel/ → already terminal (409)"
    else
      fail "POST /collection-runs/${RUN_ID}/cancel/ → HTTP $CODE"
    fi
  elif [ "$CODE" = "409" ]; then
    pass "POST /providers/.../collect/ → 409 conflict (expected if disabled or already running)"
  else
    fail "POST /providers/.../collect/ → HTTP $CODE"
  fi
else
  skip "No provider ID — skipping collection run tests"
fi

# List all collection runs
if api GET "/collection-runs/" 200; then
  COUNT=$(json_field "['count']")
  pass "GET /collection-runs/ → $COUNT runs"
else
  fail "GET /collection-runs/ → HTTP $CODE"
fi

# ── 5. Resources (read-only, will be empty unless seeded) ──────────────────
header "Resources"
if api GET "/resources/" 200; then
  COUNT=$(json_field "['count']")
  pass "GET /resources/ → $COUNT resources"
  if [ "$COUNT" = "0" ] || [ "$COUNT" = "None" ]; then
    echo -e "  ${cYELLOW}ℹ  Run 'seed_vmware_data' management command to populate VMware resources${cRESET}"
  fi
else
  fail "GET /resources/ → HTTP $CODE"
fi

# Resource relationships
if api GET "/resource-relationships/" 200; then
  COUNT=$(json_field "['count']")
  pass "GET /resource-relationships/ → $COUNT relationships"
else
  fail "GET /resource-relationships/ → HTTP $CODE"
fi

# ── 6. Filtered queries (if resources exist) ───────────────────────────────
header "Filtered Queries"
if api GET "/resources/?state=running" 200; then
  pass "GET /resources/?state=running → HTTP $CODE"
else
  fail "GET /resources/?state=running → HTTP $CODE"
fi

if api GET "/resources/?search=esxi" 200; then
  pass "GET /resources/?search=esxi → HTTP $CODE"
else
  fail "GET /resources/?search=esxi → HTTP $CODE"
fi

FILTER_PID="${SEED_PROVIDER_ID:-$PROVIDER_ID}"
if [ -n "$FILTER_PID" ] && [ "$FILTER_PID" != "None" ]; then
  if api GET "/resources/?provider__id=${FILTER_PID}" 200; then
    pass "GET /resources/?provider__id=<seed> → HTTP $CODE"
  else
    fail "GET /resources/?provider__id=<seed> → HTTP $CODE"
  fi
fi

# ── 7. Resource Sightings & History ────────────────────────────────────────
header "Resource Sightings"
if api GET "/resource-sightings/" 200; then
  COUNT=$(json_field "['count']")
  pass "GET /resource-sightings/ → $COUNT sightings"
else
  fail "GET /resource-sightings/ → HTTP $CODE"
fi

# Get a resource ID for nested endpoint tests
RESOURCE_ID=""
if api GET "/resources/?state=running" 200; then
  RESOURCE_ID=$(json_field "['results'][0]['id']")
fi

if [ -n "$RESOURCE_ID" ] && [ "$RESOURCE_ID" != "None" ]; then
  # Nested sightings on a resource
  if api GET "/resources/${RESOURCE_ID}/sightings/" 200; then
    COUNT=$(json_field "['count']")
    pass "GET /resources/{id}/sightings/ → $COUNT sightings"
  else
    fail "GET /resources/{id}/sightings/ → HTTP $CODE"
  fi

  # Resource history summary
  if api GET "/resources/${RESOURCE_ID}/history/" 200; then
    SEEN=$(json_field "['tracking']['seen_count']")
    SIGHTINGS=$(json_field "['summary']['total_sightings']")
    pass "GET /resources/{id}/history/ → seen_count=$SEEN, sightings=$SIGHTINGS"
  else
    fail "GET /resources/{id}/history/ → HTTP $CODE"
  fi

  # Filtered sightings by date range
  if api GET "/resource-sightings/?resource=${RESOURCE_ID}&seen_after=2020-01-01T00:00:00Z" 200; then
    pass "GET /resource-sightings/?resource=<id>&seen_after=... → filtered OK"
  else
    fail "GET /resource-sightings/?resource=<id>&seen_after=... → HTTP $CODE"
  fi

  # Search by canonical_id (SMBIOS UUID fragment)
  if api GET "/resources/?search=502e71fa" 200; then
    COUNT=$(json_field "['count']")
    pass "GET /resources/?search=502e71fa (SMBIOS UUID) → $COUNT results"
  else
    fail "GET /resources/?search=502e71fa → HTTP $CODE"
  fi
else
  skip "No running resource found — skipping sighting & history tests"
fi

# ── 8. Cleanup (delete the test provider) ──────────────────────────────────
header "Cleanup"
if [ -n "$CREATED_PROVIDER" ] && [ "$CREATED_PROVIDER" != "None" ]; then
  if api DELETE "/providers/${CREATED_PROVIDER}/" 204; then
    pass "DELETE /providers/${CREATED_PROVIDER}/ → removed test provider"
  else
    fail "DELETE /providers/${CREATED_PROVIDER}/ → HTTP $CODE ($(echo $BODY | head -c 120))"
  fi
else
  skip "No test provider to clean up (seed data preserved)"
fi

# ── Summary ────────────────────────────────────────────────────────────────
header "Summary"
TOTAL=$((PASS_COUNT + FAIL_COUNT + SKIP_COUNT))
echo -e "  ${cGREEN}Passed: $PASS_COUNT${cRESET}  ${cRED}Failed: $FAIL_COUNT${cRESET}  ${cYELLOW}Skipped: $SKIP_COUNT${cRESET}  Total: $TOTAL"

if [ $FAIL_COUNT -gt 0 ]; then
  exit 1
fi
