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
    """Build a libpq connection string from Django DATABASES['default'].

    Falls back to INVENTORY_SERVICE_DB_* / INVENTORY_SERVICE_DATABASES__default__*
    environment variables when Django settings contain the default ``127.0.0.1``
    placeholder (which happens when ``override_database_settings`` runs before
    Dynaconf resolves the nested env-var overrides).
    """
    import os

    db = dict(settings.DATABASES.get("default", {}))

    # Dynaconf nested env vars (INVENTORY_SERVICE_DATABASES__default__HOST)
    # may not be reflected in the dict snapshot returned by settings.DATABASES
    # when override_database_settings() has already overwritten it with the
    # DB_HOST default of 127.0.0.1.  Fall back to env vars directly.
    env_host = (
        os.environ.get("INVENTORY_SERVICE_DB_HOST")
        or os.environ.get("INVENTORY_SERVICE_DATABASES__default__HOST")
    )
    env_port = (
        os.environ.get("INVENTORY_SERVICE_DB_PORT")
        or os.environ.get("INVENTORY_SERVICE_DATABASES__default__PORT")
    )
    env_name = (
        os.environ.get("INVENTORY_SERVICE_DB_NAME")
        or os.environ.get("INVENTORY_SERVICE_DATABASES__default__NAME")
    )
    env_user = (
        os.environ.get("INVENTORY_SERVICE_DB_USER")
        or os.environ.get("INVENTORY_SERVICE_DATABASES__default__USER")
    )
    env_password = (
        os.environ.get("INVENTORY_SERVICE_DB_PASSWORD")
        or os.environ.get("INVENTORY_SERVICE_DATABASES__default__PASSWORD")
    )

    host = env_host or db.get("HOST") or "127.0.0.1"
    port = env_port or db.get("PORT") or "5432"
    name = env_name or db.get("NAME") or "inventory_db"
    user = env_user or db.get("USER") or "inventory_svc"
    password = env_password or db.get("PASSWORD") or ""

    parts = [
        "dbname={}".format(name),
        "user={}".format(user),
    ]
    if password:
        parts.append("password={}".format(password))
    parts.append("host={}".format(host))
    parts.append("port={}".format(port))
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
