"""Collector — Django integration layer for inventory providers.

This module bridges the external ``inventory_providers`` package (which
has no Django dependency) with the inventory service's Django ORM models.

It handles:
    - Credential resolution from Provider model → ProviderCredential
    - Upserting Resource records from ResourceData
    - Creating ResourceSightings
    - Building ResourceRelationships
    - Marking stale resources
    - Registry initialization with Django settings filters

Provider plugins never import Django — they yield ``ResourceData`` and
this module does all the database work.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.db.models import F
from django.utils import timezone

from inventory_providers import (
    BaseProvider,
    CollectionResult,
    ProviderCredential,
    ResourceData,
    registry,
)

logger = logging.getLogger("apps.inventory.collector")

_registry_initialized = False


# ── Registry setup ────────────────────────────────────────────────────


def get_registry():
    """
    Return the provider registry, applying Django settings filters on first call.

    Ensures ``plugins_dir`` is set before discovery so that file-based
    plugins (uploaded via the provider-plugins API) are found even when
    this function is called from a management command or worker process
    that may not have run the full ``InventoryConfig.ready()`` path.

    Settings:
        INVENTORY_PROVIDERS_ENABLED:  list of 'vendor:type' keys to whitelist
        INVENTORY_PROVIDERS_DISABLED: list of 'vendor:type' keys to blacklist
    """
    global _registry_initialized
    if not _registry_initialized:
        # Ensure plugins_dir is set before discovery -- apps.py sets this
        # at startup, but worker processes and management commands may
        # reach here before ready() has run.
        if registry.plugins_dir is None:
            from pathlib import Path
            plugins_dir = Path(getattr(settings, "PLUGINS_DIR", settings.BASE_DIR / "plugins"))
            if plugins_dir.is_dir():
                registry.plugins_dir = plugins_dir
                logger.info("get_registry: set plugins_dir=%s", plugins_dir)

        # Ensure plugin .deps are importable (pip deps installed during upload)
        import sys
        if registry.plugins_dir:
            deps_dir = registry.plugins_dir / ".deps"
            if deps_dir.is_dir():
                deps_str = str(deps_dir)
                if deps_str not in sys.path:
                    sys.path.insert(0, deps_str)

        registry.discover()
        registry.apply_filter(
            enabled=getattr(settings, "INVENTORY_PROVIDERS_ENABLED", None),
            disabled=getattr(settings, "INVENTORY_PROVIDERS_DISABLED", None),
        )
        _registry_initialized = True
    return registry

# ── Credential resolution ─────────────────────────────────────────────


def resolve_credential(provider_model) -> ProviderCredential:
    """
    Build a ProviderCredential from a Provider model instance.

    Parses the endpoint URL and connection_config into a flat credential
    object that provider plugins can use without knowing about Django.

    In production this would call out to AAP's credential store or an
    external vault via credential_ref. For now, reads directly from
    the model's connection_config.
    """
    config = provider_model.connection_config or {}

    # Parse endpoint for hostname / port
    hostname = provider_model.endpoint
    port = config.get("port", 443)

    # Strip protocol prefix
    for prefix in ("https://", "http://"):
        if hostname.startswith(prefix):
            hostname = hostname[len(prefix):]
            break

    # Strip trailing path
    if "/" in hostname:
        hostname = hostname.split("/")[0]

    # Handle host:port in endpoint
    if ":" in hostname:
        parts = hostname.rsplit(":", 1)
        hostname = parts[0]
        try:
            port = int(parts[1])
        except ValueError:
            pass

    return ProviderCredential(
        username=config.get("username", ""),
        password=config.get("password", ""),
        hostname=hostname,
        port=port,
        extra={k: v for k, v in config.items()
               if k not in ("username", "password", "port")},
    )


# ── Collection execution ─────────────────────────────────────────────


def run_collection(collection_run) -> CollectionResult:
    """
    Execute a full inventory collection for a CollectionRun.

    This is the main entry point called by the dispatcherd task. It:
    1. Resolves credentials
    2. Instantiates the provider plugin
    3. Connects, collects, and disconnects
    4. Upserts resources, creates sightings, builds relationships
    5. Marks stale resources

    Args:
        collection_run: The CollectionRun model instance.

    Returns:
        CollectionResult with statistics.
    """
    from apps.inventory.models import (
        Resource,
        ResourceRelationship,
        ResourceSighting,
        ResourceType,
    )

    provider_model = collection_run.provider
    reg = get_registry()

    logger.info(
        "Collecting from provider=%s vendor=%s type=%s endpoint=%s",
        provider_model.name,
        provider_model.vendor,
        provider_model.provider_type,
        provider_model.endpoint,
    )

    # Resolve credentials and instantiate the plugin
    credential = resolve_credential(provider_model)
    provider_instance = reg.instantiate(provider_model, credential)

    # Update collection run metadata
    collection_run.collector_version = getattr(provider_instance, "__version__", "0.1.0")
    collection_run.save(update_fields=["collector_version"])

    result = CollectionResult()
    seen_ems_refs: set[str] = set()
    resource_map: dict[str, Resource] = {}
    type_cache: dict[str, ResourceType] = {}

    try:
        logger.info("Connecting to %s (%s)", provider_model.name, provider_model.endpoint)
        provider_instance.connect()

        for resource_data in provider_instance.collect():
            try:
                resource, created = _upsert_resource(
                    provider_model, resource_data, collection_run, type_cache
                )
                seen_ems_refs.add(resource_data.ems_ref)
                resource_map[resource_data.ems_ref] = (resource, resource_data)
                result.found += 1

                if created:
                    result.created += 1
                else:
                    result.updated += 1

                # Create sighting
                ResourceSighting.objects.create(
                    resource=resource,
                    collection_run=collection_run,
                    state=resource.state,
                    power_state=resource.power_state or "",
                    cpu_count=resource.cpu_count,
                    memory_mb=resource.memory_mb,
                    disk_gb=resource.disk_gb,
                    metrics=resource_data.metrics,
                )

            except Exception as exc:
                result.errors.append(f"{resource_data.ems_ref}: {exc}")
                logger.exception("Error upserting resource %s", resource_data.ems_ref)

        # Build relationships
        _build_relationships(provider_model, resource_map)

        # Mark stale
        result.removed = _mark_stale(provider_model, seen_ems_refs)
        result.unchanged = max(0, result.found - result.created - result.removed)

    finally:
        try:
            provider_instance.disconnect()
        except Exception:
            logger.exception("Error disconnecting from %s", provider_model.name)

    # Update provider's last refresh
    provider_model.last_refresh_at = timezone.now()
    provider_model.save(update_fields=["last_refresh_at"])

    return result


# ── ORM helpers (private) ─────────────────────────────────────────────


def _upsert_resource(provider_model, data: ResourceData, collection_run, type_cache):
    """Create or update a Resource from a ResourceData."""
    from apps.inventory.models import Resource, ResourceType

    if data.resource_type_slug not in type_cache:
        try:
            type_cache[data.resource_type_slug] = ResourceType.objects.get(
                slug=data.resource_type_slug
            )
        except ResourceType.DoesNotExist:
            raise ValueError(
                f"ResourceType '{data.resource_type_slug}' not found in taxonomy. "
                f"Run migrations or seed the taxonomy first."
            )

    resource_type = type_cache[data.resource_type_slug]

    defaults = {
        "resource_type": resource_type,
        "name": data.name or data.ems_ref,
        "description": data.description,
        "canonical_id": data.canonical_id,
        "vendor_identifiers": data.vendor_identifiers,
        "vendor_type": data.vendor_type,
        "state": data.state,
        "power_state": data.power_state,
        "boot_time": data.boot_time,
        "region": data.region,
        "availability_zone": data.availability_zone,
        "cloud_tenant": data.cloud_tenant,
        "flavor": data.flavor,
        "cpu_count": data.cpu_count,
        "memory_mb": data.memory_mb,
        "disk_gb": data.disk_gb,
        "ip_addresses": data.ip_addresses,
        "fqdn": data.fqdn,
        "mac_addresses": data.mac_addresses,
        "os_type": data.os_type,
        "os_name": data.os_name,
        "properties": data.properties,
        "provider_tags": data.provider_tags,
        "ansible_host": data.ansible_host,
        "ansible_connection": data.ansible_connection,
        "inventory_group": data.inventory_group,
        "ems_created_on": data.ems_created_on,
        "collection_run": collection_run,
        "organization": provider_model.organization,
    }

    resource, created = Resource.objects.update_or_create(
        provider=provider_model,
        ems_ref=data.ems_ref,
        defaults=defaults,
    )

    if not created:
        Resource.objects.filter(pk=resource.pk).update(seen_count=F("seen_count") + 1)

    return resource, created


def _build_relationships(provider_model, resource_map: dict) -> None:
    """Build ResourceRelationships from collected data."""
    from apps.inventory.models import ResourceRelationship

    # Clear existing relationships for this provider
    ResourceRelationship.objects.filter(source__provider=provider_model).delete()

    # resource_map: ems_ref → (Resource, ResourceData)
    ref_to_resource = {ref: resource for ref, (resource, _) in resource_map.items()}

    for ems_ref, (resource, resource_data) in resource_map.items():
        for rel in resource_data.relationships:
            target_ref = rel.get("target_ems_ref", "")
            rel_type = rel.get("relationship_type", "")
            if target_ref in ref_to_resource and rel_type:
                ResourceRelationship.objects.get_or_create(
                    source=resource,
                    target=ref_to_resource[target_ref],
                    relationship_type=rel_type,
                )


def _mark_stale(provider_model, seen_ems_refs: set[str]) -> int:
    """Mark resources not seen in this run as 'unknown'."""
    from apps.inventory.models import Resource

    stale = Resource.objects.filter(
        provider=provider_model,
    ).exclude(
        ems_ref__in=seen_ems_refs,
    ).exclude(
        state="decommissioned",
    )

    count = stale.update(state="unknown")
    if count:
        logger.info("Marked %d stale resources as unknown", count)
    return count
