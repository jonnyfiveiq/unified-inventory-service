"""Pluggable inventory collection providers.

This package implements the provider plugin architecture for the
inventory service. Providers are responsible for connecting to
external management systems and collecting inventory data.

Quick start — registering a new provider:

    1. Built-in: Create a module in this package that subclasses
       ``BaseProvider`` with ``vendor`` and ``provider_type`` set.
       It will be discovered automatically at startup.

    2. External package: Declare an entry point in pyproject.toml:

           [project.entry-points."inventory_service.providers"]
           my_cloud = "my_package.provider:MyCloudProvider"

    3. Runtime: Call ``registry.register(MyProvider)`` directly.

Usage from tasks.py:

    from apps.inventory.providers import registry

    provider_instance = registry.instantiate(provider_model)
    result = provider_instance.run_collection(collection_run)

Enable / disable at the settings level:

    # settings.py — whitelist mode (only these are available)
    INVENTORY_PROVIDERS_ENABLED = ["vmware:vcenter", "aws:ec2"]

    # settings.py — blacklist mode (these are excluded)
    INVENTORY_PROVIDERS_DISABLED = ["cisco:nxos"]
"""

from .base import BaseProvider, CollectionResult, ProviderCredential, ResourceData
from .registry import ProviderManifest, ProviderRegistry, registry

__all__ = [
    "BaseProvider",
    "CollectionResult",
    "ProviderCredential",
    "ProviderManifest",
    "ProviderRegistry",
    "ResourceData",
    "registry",
]
