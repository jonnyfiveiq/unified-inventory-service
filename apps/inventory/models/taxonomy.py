"""
Taxonomy reference models — the normalized resource classification hierarchy.

These are the Ansible equivalent of ManageIQ's implicit STI class hierarchy,
made explicit as database-driven lookup tables so they can be maintained by
Partner Engineering (as the taxonomy doc recommends) without code changes.

Hierarchy from the Ansible Normalized Resource Taxonomy:
  Level 0: Infrastructure       → Provider.infrastructure
  Level 1: Device Category      → ResourceCategory  (compute, storage, networking, database, …)
  Level 2: Device Type          → ResourceType       (virtual_machine, container, switch, …)
  Level 3: Device Properties    → Resource.properties (JSONB)

ManageIQ alignment:
  ManageIQ's STI types like VmOrTemplate, Host, CloudNetwork, SecurityGroup
  correspond to our ResourceType entries. The difference is that MIQ bakes
  these into Ruby classes; we store them as data so the taxonomy is extensible
  at runtime.
"""

import uuid

from django.db import models


class ResourceCategory(models.Model):
    """
    Level 1 — Device Category.

    Examples: Compute, Storage, Networking, Database, Security & Identity,
    App Integration & Messaging, DevOps, AI/ML, Governance & Operations, etc.

    Maps to ManageIQ's top-level model groupings (Cloud, Infra, Network,
    Storage, Container).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(
        max_length=64,
        unique=True,
        help_text="Machine-readable key (e.g. 'compute', 'networking').",
    )
    name = models.CharField(
        max_length=128,
        help_text="Human-readable name (e.g. 'Compute', 'Networking').",
    )
    description = models.TextField(blank=True, default="")

    # Ordering for UI display
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "resource categories"

    def __str__(self):
        return self.name


class ResourceType(models.Model):
    """
    Level 2 — Device Type (normalized).

    Examples: virtual_machine, container, hypervisor_host, bare_metal,
    switch, router, firewall, block_storage, object_storage, relational_db, etc.

    This is the Ansible equivalent of ManageIQ's concrete model classes:
      virtual_machine     ↔ VmOrTemplate
      hypervisor_host     ↔ Host
      cloud_network / vpc ↔ CloudNetwork
      security_group      ↔ SecurityGroup
      flavor              ↔ Flavor
      block_storage       ↔ CloudVolume
      container           ↔ Container (from containers provider)
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.ForeignKey(
        ResourceCategory,
        on_delete=models.CASCADE,
        related_name="resource_types",
        help_text="The device category this type belongs to.",
    )
    slug = models.SlugField(
        max_length=96,
        unique=True,
        help_text="Machine-readable key (e.g. 'virtual_machine', 'switch').",
    )
    name = models.CharField(
        max_length=256,
        help_text="Human-readable name (e.g. 'Virtual Machine', 'Switch').",
    )
    description = models.TextField(blank=True, default="")

    # Whether this type represents a billable/countable indirect node
    is_countable = models.BooleanField(
        default=True,
        help_text="Whether resources of this type should be counted for billing/licensing.",
    )

    # Strategic value scores from the taxonomy doc
    long_term_strategic_value = models.IntegerField(
        null=True,
        blank=True,
        help_text="LTSV score (1-5) from the normalized taxonomy.",
    )
    short_term_opportunity = models.IntegerField(
        null=True,
        blank=True,
        help_text="STO / metrics-utility fit score (1-5).",
    )

    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["category", "sort_order", "name"]

    def __str__(self):
        return f"{self.category.name} → {self.name}"


class VendorTypeMapping(models.Model):
    """
    Maps vendor-specific resource names to the normalized ResourceType.

    This is the Ansible equivalent of ManageIQ's parser logic — the mapping
    between the native provider schema and the normalized schema.

    Examples:
      vendor='aws',     vendor_type='EC2 Instance'   → resource_type='virtual_machine'
      vendor='azure',   vendor_type='Virtual Machine' → resource_type='virtual_machine'
      vendor='vmware',  vendor_type='vSphere VM'      → resource_type='virtual_machine'
      vendor='cisco',   vendor_type='Nexus 9000'      → resource_type='switch'
      vendor='netapp',  vendor_type='ONTAP SAN'       → resource_type='block_storage'
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    vendor = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Vendor slug matching Provider.vendor.",
    )
    vendor_resource_type = models.CharField(
        max_length=256,
        help_text="The vendor's native name for this resource type.",
    )
    resource_type = models.ForeignKey(
        ResourceType,
        on_delete=models.CASCADE,
        related_name="vendor_mappings",
        help_text="The normalized resource type this maps to.",
    )

    # Optional: the Ansible collection + module that manages this type
    ansible_collection = models.CharField(
        max_length=256,
        blank=True,
        default="",
        help_text="Ansible collection (e.g. 'amazon.aws', 'cisco.nxos').",
    )
    ansible_module = models.CharField(
        max_length=256,
        blank=True,
        default="",
        help_text="Primary Ansible module for this resource type.",
    )

    # Query file reference for indirect node counting
    query_file_ref = models.CharField(
        max_length=512,
        blank=True,
        default="",
        help_text="Reference to the query file used in indirect node counting.",
    )

    class Meta:
        unique_together = [("vendor", "vendor_resource_type")]
        ordering = ["vendor", "vendor_resource_type"]

    def __str__(self):
        return f"{self.vendor}:{self.vendor_resource_type} → {self.resource_type.slug}"


class PropertyDefinition(models.Model):
    """
    Defines an expected key in Resource.properties for a given ResourceType.

    This is the contract between the taxonomy and collector authors. When a
    collector writes to Resource.properties, it SHOULD use the keys defined
    here. This solves the "publicly_available vs public vs is_public" problem
    by giving each resource type a documented schema for its JSONB properties.

    Benefits:
      - Collector authors know exactly what keys to write
      - Reporting can query PropertyDefinition to build dynamic columns
      - Validation can flag non-conforming properties
      - API docs can expose the expected schema per resource type

    The `required` flag indicates whether collectors MUST populate this key.
    Optional properties are documented but not enforced.

    Example definitions for resource_type='virtual_machine':
      key='linked_clone',       value_type='boolean', required=False
      key='fault_tolerance',    value_type='boolean', required=False
      key='tools_status',       value_type='string',  required=False
      key='memory_reservation', value_type='integer', required=False
      key='publicly_available', value_type='boolean', required=False
    """

    class ValueType(models.TextChoices):
        STRING = "string", "String"
        INTEGER = "integer", "Integer"
        FLOAT = "float", "Float"
        BOOLEAN = "boolean", "Boolean"
        DATETIME = "datetime", "DateTime (ISO 8601)"
        JSON = "json", "JSON object/array"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    resource_type = models.ForeignKey(
        ResourceType,
        on_delete=models.CASCADE,
        related_name="property_definitions",
        help_text="The resource type this property applies to.",
    )
    key = models.CharField(
        max_length=128,
        help_text="The JSONB key name that collectors should use in "
        "Resource.properties (e.g. 'linked_clone', 'tools_status').",
    )
    name = models.CharField(
        max_length=256,
        help_text="Human-readable name (e.g. 'Linked Clone', 'VMware Tools Status').",
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="What this property represents and how collectors should populate it.",
    )
    value_type = models.CharField(
        max_length=16,
        choices=ValueType.choices,
        default=ValueType.STRING,
        help_text="Expected data type for this property value.",
    )
    required = models.BooleanField(
        default=False,
        help_text="Whether collectors MUST populate this property. "
        "Optional properties are documented but not enforced.",
    )
    example_value = models.CharField(
        max_length=512,
        blank=True,
        default="",
        help_text="Example value for documentation (e.g. 'true', '4096', 'guestToolsRunning').",
    )
    vendor_scope = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="If set, this property only applies to a specific vendor "
        "(e.g. 'vmware', 'aws'). Empty means it applies to all vendors.",
    )

    class Meta:
        unique_together = [("resource_type", "key")]
        ordering = ["resource_type", "key"]
        verbose_name_plural = "property definitions"

    def __str__(self):
        scope = f" [{self.vendor_scope}]" if self.vendor_scope else ""
        return f"{self.resource_type.slug}.{self.key}{scope} ({self.value_type})"
