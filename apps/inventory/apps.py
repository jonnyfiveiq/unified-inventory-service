import logging
import sys
from pathlib import Path

from django.apps import AppConfig

logger = logging.getLogger("apps.inventory")


class InventoryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.inventory"
    label = "inventory"
    verbose_name = "Unified Inventory"

    def ready(self):
        # Configure dispatcherd so that both the web process (publisher)
        # and the worker process use the same pg_notify settings.
        # Import is deferred to avoid loading models before the app registry
        # is fully populated.
        try:
            from apps.inventory.dispatcher import setup_dispatcher
            setup_dispatcher()
        except Exception:
            logger.debug("dispatcherd setup deferred — database may not be available yet")

        # Point the provider plugin registry at the plugins/ directory
        # so it can discover unpacked provider plugins on startup.
        # The PVC mount at /app/plugins ensures uploaded plugins persist
        # across pod restarts.
        try:
            from django.conf import settings
            from inventory_providers import registry

            plugins_dir = Path(getattr(settings, "PLUGINS_DIR", settings.BASE_DIR / "plugins"))
            plugins_dir.mkdir(parents=True, exist_ok=True)
            registry.plugins_dir = plugins_dir
            logger.info("Provider plugins directory: %s", plugins_dir)

            # Ensure the shared .deps directory (where plugin pip
            # dependencies are installed during upload) is on sys.path
            # so that provider plugins can import their dependencies
            # after a pod restart without re-uploading.
            deps_dir = plugins_dir / ".deps"
            if deps_dir.is_dir():
                deps_str = str(deps_dir)
                if deps_str not in sys.path:
                    sys.path.insert(0, deps_str)
                    logger.info("Added plugin deps to sys.path: %s", deps_str)
        except Exception:
            logger.debug("Provider registry setup deferred")
