"""Abstract base class for inventory collection providers.

Every provider plugin — whether built-in or loaded externally — must
subclass ``BaseProvider`` and implement the required methods. The base
class handles the lifecycle boilerplate (CollectionRun tracking, error
handling, resource upserting) so that concrete providers only need to
worry about connecting to their target system and yielding normalized
resource data.

Design principles:
    - Providers are stateless between collection runs
    - Connection credentials come from Provider.credential_ref +
      Provider.connection_config, never hardcoded
    - Providers yield ResourceData dicts; the base class handles DB writes
    - Providers declare which resource types they support so the registry
      can validate configuration at load time
"""
from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterator

from django.utils import timezone

logger = logging.getLogger("apps.inventory.providers")


@dataclass
class ProviderCredential:
    """
    Resolved credentials for connecting to a provider.

    Providers receive this instead of raw connection_config so that
    credential resolution (AAP vault, external secret store, etc.)
    happens once in the framework layer.
    """
    username: str = ""
    password: str = ""
    hostname: str = ""
    port: int = 443
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResourceData:
    """
    Normalized resource data yielded by a provider during collection.

    This is the contract between provider plugins and the inventory
    service. Providers fill in what they can; the base class handles
    mapping to the Resource model.

    The only required fields are ``ems_ref`` and ``resource_type_slug``.
    Everything else is optional and will use model defaults if omitted.
    """
    # === Required ===
    ems_ref: str
    resource_type_slug: str

    # === Identity ===
    name: str = ""
    description: str = ""
    canonical_id: str = ""
    vendor_identifiers: dict[str, str] = field(default_factory=dict)
    vendor_type: str = ""

    # === State ===
    state: str = "unknown"
    power_state: str = ""
    boot_time: datetime | None = None

    # === Location ===
    region: str = ""
    availability_zone: str = ""
    cloud_tenant: str = ""

    # === Compute ===
    flavor: str = ""
    cpu_count: int | None = None
    memory_mb: int | None = None
    disk_gb: int | None = None

    # === Network ===
    ip_addresses: list[str] = field(default_factory=list)
    fqdn: str = ""
    mac_addresses: list[str] = field(default_factory=list)

    # === OS ===
    os_type: str = ""
    os_name: str = ""

    # === Flexible properties (JSONB) ===
    properties: dict[str, Any] = field(default_factory=dict)
    provider_tags: dict[str, str] = field(default_factory=dict)

    # === Ansible metadata ===
    ansible_host: str = ""
    ansible_connection: str = ""
    inventory_group: str = ""

    # === Provider-side timestamps ===
    ems_created_on: datetime | None = None

    # === Relationships (source_ems_ref -> relationship_type) ===
    relationships: list[dict[str, str]] = field(default_factory=list)


@dataclass
class CollectionResult:
    """Summary statistics returned after a collection run."""
    found: int = 0
    created: int = 0
    updated: int = 0
    removed: int = 0
    unchanged: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "found": self.found,
            "created": self.created,
            "updated": self.updated,
            "removed": self.removed,
            "unchanged": self.unchanged,
            "errors": self.errors,
        }


class BaseProvider(ABC):
    """
    Abstract base class for inventory collection providers.

    Subclasses must implement:
        - ``vendor``                 class attribute (e.g. 'vmware')
        - ``provider_type``          class attribute (e.g. 'vcenter')
        - ``supported_resource_types`` class attribute
        - ``connect()``              establish connection to the target system
        - ``disconnect()``           tear down the connection
        - ``collect()``              yield ResourceData for each discovered resource

    The base class provides:
        - ``run_collection()``       full lifecycle: connect -> collect -> upsert -> disconnect
        - ``upsert_resource()``      create-or-update a Resource from ResourceData
        - ``mark_stale_resources()`` handle resources that disappeared between runs
    """

    # -- Subclass must set these -----------------------------------------
    vendor: str = ""
    provider_type: str = ""
    display_name: str = ""
    supported_resource_types: list[str] = []

    def __init__(self, provider_model, credential: ProviderCredential):
        """
        Args:
            provider_model: The Provider Django model instance.
            credential: Resolved credentials for this provider.
        """
        self.provider = provider_model
        self.credential = credential
        self.logger = logging.getLogger(
            f"apps.inventory.providers.{self.vendor}.{self.provider_type}"
        )

    # -- Abstract interface ------------------------------------------------

    @abstractmethod
    def connect(self) -> None:
        """Establish a connection to the external system."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Cleanly tear down the connection."""
        ...

    @abstractmethod
    def collect(self) -> Iterator[ResourceData]:
        """
        Yield ResourceData for every resource discovered in this provider.

        This is the main collection method. Implementations should:
        1. Query the external system for all supported resource types
        2. Normalize each resource into a ResourceData dataclass
        3. Yield each ResourceData (don't accumulate in memory)
        4. Set relationships via ResourceData.relationships

        The framework handles all DB operations.
        """
        ...

    def validate_connection(self) -> tuple[bool, str]:
        """
        Optional: test the connection without doing a full collection.
        Returns (success, message).
        """
        try:
            self.connect()
            self.disconnect()
            return True, "Connection successful"
        except Exception as exc:
            return False, str(exc)

    # -- Framework methods (used by tasks.py) ---------------------------

    def run_collection(self, collection_run) -> CollectionResult:
        """
        Execute a full collection lifecycle.

        This is called by the dispatcherd task. It:
        1. Connects to the provider
        2. Iterates over collect(), upserting each resource
        3. Marks stale resources (present in DB but not seen this run)
        4. Creates ResourceSightings for all seen resources
        5. Disconnects

        Args:
            collection_run: The CollectionRun model instance tracking this run.

        Returns:
            CollectionResult with statistics.
        """
        from apps.inventory.models import (
            Resource, ResourceRelationship, ResourceSighting, ResourceType,
        )

        result = CollectionResult()
        seen_ems_refs: set[str] = set()
        resource_map: dict[str, Resource] = {}  # ems_ref -> Resource for relationships

        # Cache resource type lookups
        type_cache: dict[str, ResourceType] = {}

        try:
            self.logger.info("Connecting to %s (%s)", self.provider.name, self.provider.endpoint)
            self.connect()

            for resource_data in self.collect():
                try:
                    resource, created = self._upsert_resource(
                        resource_data, collection_run, type_cache
                    )
                    seen_ems_refs.add(resource_data.ems_ref)
                    resource_map[resource_data.ems_ref] = resource
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
                        metrics=resource_data.properties.get("_metrics", {}),
                    )

                except Exception as exc:
                    result.errors.append(f"{resource_data.ems_ref}: {exc}")
                    self.logger.exception("Error upserting resource %s", resource_data.ems_ref)

            # Build relationships (second pass)
            self._build_relationships(resource_map, collection_run)

            # Mark stale resources
            result.removed = self._mark_stale(seen_ems_refs, collection_run)
            result.unchanged = max(0, result.found - result.created - result.removed)

        finally:
            try:
                self.disconnect()
            except Exception:
                self.logger.exception("Error disconnecting from %s", self.provider.name)

        # Update provider's last refresh timestamp
        self.provider.last_refresh_at = timezone.now()
        self.provider.save(update_fields=["last_refresh_at"])

        return result

    def _upsert_resource(self, data: ResourceData, collection_run, type_cache) -> tuple:
        """Create or update a Resource from a ResourceData."""
        from apps.inventory.models import Resource, ResourceType

        # Resolve resource type
        if data.resource_type_slug not in type_cache:
            try:
                type_cache[data.resource_type_slug] = ResourceType.objects.get(
                    slug=data.resource_type_slug
                )
            except ResourceType.DoesNotExist:
                raise ValueError(
                    f"ResourceType '{data.resource_type_slug}' not found in taxonomy. "
                    f"Run seed_taxonomy management command first."
                )

        resource_type = type_cache[data.resource_type_slug]

        # Store relationships in properties temporarily for second pass
        props = dict(data.properties)
        if data.relationships:
            props["_relationships"] = data.relationships

        defaults = {
            "name": data.name or data.ems_ref,
            "description": data.description,
            "resource_type": resource_type,
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
            "properties": props,
            "provider_tags": data.provider_tags,
            "ansible_host": data.ansible_host,
            "ansible_connection": data.ansible_connection,
            "inventory_group": data.inventory_group,
            "ems_created_on": data.ems_created_on,
            "last_seen_at": timezone.now(),
        }

        resource, created = Resource.objects.update_or_create(
            provider=self.provider,
            ems_ref=data.ems_ref,
            defaults=defaults,
        )

        if not created:
            resource.seen_count = (resource.seen_count or 0) + 1
            resource.save(update_fields=["seen_count"])

        return resource, created

    def _build_relationships(self, resource_map, collection_run):
        """
        Build ResourceRelationship records from collected data.

        Provider implementations store relationship info in
        ResourceData.relationships as:
            [{"target_ems_ref": "...", "relationship_type": "runs_on"}, ...]
        """
        from apps.inventory.models import ResourceRelationship

        # Clear existing relationships for this provider's resources
        ResourceRelationship.objects.filter(
            source__provider=self.provider
        ).delete()

        for ems_ref, resource in resource_map.items():
            # Relationships were stored in properties under _relationships
            rels = resource.properties.pop("_relationships", [])
            if rels:
                resource.save(update_fields=["properties"])
            for rel in rels:
                target_ref = rel.get("target_ems_ref", "")
                rel_type = rel.get("relationship_type", "")
                if target_ref in resource_map and rel_type:
                    ResourceRelationship.objects.get_or_create(
                        source=resource,
                        target=resource_map[target_ref],
                        relationship_type=rel_type,
                    )

    def _mark_stale(self, seen_ems_refs: set[str], collection_run) -> int:
        """
        Mark resources that exist in the DB but weren't seen in this run.

        For now, sets state to 'unknown'. Could be made configurable
        (e.g. mark as decommissioned after N missed runs).
        """
        from apps.inventory.models import Resource

        stale = Resource.objects.filter(
            provider=self.provider,
        ).exclude(
            ems_ref__in=seen_ems_refs,
        ).exclude(
            state="decommissioned",
        )

        count = stale.update(state="unknown")
        if count:
            self.logger.info("Marked %d stale resources as unknown", count)
        return count
