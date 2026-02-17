"""Provider plugin registry — discovery, loading, and lifecycle management.

The registry supports four loading mechanisms:

1. **Plugins directory** (primary mechanism for installed plugins) —
   scans ``plugins/`` for vendor/type directories containing a
   ``provider.py`` with a BaseProvider subclass.

2. **Entry-point providers** (for pip-installed packages)::

       # In a partner's pyproject.toml:
       [project.entry-points."inventory_providers"]
       my_cloud = "my_package.provider:MyCloudProvider"

3. **Runtime registration** — programmatic via ``registry.register()``

4. **Module scanning** — ``registry.load_module(module)`` to scan a
   module for BaseProvider subclasses

This module has no Django dependency. The inventory service app layer
calls ``registry.apply_filter()`` at startup to enforce settings-based
enable/disable.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any, Type

from .base import BaseProvider, ProviderCredential

logger = logging.getLogger("inventory_providers.registry")

# Entry point group name — external packages register under this group
ENTRY_POINT_GROUP = "inventory_providers"


class ProviderRegistry:
    """
    Singleton registry for inventory provider plugins.

    Providers are keyed by ``vendor:provider_type`` (e.g. 'vmware:vcenter',
    'aws:ec2', 'cisco:nxos').
    """

    def __init__(self):
        self._providers: dict[str, Type[BaseProvider]] = {}
        self._discovered = False
        self.plugins_dir: Path | None = None

    @property
    def providers(self) -> dict[str, Type[BaseProvider]]:
        if not self._discovered:
            self.discover()
        return dict(self._providers)

    @staticmethod
    def key_for(vendor: str, provider_type: str) -> str:
        return f"{vendor}:{provider_type}"

    # ── Registration ──────────────────────────────────────────────────

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
            raise TypeError(f"{provider_class} is not a BaseProvider subclass")

        if not provider_class.vendor or not provider_class.provider_type:
            raise ValueError(
                f"{provider_class.__name__} must set both 'vendor' and 'provider_type' class attributes"
            )

        key = provider_class.provider_key()
        if key in self._providers:
            existing = self._providers[key]
            if existing is not provider_class:
                logger.warning(
                    "Replacing provider %s: %s → %s",
                    key,
                    existing.__name__,
                    provider_class.__name__,
                )

        self._providers[key] = provider_class
        logger.info("Registered provider: %s (%s)", key, provider_class.__name__)

    def unregister(self, vendor: str, provider_type: str) -> bool:
        """Remove a provider from the registry. Returns True if it existed."""
        key = self.key_for(vendor, provider_type)
        if key in self._providers:
            del self._providers[key]
            logger.info("Unregistered provider: %s", key)
            return True
        return False

    # ── Discovery ─────────────────────────────────────────────────────

    def discover(self) -> None:
        """
        Discover and load all provider plugins.

        Scans the plugins directory (if set) and entry points.
        Called automatically on first access to ``.providers``.
        Safe to call multiple times.
        """
        if self._discovered:
            return

        if self.plugins_dir:
            self._discover_plugins_dir()
        self._discover_entrypoints()
        self._discovered = True

        logger.info(
            "Provider discovery complete: %d providers — %s",
            len(self._providers),
            ", ".join(sorted(self._providers.keys())) or "(none)",
        )

    def _discover_plugins_dir(self) -> None:
        """
        Scan the plugins directory for provider plugin packages.

        Expected layout::

            plugins/
              vmware/
                vcenter/
                  provider.py   <- must contain a BaseProvider subclass
                  manifest.yml  <- plugin metadata
              cisco/
                nxos/
                  provider.py

        Each vendor/type directory with a provider.py is loaded as a
        module and scanned for BaseProvider subclasses.
        """
        if not self.plugins_dir or not self.plugins_dir.is_dir():
            return

        for vendor_dir in sorted(self.plugins_dir.iterdir()):
            if not vendor_dir.is_dir() or vendor_dir.name.startswith((".", "_")):
                continue
            for plugin_dir in sorted(vendor_dir.iterdir()):
                if not plugin_dir.is_dir() or plugin_dir.name.startswith((".", "_")):
                    continue
                provider_py = plugin_dir / "provider.py"
                if not provider_py.exists():
                    logger.debug(
                        "Skipping %s/%s — no provider.py",
                        vendor_dir.name, plugin_dir.name,
                    )
                    continue
                try:
                    self._load_provider_from_path(provider_py, vendor_dir.name, plugin_dir.name)
                except Exception:
                    logger.exception(
                        "Failed to load provider from %s/%s",
                        vendor_dir.name, plugin_dir.name,
                    )

    def _load_provider_from_path(
        self, provider_py: Path, vendor: str, plugin_type: str,
    ) -> None:
        """Load a provider module from a file path and register any BaseProvider subclasses."""
        module_name = f"inventory_providers_plugin_{vendor}_{plugin_type}"

        # Add the plugin directory to sys.path so relative imports work
        plugin_dir_str = str(provider_py.parent)
        if plugin_dir_str not in sys.path:
            sys.path.insert(0, plugin_dir_str)

        spec = importlib.util.spec_from_file_location(module_name, provider_py)
        if spec is None or spec.loader is None:
            logger.warning("Cannot create module spec for %s", provider_py)
            return

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        count = self.load_module(module)
        if count:
            logger.info(
                "Loaded %d provider(s) from plugins/%s/%s",
                count, vendor, plugin_type,
            )
        else:
            logger.warning(
                "No BaseProvider subclasses found in plugins/%s/%s/provider.py",
                vendor, plugin_type,
            )

    def _discover_entrypoints(self) -> None:
        """Load providers from the ``inventory_providers`` entry point group."""
        try:
            from importlib.metadata import entry_points
        except ImportError:
            return

        eps = entry_points()
        if hasattr(eps, "select"):
            group = eps.select(group=ENTRY_POINT_GROUP)
        elif isinstance(eps, dict):
            group = eps.get(ENTRY_POINT_GROUP, [])
        else:
            group = [ep for ep in eps if ep.group == ENTRY_POINT_GROUP]

        for ep in group:
            try:
                obj = ep.load()
                if isinstance(obj, type) and issubclass(obj, BaseProvider):
                    self.register(obj)
                    logger.info("Loaded entry-point provider: %s → %s", ep.name, obj.__name__)
                elif hasattr(obj, "__path__") or hasattr(obj, "__file__"):
                    # It's a module — scan for BaseProvider subclasses
                    self.load_module(obj)
                else:
                    logger.warning(
                        "Entry point %s resolved to %s which is not a BaseProvider subclass",
                        ep.name,
                        obj,
                    )
            except Exception:
                logger.exception("Failed to load entry-point provider: %s", ep.name)

    def load_module(self, module) -> int:
        """
        Scan a Python module for BaseProvider subclasses and register them.

        Useful for loading providers from arbitrary modules at runtime::

            import my_partner_providers
            registry.load_module(my_partner_providers)

        Args:
            module: A Python module object.

        Returns:
            Number of providers registered from this module.
        """
        count = 0
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if (
                isinstance(obj, type)
                and issubclass(obj, BaseProvider)
                and obj is not BaseProvider
                and obj.vendor
                and obj.provider_type
            ):
                self.register(obj)
                count += 1
        return count

    def load_class(self, dotted_path: str) -> Type[BaseProvider]:
        """
        Import and register a provider from a dotted Python path.

        Example::

            registry.load_class("my_package.providers.MyCloudProvider")

        Args:
            dotted_path: Full dotted path to the provider class.

        Returns:
            The loaded provider class.

        Raises:
            ImportError: If the module cannot be imported.
            AttributeError: If the class doesn't exist in the module.
            TypeError: If the class is not a BaseProvider subclass.
        """
        module_path, _, class_name = dotted_path.rpartition(".")
        if not module_path:
            raise ImportError(f"Invalid dotted path: {dotted_path}")

        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        if not isinstance(cls, type) or not issubclass(cls, BaseProvider):
            raise TypeError(f"{dotted_path} is not a BaseProvider subclass")

        self.register(cls)
        return cls

    # ── Filtering (called by app layer with Django settings) ──────────

    def apply_filter(
        self,
        enabled: list[str] | None = None,
        disabled: list[str] | None = None,
    ) -> None:
        """
        Filter registered providers by whitelist / blacklist.

        Called by the inventory service app at startup with values
        from Django settings.

        Args:
            enabled: If set, only these provider keys are kept (whitelist).
            disabled: These provider keys are removed (blacklist).
        """
        # Ensure discovery has run
        _ = self.providers

        if enabled:
            enabled_set = set(enabled)
            to_remove = [k for k in self._providers if k not in enabled_set]
            for key in to_remove:
                del self._providers[key]
                logger.info("Provider %s filtered out (not in enabled list)", key)

        if disabled:
            for key in disabled:
                if key in self._providers:
                    del self._providers[key]
                    logger.info("Provider %s disabled via disabled list", key)

    # ── Lookup ────────────────────────────────────────────────────────

    def get(self, vendor: str, provider_type: str) -> Type[BaseProvider] | None:
        """Look up a registered provider class by vendor and type."""
        return self.providers.get(self.key_for(vendor, provider_type))

    def get_by_key(self, key: str) -> Type[BaseProvider] | None:
        """Look up a registered provider class by its key (vendor:type)."""
        return self.providers.get(key)

    def list_providers(self) -> list[dict[str, Any]]:
        """Return metadata about all registered providers."""
        return [cls.metadata() for _, cls in sorted(self.providers.items())]

    def instantiate(
        self,
        provider_model: Any,
        credential: ProviderCredential | None = None,
    ) -> BaseProvider:
        """
        Create an instance of the appropriate provider for a provider record.

        Args:
            provider_model: An object with ``.vendor`` and ``.provider_type``
                attributes (typically the Django Provider model instance).
            credential: Resolved credentials. If None, you must supply
                them before calling connect().

        Raises:
            ValueError: If no provider plugin matches.
        """
        vendor = getattr(provider_model, "vendor", "")
        ptype = getattr(provider_model, "provider_type", "")
        cls = self.get(vendor, ptype)
        if cls is None:
            available = ", ".join(sorted(self._providers.keys())) or "(none)"
            raise ValueError(
                f"No provider plugin registered for {vendor}:{ptype}. "
                f"Available: {available}"
            )

        if credential is None:
            credential = ProviderCredential()

        return cls(provider_model, credential)

    # ── Utility ───────────────────────────────────────────────────────

    def reset(self) -> None:
        """Clear the registry. Primarily for testing."""
        self._providers.clear()
        self._discovered = False
        # Note: plugins_dir is preserved across reset


# Module-level singleton
registry = ProviderRegistry()
