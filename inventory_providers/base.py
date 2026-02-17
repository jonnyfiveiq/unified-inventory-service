"""Base classes and data contracts for inventory providers.

This module defines the provider plugin interface. It is intentionally
free of Django dependencies so that provider authors — including external
partners — can develop and test providers without installing the full
inventory service.

Provider authors subclass ``BaseProvider`` and implement three methods:
    - ``connect()``     — establish connection to the target system
    - ``disconnect()``  — tear down the connection
    - ``collect()``     — yield ``ResourceData`` for each discovered resource

The inventory service's collector layer handles all Django ORM operations
(upserting resources, creating sightings, managing relationships).
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterator

logger = logging.getLogger("inventory_providers")


# ── Data contracts ────────────────────────────────────────────────────


@dataclass
class ProviderCredential:
    """
    Resolved credentials for connecting to a provider.

    Providers receive this instead of raw connection config so that
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
    service. Providers fill in what they can; the collector layer in
    the inventory service handles mapping to Django models.

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

    # === Relationships ===
    relationships: list[dict[str, str]] = field(default_factory=list)
    """
    List of relationships this resource has to other resources.
    Each entry is a dict with:
        - ``target_ems_ref``: the ems_ref of the target resource
        - ``relationship_type``: e.g. 'runs_on', 'part_of', 'attached_to'

    Example::

        relationships=[
            {"target_ems_ref": "host-101", "relationship_type": "runs_on"},
            {"target_ems_ref": "datastore-501", "relationship_type": "attached_to"},
        ]
    """

    # === Metrics snapshot (for sighting) ===
    metrics: dict[str, Any] = field(default_factory=dict)
    """
    Point-in-time metrics captured during collection.
    Stored in the ResourceSighting record. Examples:
        {"cpu_usage_pct": 45.2, "memory_usage_pct": 72.1}
    """


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


# ── Abstract base provider ───────────────────────────────────────────


class BaseProvider(ABC):
    """
    Abstract base class for inventory collection providers.

    Subclasses must set these class attributes:
        - ``vendor``                   e.g. 'vmware', 'aws', 'cisco'
        - ``provider_type``            e.g. 'vcenter', 'ec2', 'nxos'
        - ``supported_resource_types`` list of taxonomy slugs this provider collects

    Subclasses must implement:
        - ``connect()``    — establish connection to the target system
        - ``disconnect()`` — tear down the connection
        - ``collect()``    — yield ResourceData for each discovered resource

    Optional overrides:
        - ``validate_connection()`` — quick connectivity test
        - ``display_name``         — human-readable name for UI

    Example::

        class MyCloudProvider(BaseProvider):
            vendor = "mycloud"
            provider_type = "api"
            display_name = "My Cloud Platform"
            supported_resource_types = ["virtual_machine", "block_storage"]

            def connect(self):
                self.client = MyCloudSDK(
                    host=self.credential.hostname,
                    token=self.credential.password,
                )

            def disconnect(self):
                self.client.close()

            def collect(self):
                for vm in self.client.list_vms():
                    yield ResourceData(
                        ems_ref=vm.id,
                        resource_type_slug="virtual_machine",
                        name=vm.name,
                        state="running" if vm.active else "stopped",
                        cpu_count=vm.cpus,
                        memory_mb=vm.ram_mb,
                    )
    """

    # ── Subclass must set these ───────────────────────────────────────
    vendor: str = ""
    provider_type: str = ""
    display_name: str = ""
    supported_resource_types: list[str] = []

    def __init__(self, provider_model: Any, credential: ProviderCredential):
        """
        Args:
            provider_model: The Provider record from the inventory service.
                This is opaque to the provider — used only for identity
                (name, endpoint) and passed through to the collector layer.
            credential: Resolved credentials for this provider.
        """
        self.provider = provider_model
        self.credential = credential
        self.logger = logging.getLogger(
            f"inventory_providers.{self.vendor}.{self.provider_type}"
        )

    # ── Abstract interface ────────────────────────────────────────────

    @abstractmethod
    def connect(self) -> None:
        """Establish a connection to the external system.

        Raise on failure — the collector layer will catch and record
        the error on the CollectionRun.
        """
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Cleanly tear down the connection.

        Must not raise — log errors internally.
        """
        ...

    @abstractmethod
    def collect(self) -> Iterator[ResourceData]:
        """
        Yield ResourceData for every resource discovered in this provider.

        Implementations should:
        1. Query the external system for all supported resource types
        2. Normalize each resource into a ResourceData dataclass
        3. Yield each ResourceData (don't accumulate in memory)
        4. Set relationships via ResourceData.relationships

        The inventory service's collector layer handles all DB operations.
        """
        ...

    # ── Optional overrides ────────────────────────────────────────────

    def validate_connection(self) -> tuple[bool, str]:
        """
        Test connectivity without doing a full collection.

        Returns:
            (success: bool, message: str)
        """
        try:
            self.connect()
            self.disconnect()
            return True, "Connection successful"
        except Exception as exc:
            return False, str(exc)

    # ── Metadata ──────────────────────────────────────────────────────

    @classmethod
    def provider_key(cls) -> str:
        """Return the registry key for this provider class."""
        return f"{cls.vendor}:{cls.provider_type}"

    @classmethod
    def metadata(cls) -> dict[str, Any]:
        """Return a metadata dict describing this provider."""
        return {
            "key": cls.provider_key(),
            "vendor": cls.vendor,
            "provider_type": cls.provider_type,
            "display_name": cls.display_name or cls.provider_key(),
            "supported_resource_types": cls.supported_resource_types,
            "class": f"{cls.__module__}.{cls.__name__}",
        }
