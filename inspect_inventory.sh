#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# inspect_inventory.sh — Quick-look queries for the inventory service DB
# Usage: ./inspect_inventory.sh
#
# Modes (auto-detected, or force with INVENTORY_DB_MODE):
#   k8s   — port-forwards to aap26 namespace postgres (default if kubeconfig exists)
#   local — connects to podman-compose postgres on localhost:5532
#
# All env vars can still be overridden: DB_NAME DB_USER DB_PASS DB_HOST DB_PORT
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

KUBECONFIG_PATH="${KUBECONFIG:-$HOME/upstream/aap-dev/.tmp/26.kubeconfig}"
K8S_NAMESPACE="aap26"
K8S_STATEFULSET="inventory-service-postgres-15"
LOCAL_FWD_PORT=5532
PF_PID=""

cleanup() {
    if [ -n "$PF_PID" ] && kill -0 "$PF_PID" 2>/dev/null; then
        kill "$PF_PID" 2>/dev/null || true
        wait "$PF_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# --- Decide mode: k8s or local ---
MODE="${INVENTORY_DB_MODE:-auto}"
if [ "$MODE" = "auto" ]; then
    if [ -f "$KUBECONFIG_PATH" ]; then
        MODE="k8s"
    else
        MODE="local"
    fi
fi

if [ "$MODE" = "k8s" ]; then
    export KUBECONFIG="$KUBECONFIG_PATH"
    DB_NAME="${DB_NAME:-inventory_db}"
    DB_USER="${DB_USER:-inventory_svc}"
    DB_PASS="${DB_PASS:-helloSvcDevPass123456789abcdef}"
    DB_HOST="${DB_HOST:-localhost}"
    DB_PORT="${DB_PORT:-$LOCAL_FWD_PORT}"

    # Check if port is already forwarded
    if ! psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1" >/dev/null 2>&1; then
        echo "Setting up port-forward to $K8S_NAMESPACE/$K8S_STATEFULSET ..."
        kubectl port-forward -n "$K8S_NAMESPACE" "statefulset/$K8S_STATEFULSET" "${DB_PORT}:5432" >/dev/null 2>&1 &
        PF_PID=$!
        for i in $(seq 1 20); do
            if psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1" >/dev/null 2>&1; then
                break
            fi
            sleep 0.5
        done
    fi
else
    DB_NAME="${DB_NAME:-inventory_db}"
    DB_USER="${DB_USER:-inventory}"
    DB_PASS="${DB_PASS:-inventory123}"
    DB_HOST="${DB_HOST:-localhost}"
    DB_PORT="${DB_PORT:-5532}"
fi

export PGPASSWORD="$DB_PASS"

# Verify connectivity
if ! psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1" >/dev/null 2>&1; then
    echo "ERROR: Cannot connect to PostgreSQL at $DB_HOST:$DB_PORT/$DB_NAME (mode=$MODE)"
    if [ "$MODE" = "k8s" ]; then
        echo "  Is the cluster running?  Check: kubectl --kubeconfig=$KUBECONFIG_PATH get pods -n $K8S_NAMESPACE"
    else
        echo "  Is postgres running?  Try: make db-up"
    fi
    exit 1
fi
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

banner() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}  $1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

sql() {
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
         --pset=border=1 --pset=format=aligned --pset=null='(null)' \
         -c "$1"
}

sqlv() {
    # For single-value queries (health check)
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tA -c "$1"
}

# ── 1. Overview ────────────────────────────────────────────────────────
banner "1. INVENTORY OVERVIEW"
sql "
SELECT
    (SELECT count(*) FROM inventory_provider)             AS providers,
    (SELECT count(*) FROM inventory_resource)             AS resources,
    (SELECT count(*) FROM inventory_resourcesighting)     AS sightings,
    (SELECT count(*) FROM inventory_resourcerelationship) AS relationships,
    (SELECT count(*) FROM inventory_collectionrun)        AS collection_runs,
    (SELECT count(*) FROM inventory_resourcetype)         AS resource_types,
    (SELECT count(*) FROM inventory_vendortypemapping)    AS vendor_mappings;
"

# ── 2. Providers ───────────────────────────────────────────────────────
banner "2. PROVIDERS"
sql "
SELECT
    p.name,
    p.vendor,
    p.infrastructure,
    p.provider_type,
    CASE p.enabled WHEN true THEN 'YES' ELSE 'NO' END AS enabled,
    (SELECT count(*) FROM inventory_resource r WHERE r.provider_id = p.id) AS resources,
    (SELECT count(*) FROM inventory_collectionrun cr WHERE cr.provider_id = p.id) AS runs
FROM inventory_provider p
ORDER BY p.vendor;
"

# ── 3. Resources per vendor ───────────────────────────────────────────
banner "3. RESOURCES BY VENDOR"
sql "
SELECT
    p.vendor,
    rt.slug AS resource_type,
    count(*) AS count,
    string_agg(r.name, ', ' ORDER BY r.name) AS names
FROM inventory_resource r
JOIN inventory_provider p ON r.provider_id = p.id
JOIN inventory_resourcetype rt ON r.resource_type_id = rt.id
GROUP BY p.vendor, rt.slug
ORDER BY p.vendor, rt.slug;
"

# ── 4. Compute resources detail ──────────────────────────────────────
banner "4. COMPUTE RESOURCES (VMs / Instances / Nodes)"
sql "
SELECT
    r.name,
    p.vendor,
    r.vendor_type,
    r.state,
    r.power_state,
    r.flavor,
    r.cpu_count || ' vCPU' AS cpu,
    CASE
        WHEN r.memory_mb >= 1024 THEN (r.memory_mb / 1024) || ' GB'
        ELSE r.memory_mb || ' MB'
    END AS memory,
    r.os_name,
    r.region,
    r.cloud_tenant
FROM inventory_resource r
JOIN inventory_provider p ON r.provider_id = p.id
JOIN inventory_resourcetype rt ON r.resource_type_id = rt.id
WHERE rt.slug IN ('virtual_machine', 'physical_server')
ORDER BY p.vendor, r.name;
"

# ── 5. Kubernetes / container platforms ──────────────────────────────
banner "5. KUBERNETES & CONTAINER PLATFORMS"
sql "
SELECT
    r.name,
    p.vendor,
    r.vendor_type,
    r.state,
    r.properties->>'kubernetes_version' AS k8s_version,
    r.properties->>'node_count'         AS nodes,
    r.region
FROM inventory_resource r
JOIN inventory_provider p ON r.provider_id = p.id
JOIN inventory_resourcetype rt ON r.resource_type_id = rt.id
WHERE rt.slug IN ('kubernetes_cluster', 'container_orchestration_platform')
ORDER BY p.vendor;
"

# ── 6. Storage & databases ──────────────────────────────────────────
banner "6. STORAGE & DATABASES"
sql "
SELECT
    r.name,
    p.vendor,
    r.vendor_type,
    rt.slug AS type,
    r.state,
    CASE WHEN r.disk_gb IS NOT NULL THEN r.disk_gb || ' GB' ELSE '-' END AS size,
    r.properties->>'engine'   AS engine,
    r.properties->>'multi_az' AS multi_az
FROM inventory_resource r
JOIN inventory_provider p ON r.provider_id = p.id
JOIN inventory_resourcetype rt ON r.resource_type_id = rt.id
WHERE rt.slug IN ('block_storage', 'object_storage', 'relational_db')
ORDER BY p.vendor, rt.slug;
"

# ── 7. Networking ────────────────────────────────────────────────────
banner "7. NETWORKING"
sql "
SELECT
    r.name,
    p.vendor,
    r.vendor_type,
    r.state,
    r.properties->>'cidr_block' AS cidr,
    r.region
FROM inventory_resource r
JOIN inventory_provider p ON r.provider_id = p.id
JOIN inventory_resourcetype rt ON r.resource_type_id = rt.id
WHERE rt.slug IN ('vpc', 'security_group', 'load_balancer')
ORDER BY p.vendor, rt.slug;
"

# ── 8. Relationships ────────────────────────────────────────────────
banner "8. RESOURCE RELATIONSHIPS"
sql "
SELECT
    src.name AS source,
    rel.relationship_type AS relationship,
    tgt.name AS target,
    p.vendor
FROM inventory_resourcerelationship rel
JOIN inventory_resource src ON rel.source_id = src.id
JOIN inventory_resource tgt ON rel.target_id = tgt.id
JOIN inventory_provider p ON src.provider_id = p.id
ORDER BY p.vendor, rel.relationship_type;
"

# ── 9. Sighting history summary ─────────────────────────────────────
banner "9. SIGHTING HISTORY (per resource)"
sql "
SELECT
    r.name,
    p.vendor,
    count(s.id) AS sightings,
    min(s.seen_at)::date AS first_seen,
    max(s.seen_at)::date AS last_seen,
    string_agg(DISTINCT s.state, ', ') AS states_observed,
    round(avg((s.metrics->>'cpu_usage_percent')::numeric), 1) AS avg_cpu_pct,
    round(avg((s.metrics->>'memory_usage_percent')::numeric), 1) AS avg_mem_pct
FROM inventory_resource r
JOIN inventory_provider p ON r.provider_id = p.id
JOIN inventory_resourcesighting s ON s.resource_id = r.id
JOIN inventory_resourcetype rt ON r.resource_type_id = rt.id
WHERE rt.slug = 'virtual_machine'
GROUP BY r.id, r.name, p.vendor
ORDER BY p.vendor, r.name;
"

# ── 10. Identity tracking ───────────────────────────────────────────
banner "10. IDENTITY TRACKING (canonical_id + vendor_identifiers)"
sql "
SELECT
    r.name,
    p.vendor,
    r.canonical_id::text AS canonical_id,
    r.vendor_identifiers::text AS vendor_identifiers
FROM inventory_resource r
JOIN inventory_provider p ON r.provider_id = p.id
JOIN inventory_resourcetype rt ON r.resource_type_id = rt.id
WHERE rt.slug = 'virtual_machine'
ORDER BY p.vendor, r.name;
"

# ── 11. Taxonomy coverage ───────────────────────────────────────────
banner "11. TAXONOMY: Resource types with vendor mappings"
sql "
SELECT
    rc.name AS category,
    rt.slug,
    rt.name AS type_name,
    count(vtm.id) AS vendor_mappings,
    string_agg(DISTINCT vtm.vendor, ', ' ORDER BY vtm.vendor) AS vendors
FROM inventory_resourcetype rt
JOIN inventory_resourcecategory rc ON rt.category_id = rc.id
LEFT JOIN inventory_vendortypemapping vtm ON vtm.resource_type_id = rt.id
GROUP BY rt.id, rc.name, rt.slug, rt.name, rc.sort_order, rt.sort_order
ORDER BY rc.sort_order, rt.sort_order;
"

# ── 12. Cloud tenant distribution ────────────────────────────────────
banner "12. CLOUD TENANT DISTRIBUTION"
sql "
SELECT
    p.vendor,
    r.cloud_tenant,
    count(*) AS resources,
    string_agg(DISTINCT rt.slug, ', ') AS types
FROM inventory_resource r
JOIN inventory_provider p ON r.provider_id = p.id
JOIN inventory_resourcetype rt ON r.resource_type_id = rt.id
WHERE r.cloud_tenant IS NOT NULL AND r.cloud_tenant != ''
GROUP BY p.vendor, r.cloud_tenant
ORDER BY p.vendor;
"

# ── 13. Quick health check ──────────────────────────────────────────
banner "13. HEALTH CHECK"
echo ""
ISSUES=0

# Check for resources without a provider
ORPHANS=$(sqlv "SELECT count(*) FROM inventory_resource WHERE provider_id IS NULL")
if [ "$ORPHANS" -gt 0 ]; then
    echo -e "  ${YELLOW}⚠  $ORPHANS resource(s) without a provider${NC}"
    ISSUES=$((ISSUES+1))
else
    echo -e "  ${GREEN}✓  All resources linked to a provider${NC}"
fi

# Check for resources without sightings
NO_SIGHT=$(sqlv "
    SELECT count(*) FROM inventory_resource r
    WHERE NOT EXISTS (SELECT 1 FROM inventory_resourcesighting s WHERE s.resource_id = r.id)
")
if [ "$NO_SIGHT" -gt 0 ]; then
    echo -e "  ${YELLOW}⚠  $NO_SIGHT resource(s) with no sightings${NC}"
    ISSUES=$((ISSUES+1))
else
    echo -e "  ${GREEN}✓  All resources have sighting history${NC}"
fi

# Check for broken relationships
BROKEN=$(sqlv "
    SELECT count(*) FROM inventory_resourcerelationship rel
    WHERE NOT EXISTS (SELECT 1 FROM inventory_resource WHERE id = rel.source_id)
       OR NOT EXISTS (SELECT 1 FROM inventory_resource WHERE id = rel.target_id)
")
if [ "$BROKEN" -gt 0 ]; then
    echo -e "  ${YELLOW}⚠  $BROKEN broken relationship(s)${NC}"
    ISSUES=$((ISSUES+1))
else
    echo -e "  ${GREEN}✓  All relationships valid${NC}"
fi

# Check resource types used vs available
USED=$(sqlv "SELECT count(DISTINCT resource_type_id) FROM inventory_resource")
TOTAL=$(sqlv "SELECT count(*) FROM inventory_resourcetype")
echo -e "  ${GREEN}✓  $USED of $TOTAL resource types in use${NC}"

# Database size
DB_SIZE=$(sqlv "SELECT pg_size_pretty(pg_database_size(current_database()))")
echo -e "  ${GREEN}✓  Database size: $DB_SIZE${NC}"

if [ "$ISSUES" -eq 0 ]; then
    echo ""
    echo -e "  ${GREEN}${BOLD}All checks passed.${NC}"
fi
echo ""
