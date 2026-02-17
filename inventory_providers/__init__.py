"""Inventory Providers — pluggable collection providers for the AAP Inventory Service.

This package defines the provider plugin interface and ships contrib
providers for common infrastructure platforms.

For provider authors:

    from inventory_providers import BaseProvider, ResourceData, ProviderCredential

    class MyCloudProvider(BaseProvider):
        vendor = "mycloud"
        provider_type = "api"
        supported_resource_types = ["virtual_machine"]

        def connect(self): ...
        def disconnect(self): ...
        def collect(self): yield ResourceData(ems_ref="...", ...)

Register via entry point in your package's pyproject.toml::

    [project.entry-points."inventory_providers"]
    mycloud = "my_package.provider:MyCloudProvider"

For the inventory service (consumer):

    from inventory_providers import registry

    # Auto-discovers all installed providers
    providers = registry.list_providers()

    # Instantiate for a given Provider model
    instance = registry.instantiate(provider_model, credential)
    instance.connect()
    for resource_data in instance.collect():
        ...
    instance.disconnect()
"""

from .base import BaseProvider, CollectionResult, ProviderCredential, ResourceData
from .registry import ProviderRegistry, registry

__all__ = [
    "BaseProvider",
    "CollectionResult",
    "ProviderCredential",
    "ProviderRegistry",
    "ResourceData",
    "registry",
]

__version__ = "0.1.0"
