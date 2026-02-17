"""Provider plugin registry — discovery, loading, and lifecycle management.

The registry supports three loading mechanisms, in order of precedence:

1. **Built-in providers** — Python packages in ``apps/inventory/providers/``
   that subclass ``BaseProvider``. Discovered automatically at startup.

2. **Entry-point providers** — External packages that declare the
   ``inventory_service.providers`` entry point group. This is the primary
   mechanism for third-party / partner providers:

       # In an external package's pyproject.toml:
       [project.entry-points."inventory_service.providers"]
       my_cloud = "my_package.provider:MyCloudProvider"

3. **Runtime registration** — Programmatic registration via
   ``registry.register(ProviderClass)`` for testing or dynamic loading.

Enable / disable:
    - Individual Provider model instances have an ``enabled`` flag
    - The INVENTORY_PROVIDERS_ENABLED setting controls which provider
      *classes* are available at all (empty = all discovered providers)
    - The INVENTORY_PROVIDERS_DISABLED setting can blacklist specific
      vendor:provider_type combos

Dependency awareness:
    Each provider package may include Ansible collection-compatible
    dependency files (requirements.txt, requirements.yml, bindep.txt,
    meta/execution-environment.yml, meta/runtime.yml, manifest.yml).
    The registry can introspect these for tooling and validation.
"""
from __future__ import annotations

import importlib
import logging
import os
import pkgutil
from pathlib import Path
from typing import Any, Type

import yaml

from .base import BaseProvider, ProviderCredential

logger = logging.getLogger("apps.inventory.providers.registry")

# Entry point group name for external provider packages
ENTRY_POINT_GROUP = "inventory_service.providers"

# Files the registry looks for in each provider package directory
# (mirrors Ansible collection conventions)
MANIFEST_FILE = "manifest.yml"
REQUIREMENTS_TXT = "requirements.txt"
REQUIREMENTS_YML = "requirements.yml"
BINDEP_TXT = "bindep.txt"
EE_YML = "meta/execution-environment.yml"
RUNTIME_YML = "meta/runtime.yml"


class ProviderManifest:
    """
    Parsed provider manifest (manifest.yml).

    Mirrors the structure of a collection's galaxy.yml but scoped to a
    single provider plugin. Used by tooling to resolve dependencies,
    validate compatibility, and generate documentation.
    """

    def __init__(self, data: dict[str, Any], package_dir: Path | None = None):
        self.raw = data
        self.package_dir = package_dir

        # Identity
        self.namespace: str = data.get("namespace", "")
        self.name: str = data.get("name", "")
        self.version: str = data.get("version", "0.0.0")
        self.display_name: str = data.get("display_name", "")
        self.description: str = data.get("description", "")

        # Provider mapping
        self.vendor: str = data.get("vendor", "")
        self.provider_type: str = data.get("provider_type", "")
        self.infrastructure: str = data.get("infrastructure", "")

        # Compatibility
        self.requires_python: str = data.get("requires_python", "")
        self.ansible_collection: str | None = data.get("ansible_collection")

        # Resource types
        self.supported_resource_types: list[str] = data.get(
            "supported_resource_types", []
        )

        # Connection parameters schema
        self.connection_parameters: list[dict] = data.get(
            "connection_parameters", []
        )

        # Dependency file paths (relative to package_dir)
        deps = data.get("dependencies", {})
        self.python_requirements_file: str = deps.get("python", REQUIREMENTS_TXT)
        self.collections_requirements_file: str = deps.get("collections", REQUIREMENTS_YML)
        self.system_requirements_file: str = deps.get("system", BINDEP_TXT)

    @classmethod
    def from_file(cls, path: Path) -> "ProviderManifest":
        """Load a manifest from a YAML file."""
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
        return cls(data, package_dir=path.parent)

    @classmethod
    def from_provider_class(cls, provider_class: Type[BaseProvider]) -> "ProviderManifest | None":
        """
        Attempt to load a manifest from the provider class's package directory.

        Returns None if no manifest.yml is found (the provider may be a
        bare module without collection-style packaging).
        """
        module = importlib.import_module(provider_class.__module__)
        module_file = getattr(module, "__file__", None)
        if not module_file:
            return None

        # Walk up to find the package directory containing manifest.yml
        pkg_dir = Path(module_file).parent
        manifest_path = pkg_dir / MANIFEST_FILE
        if not manifest_path.exists():
            # Try one level up (e.g. vmware_vsphere/provider.py -> vmware_vsphere/)
            manifest_path = pkg_dir.parent / MANIFEST_FILE
            if not manifest_path.exists():
                return None
            pkg_dir = pkg_dir.parent

        return cls.from_file(manifest_path)

    # -- Dependency file access ------------------------------------------

    def _read_file(self, relative_path: str) -> str | None:
        """Read a dependency file relative to the package directory."""
        if not self.package_dir:
            return None
        full_path = self.package_dir / relative_path
        if full_path.exists():
            return full_path.read_text()
        return None

    def python_requirements(self) -> str | None:
        """Return contents of requirements.txt (PEP 508 format)."""
        return self._read_file(self.python_requirements_file)

    def collection_requirements(self) -> dict | None:
        """Return parsed requirements.yml (ansible-galaxy format)."""
        content = self._read_file(self.collections_requirements_file)
        if content:
            return yaml.safe_load(content)
        return None

    def system_requirements(self) -> str | None:
        """Return contents of bindep.txt."""
        return self._read_file(self.system_requirements_file)

    def execution_environment(self) -> dict | None:
        """Return parsed meta/execution-environment.yml."""
        content = self._read_file(EE_YML)
        if content:
            return yaml.safe_load(content)
        return None

    def runtime_metadata(self) -> dict | None:
        """Return parsed meta/runtime.yml."""
        content = self._read_file(RUNTIME_YML)
        if content:
            return yaml.safe_load(content)
        return None

    def as_dict(self) -> dict[str, Any]:
        """Serialize manifest to a dict for API responses / CLI output."""
        return {
            "namespace": self.namespace,
            "name": self.name,
            "version": self.version,
            "display_name": self.display_name,
            "description": self.description,
            "vendor": self.vendor,
            "provider_type": self.provider_type,
            "infrastructure": self.infrastructure,
            "ansible_collection": self.ansible_collection,
            "supported_resource_types": self.supported_resource_types,
            "connection_parameters": self.connection_parameters,
            "has_python_requirements": self._read_file(self.python_requirements_file) is not None,
            "has_collection_requirements": self._read_file(self.collections_requirements_file) is not None,
            "has_system_requirements": self._read_file(self.system_requirements_file) is not None,
        }


class ProviderRegistry:
    """
    Singleton registry for inventory provider plugins.

    Providers are keyed by ``vendor:provider_type`` (e.g. 'vmware:vcenter',
    'aws:ec2', 'cisco:nxos').
    """

    def __init__(self):
        self._providers: dict[str, Type[BaseProvider]] = {}
        self._manifests: dict[str, ProviderManifest | None] = {}
        self._discovered = False

    @property
    def providers(self) -> dict[str, Type[BaseProvider]]:
        if not self._discovered:
            self.discover()
        return dict(self._providers)

    def key_for(self, vendor: str, provider_type: str) -> str:
        return f"{vendor}:{provider_type}"

    # -- Registration ------------------------------------------------------

    def register(self, provider_class: Type[BaseProvider]) -> None:
        """
        Register a provider class.

        Args:
            provider_class: A subclass of BaseProvider with vendor and
                provider_type set.

        Raises:
            TypeError: If not a BaseProvider subclass.
            ValueError: If vendor or provider_type is missing.
        """
        if not isinstance(provider_class, type) or not issubclass(provider_class, BaseProvider):
            raise TypeError(
                f"{provider_class} is not a BaseProvider subclass"
            )
        if not provider_class.vendor or not provider_class.provider_type:
            raise ValueError(
                f"{provider_class.__name__} must set vendor and provider_type"
            )

        key = self.key_for(provider_class.vendor, provider_class.provider_type)

        if not self._is_enabled(key):
            logger.debug("Provider %s is disabled — skipping registration", key)
            return

        if key in self._providers:
            logger.warning(
                "Provider %s already registered (%s) — overwriting with %s",
                key,
                self._providers[key].__name__,
                provider_class.__name__,
            )

        self._providers[key] = provider_class

        # Try to load manifest
        try:
            self._manifests[key] = ProviderManifest.from_provider_class(provider_class)
        except Exception as exc:
            logger.warning("Could not load manifest for %s: %s", key, exc)
            self._manifests[key] = None

        logger.info("Registered provider: %s (%s)", key, provider_class.__name__)

    # -- Discovery ---------------------------------------------------------

    def discover(self) -> None:
        """
        Discover and register all available providers.

        Called automatically on first access to ``providers``. Safe to
        call multiple times (idempotent after first run).
        """
        if self._discovered:
            return
        self._discovered = True

        logger.info("Discovering inventory providers...")
        self._discover_builtin()
        self._discover_entry_points()
        logger.info(
            "Discovery complete: %d provider(s) registered", len(self._providers)
        )

    def _discover_builtin(self) -> None:
        """Discover providers in apps/inventory/providers/ subpackages."""
        package_dir = os.path.dirname(__file__)

        for importer, modname, ispkg in pkgutil.iter_modules([package_dir]):
            # Skip private modules and this module
            if modname.startswith("_") or modname in ("base", "registry"):
                continue

            try:
                if ispkg:
                    # Package provider (e.g. vmware_vsphere/)
                    module = importlib.import_module(
                        f"apps.inventory.providers.{modname}"
                    )
                else:
                    # Single-file provider (e.g. my_provider.py)
                    module = importlib.import_module(
                        f"apps.inventory.providers.{modname}"
                    )

                # Find BaseProvider subclasses in the module
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, BaseProvider)
                        and attr is not BaseProvider
                        and attr.vendor
                        and attr.provider_type
                    ):
                        self.register(attr)

            except Exception as exc:
                logger.warning("Failed to load built-in provider '%s': %s", modname, exc)

    def _discover_entry_points(self) -> None:
        """Discover providers registered via Python entry points."""
        try:
            from importlib.metadata import entry_points
            eps = entry_points(group=ENTRY_POINT_GROUP)
        except Exception:
            return

        for ep in eps:
            try:
                provider_class = ep.load()
                if (
                    isinstance(provider_class, type)
                    and issubclass(provider_class, BaseProvider)
                ):
                    self.register(provider_class)
                else:
                    logger.warning(
                        "Entry point '%s' did not resolve to a BaseProvider subclass",
                        ep.name,
                    )
            except Exception as exc:
                logger.warning(
                    "Failed to load entry point provider '%s': %s", ep.name, exc
                )

    # -- Enable / disable --------------------------------------------------

    def _is_enabled(self, key: str) -> bool:
        """Check if a provider key is enabled via settings."""
        try:
            from django.conf import settings
        except Exception:
            return True

        # Whitelist mode
        enabled = getattr(settings, "INVENTORY_PROVIDERS_ENABLED", [])
        if enabled and key not in enabled:
            return False

        # Blacklist mode
        disabled = getattr(settings, "INVENTORY_PROVIDERS_DISABLED", [])
        if key in disabled:
            return False

        return True

    # -- Instantiation -----------------------------------------------------

    def get(self, vendor: str, provider_type: str) -> Type[BaseProvider] | None:
        """Look up a provider class by vendor and type."""
        if not self._discovered:
            self.discover()
        return self._providers.get(self.key_for(vendor, provider_type))

    def get_manifest(self, vendor: str, provider_type: str) -> ProviderManifest | None:
        """Get the manifest for a provider, if available."""
        if not self._discovered:
            self.discover()
        return self._manifests.get(self.key_for(vendor, provider_type))

    def instantiate(self, provider_model) -> BaseProvider:
        """
        Create a provider instance from a Provider model.

        Resolves the provider class from the registry, resolves
        credentials from the model's connection_config, and returns
        an instantiated provider ready for collection.

        Args:
            provider_model: A Provider Django model instance.

        Returns:
            An instantiated BaseProvider subclass.

        Raises:
            ValueError: If no provider is registered for this vendor:type.
        """
        key = self.key_for(provider_model.vendor, provider_model.provider_type)
        provider_class = self.get(provider_model.vendor, provider_model.provider_type)

        if provider_class is None:
            raise ValueError(
                f"No provider registered for '{key}'. "
                f"Available: {list(self._providers.keys())}"
            )

        credential = self._resolve_credential(provider_model)
        return provider_class(provider_model, credential)

    def _resolve_credential(self, provider_model) -> ProviderCredential:
        """
        Resolve credentials from a Provider model's connection_config.

        This is the seam where you'd plug in AAP credential store /
        vault resolution later — one method to change, all providers
        benefit.
        """
        config = provider_model.connection_config or {}
        endpoint = provider_model.endpoint or ""

        # Parse hostname and port from endpoint
        hostname = endpoint
        port = 443
        if "://" in endpoint:
            hostname = endpoint.split("://", 1)[1]
        if "/" in hostname:
            hostname = hostname.split("/", 1)[0]
        if ":" in hostname:
            hostname, port_str = hostname.rsplit(":", 1)
            try:
                port = int(port_str)
            except ValueError:
                pass

        return ProviderCredential(
            username=config.get("username", ""),
            password=config.get("password", ""),
            hostname=hostname,
            port=config.get("port", port),
            extra={
                k: v
                for k, v in config.items()
                if k not in ("username", "password", "port")
            },
        )

    # -- Listing -----------------------------------------------------------

    def list_providers(self) -> list[dict]:
        """Return a list of registered providers with metadata."""
        if not self._discovered:
            self.discover()

        result = []
        for key, cls in sorted(self._providers.items()):
            manifest = self._manifests.get(key)
            info = {
                "key": key,
                "vendor": cls.vendor,
                "provider_type": cls.provider_type,
                "display_name": cls.display_name or cls.__name__,
                "class": f"{cls.__module__}.{cls.__name__}",
                "supported_resource_types": cls.supported_resource_types,
                "manifest": manifest.as_dict() if manifest else None,
            }
            result.append(info)
        return result

    def aggregated_python_requirements(self) -> str:
        """Merge all providers' requirements.txt into one."""
        lines: set[str] = set()
        for key, manifest in self._manifests.items():
            if manifest:
                content = manifest.python_requirements()
                if content:
                    for line in content.strip().splitlines():
                        line = line.strip()
                        if line and not line.startswith("#"):
                            lines.add(line)
        return "\n".join(sorted(lines))

    def aggregated_collection_requirements(self) -> dict:
        """Merge all providers' requirements.yml into one."""
        seen: dict[str, str] = {}  # collection name -> version spec
        for key, manifest in self._manifests.items():
            if manifest:
                reqs = manifest.collection_requirements()
                if reqs and "collections" in reqs:
                    for col in reqs["collections"]:
                        name = col.get("name", "")
                        version = col.get("version", "*")
                        if name:
                            # Keep the most specific version constraint
                            if name not in seen or seen[name] == "*":
                                seen[name] = version
        return {
            "collections": [
                {"name": name, "version": version}
                for name, version in sorted(seen.items())
            ]
        }

    def aggregated_system_requirements(self) -> str:
        """Merge all providers' bindep.txt into one."""
        lines: set[str] = set()
        for key, manifest in self._manifests.items():
            if manifest:
                content = manifest.system_requirements()
                if content:
                    for line in content.strip().splitlines():
                        line = line.strip()
                        if line and not line.startswith("#"):
                            lines.add(line)
        return "\n".join(sorted(lines))

    # -- Reset (for testing) -----------------------------------------------

    def reset(self) -> None:
        """Clear all registrations and reset discovery state.

        Primarily for testing."""
        self._providers.clear()
        self._manifests.clear()
        self._discovered = False


# Module-level singleton
registry = ProviderRegistry()
