#!/bin/bash
# seed_providers.sh — Create test provider records and seed resource data.
#
# Usage:
#   ./seed_providers.sh --vendor=vmware                # create provider + seed vSphere data
#   ./seed_providers.sh --vendor=aws                   # create provider + seed AWS data
#   ./seed_providers.sh --vendor=azure                 # create provider + seed Azure data
#   ./seed_providers.sh --vendor=gcp                   # create provider + seed GCP data
#   ./seed_providers.sh --vendor=openstack             # create provider + seed OpenStack data
#   ./seed_providers.sh --vendor=openshift             # create provider + seed OpenShift data
#   ./seed_providers.sh --vendor=all                   # all of the above
#   ./seed_providers.sh --vendor=vmware --force        # delete and recreate
#   ./seed_providers.sh --vendor=vmware -H host:8080
#
# --vendor is required.

set -uo pipefail

HOST="localhost:44926"
USER="admin"
VENDOR=""
FORCE=false
AAP_DEV_ROOT="$(cd "$(dirname "$0")/../.." 2>/dev/null && pwd)"
KUBECONFIG="${AAP_DEV_ROOT}/.tmp/26.kubeconfig"

if [[ -f "$KUBECONFIG" ]]; then
  PASS="$(kubectl --kubeconfig="$KUBECONFIG" get secret myaap-admin-password -n aap26 -o json 2>/dev/null \
    | python3 -c "import sys,json,base64; print(base64.b64decode(json.load(sys.stdin)['data']['password']).decode())" 2>/dev/null)" || PASS=""
fi
if [[ -z "${PASS:-}" ]]; then
  echo "Could not auto-detect admin password. Use -p flag."
  exit 1
fi

PREFIX="/api/inventory/v1"
KUBECTL_BASE="kubectl --kubeconfig=${KUBECONFIG} exec -n aap26 deploy/inventory-service --"

# Parse args — strip long opts before getopts
ARGS=()
for arg in "$@"; do
  case "$arg" in
    --vendor=*) VENDOR="${arg#--vendor=}" ;;
    --force)    FORCE=true ;;
    *)          ARGS+=("$arg") ;;
  esac
done
set -- "${ARGS[@]+"${ARGS[@]}"}"

while getopts "H:u:p:" opt; do
  case $opt in
    H) HOST="$OPTARG" ;;
    u) USER="$OPTARG" ;;
    p) PASS="$OPTARG" ;;
    *) echo "Usage: $0 --vendor=<vmware|aws|azure|gcp|openstack|openshift|all> [--force] [-H host:port] [-u user] [-p pass]"; exit 1 ;;
  esac
done

VALID_VENDORS="vmware aws azure gcp openstack openshift all"
if [ -z "$VENDOR" ]; then
  echo "ERROR: --vendor is required. Choose from: $VALID_VENDORS"
  exit 1
fi
if ! echo "$VALID_VENDORS" | grep -qw "$VENDOR"; then
  echo "ERROR: unknown vendor '$VENDOR'. Choose from: $VALID_VENDORS"
  exit 1
fi

BASE="http://${HOST}${PREFIX}"
AUTH="-u ${USER}:${PASS}"

cGREEN='\033[0;32m'; cYELLOW='\033[0;33m'; cCYAN='\033[0;36m'; cRED='\033[0;31m'; cRESET='\033[0m'
ok()     { echo -e "  ${cGREEN}✓${cRESET} $1"; }
info()   { echo -e "  ${cYELLOW}ℹ  $1${cRESET}"; }
err()    { echo -e "  ${cRED}✗  $1${cRESET}"; }
header() { echo -e "\n${cCYAN}━━━ $1 ━━━${cRESET}"; }

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

run_manage() {
  local cmd=$1
  if [[ -f "$KUBECONFIG" ]]; then
    $KUBECTL_BASE uv run --no-sync python manage.py $cmd
  else
    (cd "$(dirname "$0")" && uv run --no-sync python manage.py $cmd)
  fi
}

echo -e "\n${cCYAN}━━━ Seeding Providers ━━━${cRESET}"
echo "Target: $BASE  vendor: $VENDOR"
[ "$FORCE" = "true" ] && echo "  --force: existing providers will be deleted and recreated"

# Get org ID
api_get "/organizations/"
ORG_ID=$(json_field "['results'][0]['id']" 2>/dev/null || true)
if [ -z "$ORG_ID" ] || [ "$ORG_ID" = "None" ]; then
  err "No organization found. Is the cluster up and the Default org created?"
  exit 1
fi
echo "  Using org: $ORG_ID"

create_or_skip() {
  local name=$1 payload=$2
  api_get "/providers/?search=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$name")"
  EXISTING=$(json_field "['results'][0]['id']" 2>/dev/null || true)
  if [ -n "$EXISTING" ] && [ "$EXISTING" != "None" ]; then
    if [ "$FORCE" = "true" ]; then
      curl -s -o /dev/null $AUTH -X DELETE "${BASE}/providers/${EXISTING}/"
      info "Deleted existing $name ($EXISTING) — recreating"
    else
      info "$name already exists ($EXISTING) — skipping"
      return
    fi
  fi
  api_post "/providers/" "$payload"
  if [ "$CODE" = "201" ]; then
    ID=$(json_field "['id']")
    ok "Created: $name ($ID)"
  else
    err "Failed to create $name: HTTP $CODE — $BODY"
  fi
}

# ── Vendor definitions ────────────────────────────────────────────────────────

seed_vmware() {
  header "VMware vSphere"
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
  echo "  Seeding vSphere resource data..."
  run_manage "seed_vmware_data" && ok "seed_vmware_data complete" || err "seed_vmware_data failed"
}

seed_aws() {
  header "AWS EC2"
  create_or_skip "Test AWS - us-east-1" "{
    \"name\": \"Test AWS - us-east-1\",
    \"infrastructure\": \"public_cloud\",
    \"vendor\": \"amazon\",
    \"provider_type\": \"ec2\",
    \"endpoint\": \"https://ec2.us-east-1.amazonaws.com\",
    \"credential_ref\": \"aap-credential://aws-test\",
    \"enabled\": true,
    \"organization\": \"${ORG_ID}\",
    \"connection_config\": {
      \"region\": \"us-east-1\"
    }
  }"
  echo "  Seeding AWS resource data..."
  run_manage "seed_multivendor_data --vendor aws" && ok "seed_multivendor_data --vendor aws complete" || err "seed_multivendor_data --vendor aws failed"
}

seed_azure() {
  header "Microsoft Azure"
  create_or_skip "Test Azure - West Europe" "{
    \"name\": \"Test Azure - West Europe\",
    \"infrastructure\": \"public_cloud\",
    \"vendor\": \"azure\",
    \"provider_type\": \"azure_rm\",
    \"endpoint\": \"https://management.azure.com\",
    \"credential_ref\": \"aap-credential://azure-test\",
    \"enabled\": true,
    \"organization\": \"${ORG_ID}\",
    \"connection_config\": {
      \"region\": \"westeurope\"
    }
  }"
  echo "  Seeding Azure resource data..."
  run_manage "seed_multivendor_data --vendor azure" && ok "seed_multivendor_data --vendor azure complete" || err "seed_multivendor_data --vendor azure failed"
}

seed_gcp() {
  header "Google Cloud"
  create_or_skip "Test GCP - us-central1" "{
    \"name\": \"Test GCP - us-central1\",
    \"infrastructure\": \"public_cloud\",
    \"vendor\": \"google\",
    \"provider_type\": \"gce\",
    \"endpoint\": \"https://compute.googleapis.com\",
    \"credential_ref\": \"aap-credential://gcp-test\",
    \"enabled\": true,
    \"organization\": \"${ORG_ID}\",
    \"connection_config\": {
      \"region\": \"us-central1\"
    }
  }"
  echo "  Seeding GCP resource data..."
  run_manage "seed_multivendor_data --vendor gcp" && ok "seed_multivendor_data --vendor gcp complete" || err "seed_multivendor_data --vendor gcp failed"
}

seed_openstack() {
  header "OpenStack"
  create_or_skip "Test OpenStack - RegionOne" "{
    \"name\": \"Test OpenStack - RegionOne\",
    \"infrastructure\": \"private_cloud\",
    \"vendor\": \"openstack\",
    \"provider_type\": \"openstack\",
    \"endpoint\": \"https://openstack.test.local:5000/v3\",
    \"credential_ref\": \"aap-credential://openstack-test\",
    \"enabled\": true,
    \"organization\": \"${ORG_ID}\",
    \"connection_config\": {
      \"region\": \"RegionOne\"
    }
  }"
  echo "  Seeding OpenStack resource data..."
  run_manage "seed_multivendor_data --vendor openstack" && ok "seed_multivendor_data --vendor openstack complete" || err "seed_multivendor_data --vendor openstack failed"
}

seed_openshift() {
  header "OpenShift"
  create_or_skip "Test OpenShift - cluster-01" "{
    \"name\": \"Test OpenShift - cluster-01\",
    \"infrastructure\": \"on_premise\",
    \"vendor\": \"redhat\",
    \"provider_type\": \"openshift\",
    \"endpoint\": \"https://api.cluster-01.test.local:6443\",
    \"credential_ref\": \"aap-credential://openshift-test\",
    \"enabled\": true,
    \"organization\": \"${ORG_ID}\",
    \"connection_config\": {
      \"validate_certs\": false
    }
  }"
  echo "  Seeding OpenShift resource data..."
  run_manage "seed_multivendor_data --vendor openshift" && ok "seed_multivendor_data --vendor openshift complete" || err "seed_multivendor_data --vendor openshift failed"
}

# ── Dispatch ──────────────────────────────────────────────────────────────────

case "$VENDOR" in
  vmware)    seed_vmware ;;
  aws)       seed_aws ;;
  azure)     seed_azure ;;
  gcp)       seed_gcp ;;
  openstack) seed_openstack ;;
  openshift) seed_openshift ;;
  all)
    seed_vmware
    seed_aws
    seed_azure
    seed_gcp
    seed_openstack
    seed_openshift
    ;;
esac

echo -e "\nDone. Run ./test_api.sh to verify."
