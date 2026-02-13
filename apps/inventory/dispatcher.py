"""
Dispatcherd configuration for the inventory-service.

Builds the dispatcherd config from Django's DATABASES setting so there is
a single source of truth for the PostgreSQL connection.  The pg_notify
channel ``inventory_tasks`` is used for all collection task dispatch.

Usage:
    Called once from InventoryConfig.ready() so that both the web process
    (publisher) and the dispatcher worker process share the same config.

    # Publishing a task (from a viewset or management command):
    from dispatcherd.publish import submit_task
    from apps.inventory.tasks import run_collection
    submit_task(run_collection, kwargs={"collection_run_id": str(run.id)})
"""

import logging

from django.conf import settings

logger = logging.getLogger("apps.inventory.dispatcher")

INVENTORY_CHANNEL = "inventory_tasks"
DEFAULT_TASK_TIMEOUT = 3600  # 1 hour max per collection run


def build_conninfo() -> str:
    """Build a libpq connection string from Django DATABASES['default']."""
    db = settings.DATABASES["default"]
    parts = [
        f"dbname={db.get('NAME', 'inventory_db')}",
        f"user={db.get('USER', 'inventory_svc')}",
    ]
    if db.get("PASSWORD"):
        parts.append(f"password={db['PASSWORD']}")
    if db.get("HOST"):
        parts.append(f"host={db['HOST']}")
    if db.get("PORT"):
        parts.append(f"port={db['PORT']}")
    parts.append("application_name=inventory_dispatcher")
    return " ".join(parts)


def get_dispatcher_config() -> dict:
    """Return the full dispatcherd config dictionary."""
    conninfo = build_conninfo()
    return {
        "version": 2,
        "brokers": {
            "pg_notify": {
                "config": {"conninfo": conninfo},
                "channels": [INVENTORY_CHANNEL],
                "default_publish_channel": INVENTORY_CHANNEL,
                "max_connection_idle_seconds": 30,
            },
        },
        "service": {
            "pool_kwargs": {
                "min_workers": getattr(settings, "DISPATCHER_MIN_WORKERS", 1),
                "max_workers": getattr(settings, "DISPATCHER_MAX_WORKERS", 4),
            },
        },
        "producers": {
            "ControlProducer": {},
        },
        "publish": {
            "default_broker": "pg_notify",
        },
    }


def setup_dispatcher() -> None:
    """Configure dispatcherd from Django settings.  Safe to call multiple times."""
    try:
        from dispatcherd.config import is_setup, setup
    except ImportError:
        logger.warning("dispatcherd is not installed — background task dispatch will be unavailable")
        return

    if is_setup():
        return

    config = get_dispatcher_config()
    setup(config)
    logger.info("dispatcherd configured: channel=%s", INVENTORY_CHANNEL)
