"""
Provider model — the Ansible equivalent of ManageIQ's ExtManagementSystem (EMS).

A Provider represents a connection to an external management system from which
inventory is collected. Examples: an AWS account, a vCenter instance, a Cisco
APIC controller, a NetApp ONTAP cluster.

Design notes (ManageIQ alignment):
- ManageIQ uses STI on a single `ext_management_systems` table with a `type`
  column (e.g. ManageIQ::Providers::Amazon::CloudManager). We use an
  `infrastructure` + `vendor` + `provider_type` triple instead, which maps
  directly to the Ansible Normalized Resource Taxonomy levels and avoids
  Ruby-specific STI inheritance.
- `ems_ref`-style cross-referencing happens on Resource, not here.
"""

import uuid

from django.conf import settings
from django.db import models


class ProviderInfrastructure(models.TextChoices):
    """Level 0 — Infrastructure classification from the Ansible taxonomy."""

    PUBLIC_CLOUD = "public_cloud", "Public Cloud"
    PRIVATE_CLOUD = "private_cloud", "Private Cloud"
    NETWORKING = "networking", "Networking"
    STORAGE = "storage", "Storage"


class Provider(models.Model):
    """
    An external management system that Ansible collects inventory from.

    Parallels ManageIQ's ExtManagementSystem. Every resource in the inventory
    is associated with exactly one provider.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Human-readable label, e.g. "Production AWS US-East-1"
    name = models.CharField(max_length=512, help_text="Display name for this provider.")

    # Taxonomy Level 0
    infrastructure = models.CharField(
        max_length=32,
        choices=ProviderInfrastructure.choices,
        help_text="Top-level infrastructure classification.",
    )

    # Vendor key — normalized slug, e.g. "aws", "azure", "vmware", "cisco", "netapp"
    vendor = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Vendor slug matching the Ansible collection namespace (e.g. 'aws', 'vmware', 'cisco').",
    )

    # More specific provider type within the vendor, e.g. "ec2", "vcenter", "nxos", "ontap"
    provider_type = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Specific manager type within the vendor (e.g. 'ec2', 'vcenter', 'aci').",
    )

    # Connection endpoint (URL, hostname, or API base)
    endpoint = models.CharField(
        max_length=1024,
        blank=True,
        default="",
        help_text="Connection URL or hostname for this provider.",
    )

    # Reference to external credential (e.g. AAP credential ID, vault path)
    credential_ref = models.CharField(
        max_length=512,
        blank=True,
        default="",
        help_text="External credential reference (AAP credential ID, vault path, etc.).",
    )

    # Enabled/disabled toggle
    enabled = models.BooleanField(default=True, help_text="Whether inventory collection is active.")

    # Flexible vendor-specific connection config
    connection_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Vendor-specific connection parameters (region, zone, tenant, etc.).",
    )

    # Ownership
    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="providers",
        help_text="Organization that owns this provider.",
    )

    # Timestamps
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        default=None,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        default=None,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )

    # Last successful collection timestamp
    last_refresh_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of the last successful inventory collection.",
    )

    class Meta:
        ordering = ["name"]
        unique_together = [("organization", "name")]
        indexes = [
            models.Index(fields=["vendor"]),
            models.Index(fields=["infrastructure", "vendor"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.vendor})"
