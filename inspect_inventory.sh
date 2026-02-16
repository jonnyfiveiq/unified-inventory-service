#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# inspect_inventory.sh — Quick-look queries for the inventory service DB
# Usage: ./inspect_inventory.sh [db_path]
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

DB="${1:-db.sqlite3}"

if [ ! -f "$DB" ]; then
    echo "ERROR: Database file '$DB' not found."
    echo "Usage: $0 [path/to/db.sqlite3]"
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
    sqlite3 -header -column "$DB" "$1"
}

# ── 1. Overview ────────────────────────────────────────────────────────
banner "1. INVENTORY OVERVIEW"
sql "
SELECT
    (SELECT count(*) FROM inventory_provider)            AS providers,
    (SELECT count(*) FROM inventory_resource)            AS resources,
    (SELECT count(*) FROM inventory_resourcesighting)    AS sightings,
    (SELECT count(*) FROM inventory_resourcerelationship)AS relationships,
    (SELECT count(*) FROM inventory_collectionrun)       AS collection_runs,
    (SELECT count(*) FROM inventory_resourcetype)        AS resource_types,
    (SELECT count(*) FROM inventory_vendortypemapping)   AS vendor_mappings;
"

# ── 2. Providers ───────────────────────────────────────────────────────
banner "2. PROVIDERS"
sql "
SELECT
    p.name,
    p.vendor,
    p.infrastructure,
    p.provider_type,
    CASE p.enabled WHEN 1 THEN 'YES' ELSE 'NO' END AS enabled,
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
    group_concat(r.name, ', ') AS names
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
    json_extract(r.properties, '$.kubernetes_version') AS k8s_version,
    json_extract(r.properties, '$.node_count') AS nodes,
    r.region
FROM inventory_resource r
JOIN inventory_provider p ON r.provider_id = p.id
JOIN inventory_resourcetype rt ON r.resource_type_id = rt.id
WHERE rt.slug IN ('kubernetes_cluster', 'container_platform')
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
    json_extract(r.properties, '$.engine') AS engine,
    json_extract(r.properties, '$.multi_az') AS multi_az
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
    json_extract(r.properties, '$.cidr_block') AS cidr,
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
    min(s.seen_at) AS first_seen,
    max(s.seen_at) AS last_seen,
    group_concat(DISTINCT s.state) AS states_observed,
    CASE WHEN s.cpu_count IS NOT NULL
         THEN round(avg(json_extract(s.metrics, '$.cpu_usage_percent')), 1)
         ELSE NULL
    END AS avg_cpu_pct,
    CASE WHEN s.memory_mb IS NOT NULL
         THEN round(avg(json_extract(s.metrics, '$.memory_usage_percent')), 1)
         ELSE NULL
    END AS avg_mem_pct
FROM inventory_resource r
JOIN inventory_provider p ON r.provider_id = p.id
JOIN inventory_resourcesighting s ON s.resource_id = r.id
JOIN inventory_resourcetype rt ON r.resource_type_id = rt.id
WHERE rt.slug = 'virtual_machine'
GROUP BY r.id
ORDER BY p.vendor, r.name;
"

# ── 10. Identity tracking ───────────────────────────────────────────
banner "10. IDENTITY TRACKING (canonical_id + vendor_identifiers)"
sql "
SELECT
    r.name,
    p.vendor,
    substr(r.canonical_id, 1, 36) AS canonical_id,
    r.vendor_identifiers
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
    group_concat(DISTINCT vtm.vendor) AS vendors
FROM inventory_resourcetype rt
JOIN inventory_resourcecategory rc ON rt.category_id = rc.id
LEFT JOIN inventory_vendortypemapping vtm ON vtm.resource_type_id = rt.id
GROUP BY rt.id
ORDER BY rc.sort_order, rt.sort_order;
"

# ── 12. Cloud tenant distribution ────────────────────────────────────
banner "12. CLOUD TENANT DISTRIBUTION"
sql "
SELECT
    p.vendor,
    r.cloud_tenant,
    count(*) AS resources,
    group_concat(DISTINCT rt.slug) AS types
FROM inventory_resource r
JOIN inventory_provider p ON r.provider_id = p.id
JOIN inventory_resourcetype rt ON r.resource_type_id = rt.id
WHERE r.cloud_tenant != ''
GROUP BY p.vendor, r.cloud_tenant
ORDER BY p.vendor;
"

# ── 13. Quick health check ──────────────────────────────────────────
banner "13. HEALTH CHECK"
echo ""
ISSUES=0

# Check for resources without a provider
ORPHANS=$(sqlite3 "$DB" "SELECT count(*) FROM inventory_resource WHERE provider_id IS NULL")
if [ "$ORPHANS" -gt 0 ]; then
    echo -e "  ${YELLOW}⚠  $ORPHANS resource(s) without a provider${NC}"
    ISSUES=$((ISSUES+1))
else
    echo -e "  ${GREEN}✓  All resources linked to a provider${NC}"
fi

# Check for resources without sightings
NO_SIGHT=$(sqlite3 "$DB" "
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
BROKEN=$(sqlite3 "$DB" "
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
USED=$(sqlite3 "$DB" "SELECT count(DISTINCT resource_type_id) FROM inventory_resource")
TOTAL=$(sqlite3 "$DB" "SELECT count(*) FROM inventory_resourcetype")
echo -e "  ${GREEN}✓  $USED of $TOTAL resource types in use${NC}"

if [ "$ISSUES" -eq 0 ]; then
    echo ""
    echo -e "  ${GREEN}${BOLD}All checks passed.${NC}"
fi
echo ""
