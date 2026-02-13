"""
Resource model — the central normalized inventory record.

This is the Ansible equivalent of ManageIQ's entire VMDB approach, but
collapsed into a single polymorphic table with JSONB properties rather
than 200+ separate tables. The trade-off is simplicity and extensibility
over strict relational enforcement of every attribute.

Design rationale:
  ManageIQ uses STI with ~200 tables (vms, hosts, cloud_networks,
  security_groups, etc.) each with typed columns. This works for a mature
  product with known, stable schemas. For our use case — a new inventory
  service that needs to support an ever-growing taxonomy of resource types
  across dozens of vendors — a single Resource table with:
    1. Typed classification via resource_type FK (taxonomy-driven)
    2. Common columns for universally applicable attributes
    3. JSONB `properties` for type-specific and vendor-specific attributes
  gives us the flexibility to onboard new resource types without schema
  migrations while still supporting structured queries on common fields.

  The `properties` JSONB field uses GIN indexing for efficient queries.
  As patterns stabilize for high-value types (VMs, containers), dedicated
  columns or materialized views can be added without breaking the model.
"""

import uuid

from django.db import models


class ResourceState(models.TextChoices):
    """Normalized lifecycle state for any resource."""

    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    STOPPED = "stopped", "Stopped"
    RUNNING = "running", "Running"
    SUSPENDED = "suspended", "Suspended"
    TERMINATED = "terminated", "Terminated"
    ERROR = "error", "Error"
    UNKNOWN = "unknown", "Unknown"
    PROVISIONING = "provisioning", "Provisioning"
    DECOMMISSIONED = "decommissioned", "Decommissioned"


class Resource(models.Model):
    """
    A single normalized inventory resource.

    ManageIQ equivalents mapped to this model:
      MIQ VmOrTemplate  → Resource where resource_type.slug = 'virtual_machine'
      MIQ Host          → Resource where resource_type.slug = 'hypervisor_host'
      MIQ CloudNetwork  → Resource where resource_type.slug = 'vpc'
      MIQ CloudVolume   → Resource where resource_type.slug = 'block_storage'
      MIQ SecurityGroup → Resource where resource_type.slug = 'security_group'
      MIQ Container     → Resource where resource_type.slug = 'container'
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # === Classification (Taxonomy Levels 1-2 via FK chain) ===
    resource_type = models.ForeignKey(
        "inventory.ResourceType",
        on_delete=models.PROTECT,
        related_name="resources",
        help_text="Normalized resource type from the taxonomy.",
    )

    # === Provider linkage (ManageIQ: ems_id) ===
    provider = models.ForeignKey(
        "inventory.Provider",
        on_delete=models.CASCADE,
        related_name="resources",
        help_text="The provider this resource was collected from.",
    )

    # === Identity ===
    name = models.CharField(
        max_length=1024,
        help_text="Display name of the resource.",
    )
    ems_ref = models.CharField(
        max_length=1024,
        db_index=True,
        help_text="Provider-native unique reference (ManageIQ: ems_ref). "
        "E.g. AWS instance ID, vSphere MOID, Cisco serial number.",
    )

    # The vendor's own name for this resource type (before normalization)
    # e.g. "EC2 Instance", "vSphere Virtual Machine", "Nexus 9000"
    vendor_type = models.CharField(
        max_length=256,
        blank=True,
        default="",
        help_text="The vendor's native type name (pre-normalization).",
    )

    # === State & Lifecycle ===
    state = models.CharField(
        max_length=32,
        choices=ResourceState.choices,
        default=ResourceState.UNKNOWN,
        db_index=True,
        help_text="Normalized lifecycle state.",
    )
    power_state = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Power state for compute resources (on, off, suspended).",
    )

    # === Location / Topology ===
    region = models.CharField(
        max_length=128,
        blank=True,
        default="",
        db_index=True,
        help_text="Cloud region, datacenter, or site.",
    )
    availability_zone = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Availability zone or rack location.",
    )

    # === Common Compute Attributes (denormalized for high-value queries) ===
    # These are NULL for non-compute resources
    cpu_count = models.IntegerField(
        null=True,
        blank=True,
        help_text="Number of vCPUs / cores (compute resources only).",
    )
    memory_mb = models.IntegerField(
        null=True,
        blank=True,
        help_text="Memory in MB (compute resources only).",
    )
    disk_gb = models.IntegerField(
        null=True,
        blank=True,
        help_text="Total disk/storage in GB.",
    )

    # === Network Attributes (denormalized for high-value queries) ===
    ip_addresses = models.JSONField(
        default=list,
        blank=True,
        help_text="List of IP addresses associated with this resource.",
    )
    fqdn = models.CharField(
        max_length=1024,
        blank=True,
        default="",
        help_text="Fully Qualified Domain Name.",
    )
    mac_addresses = models.JSONField(
        default=list,
        blank=True,
        help_text="List of MAC addresses.",
    )

    # === Operating System / Platform (compute resources) ===
    os_type = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Normalized OS family (linux, windows, network_os, storage_os).",
    )
    os_name = models.CharField(
        max_length=256,
        blank=True,
        default="",
        help_text="Full OS name (e.g. 'Red Hat Enterprise Linux 9.2', 'NX-OS 10.3').",
    )

    # === Flexible Properties (Level 3 — Device Properties) ===
    properties = models.JSONField(
        default=dict,
        blank=True,
        help_text="Type-specific and vendor-specific attributes (JSONB). "
        "This is the Level 3 'Device Properties' from the taxonomy.",
    )

    # === Tagging ===
    # Provider-native tags stored as JSONB for flexibility
    provider_tags = models.JSONField(
        default=dict,
        blank=True,
        help_text="Tags/labels from the provider (key-value pairs).",
    )

    # === Ansible-specific Metadata ===
    ansible_host = models.CharField(
        max_length=1024,
        blank=True,
        default="",
        help_text="The ansible_host value for this resource.",
    )
    ansible_connection = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Connection type (ssh, winrm, network_cli, httpapi, etc.).",
    )
    inventory_group = models.CharField(
        max_length=512,
        blank=True,
        default="",
        help_text="Primary Ansible inventory group this resource belongs to.",
    )
    last_job_id = models.CharField(
        max_length=256,
        blank=True,
        default="",
        help_text="ID of the last AAP job that touched this resource.",
    )

    # === Collection Tracking ===
    first_discovered_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this resource was first discovered.",
    )
    last_seen_at = models.DateTimeField(
        auto_now=True,
        help_text="When this resource was last seen in a collection run.",
    )
    collection_run = models.ForeignKey(
        "inventory.CollectionRun",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resources",
        help_text="The collection run that last updated this resource.",
    )

    # === Ownership ===
    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="resources",
        help_text="Organization that owns this resource.",
    )

    class Meta:
        ordering = ["name"]
        # A resource is uniquely identified by its provider + native ref
        unique_together = [("provider", "ems_ref")]
        indexes = [
            models.Index(fields=["resource_type", "state"]),
            models.Index(fields=["provider", "resource_type"]),
            models.Index(fields=["organization", "resource_type"]),
            models.Index(fields=["region"]),
            models.Index(fields=["vendor_type"]),
            models.Index(fields=["last_seen_at"]),
            # GIN index for JSONB properties queries
            models.Index(
                name="idx_resource_properties_gin",
                fields=["properties"],
                opclasses=["jsonb_path_ops"],
            ),
            models.Index(
                name="idx_resource_provider_tags_gin",
                fields=["provider_tags"],
                opclasses=["jsonb_path_ops"],
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.resource_type.slug})"


class ResourceRelationship(models.Model):
    """
    Relationships between resources.

    Equivalent to ManageIQ's relationship table that links VMs to Hosts,
    Hosts to Clusters, VMs to CloudNetworks, etc.

    Examples:
      source=vm-123,    target=host-456,    relationship_type='runs_on'
      source=subnet-1,  target=vpc-10,      relationship_type='part_of'
      source=vm-123,    target=sg-789,      relationship_type='member_of'
      source=volume-1,  target=vm-123,      relationship_type='attached_to'
      source=lb-1,      target=vm-123,      relationship_type='load_balances'
    """

    class RelationshipType(models.TextChoices):
        RUNS_ON = "runs_on", "Runs On"
        PART_OF = "part_of", "Part Of"
        MEMBER_OF = "member_of", "Member Of"
        ATTACHED_TO = "attached_to", "Attached To"
        CONNECTED_TO = "connected_to", "Connected To"
        MANAGED_BY = "managed_by", "Managed By"
        CONTAINS = "contains", "Contains"
        DEPENDS_ON = "depends_on", "Depends On"
        LOAD_BALANCES = "load_balances", "Load Balances"
        ROUTES_TO = "routes_to", "Routes To"
        BACKS_UP = "backs_up", "Backs Up"
        REPLICATES_TO = "replicates_to", "Replicates To"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey(
        Resource,
        on_delete=models.CASCADE,
        related_name="outgoing_relationships",
    )
    target = models.ForeignKey(
        Resource,
        on_delete=models.CASCADE,
        related_name="incoming_relationships",
    )
    relationship_type = models.CharField(
        max_length=32,
        choices=RelationshipType.choices,
        db_index=True,
    )
    properties = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional relationship metadata.",
    )

    class Meta:
        unique_together = [("source", "target", "relationship_type")]
        indexes = [
            models.Index(fields=["source", "relationship_type"]),
            models.Index(fields=["target", "relationship_type"]),
        ]

    def __str__(self):
        return f"{self.source.name} —[{self.relationship_type}]→ {self.target.name}"
