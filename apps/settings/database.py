"""Database configuration hook for the inventory service.

This module provides the `override_database_settings` function that maps
simple DB_* environment variables (loaded by Dynaconf from
INVENTORY_SERVICE_DB_* env vars) into Django's DATABASES dict with
PostgreSQL as the backend.

This follows the same pattern used by the AAP platform-service-framework
(see ansible-pattern-service/pattern_service/settings/dispatcher.py).

Loading order (in inventory_service/settings.py):
  1. Defaults define DATABASES with sqlite3 fallback
  2. Dynaconf loads INVENTORY_SERVICE_DB_* env vars as DB_HOST, DB_PORT, etc.
  3. This function constructs DATABASES["default"] and DATABASES["dispatcher"]
     from those DB_* settings, switching the engine to PostgreSQL.

Environment variables (set via compose.yaml or shell):
  INVENTORY_SERVICE_DB_HOST       (default: 127.0.0.1)
  INVENTORY_SERVICE_DB_PORT       (default: 5432)
  INVENTORY_SERVICE_DB_NAME       (default: inventory_db)
  INVENTORY_SERVICE_DB_USER       (default: inventory)
  INVENTORY_SERVICE_DB_PASSWORD   (required in production)
  INVENTORY_SERVICE_DB_SSLMODE    (default: allow)
  INVENTORY_SERVICE_DB_SSLCERT    (default: "")
  INVENTORY_SERVICE_DB_SSLKEY     (default: "")
  INVENTORY_SERVICE_DB_SSLROOTCERT (default: "")
"""

from django.core.exceptions import ImproperlyConfigured
from dynaconf import Dynaconf


def override_database_settings(loaded_settings: Dynaconf) -> None:
    """Build PostgreSQL DATABASES from DB_* settings loaded by Dynaconf."""
    databases = loaded_settings.get("DATABASES", {})

    db_host = loaded_settings.get("DB_HOST", "127.0.0.1")
    db_port = loaded_settings.get("DB_PORT", 5432)
    db_user = loaded_settings.get("DB_USER", "inventory")
    db_password = loaded_settings.get("DB_PASSWORD", "inventory123")
    db_name = loaded_settings.get("DB_NAME", "inventory_db")
    db_app_name = loaded_settings.get("DB_APP_NAME", "inventory_service")

    db_sslmode = loaded_settings.get("DB_SSLMODE", default="allow")
    db_sslcert = loaded_settings.get("DB_SSLCERT", default="")
    db_sslkey = loaded_settings.get("DB_SSLKEY", default="")
    db_sslrootcert = loaded_settings.get("DB_SSLROOTCERT", default="")

    pg_options = {
        "sslmode": db_sslmode,
        "sslcert": db_sslcert,
        "sslkey": db_sslkey,
        "sslrootcert": db_sslrootcert,
    }

    pg_config = {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": db_host,
        "PORT": db_port,
        "USER": db_user,
        "PASSWORD": db_password,
        "NAME": db_name,
        "OPTIONS": pg_options,
    }

    databases["default"] = dict(pg_config)
    databases["dispatcher"] = dict(pg_config)

    dispatcher_conninfo = (
        f"dbname={db_name} user={db_user} password={db_password} "
        f"host={db_host} port={db_port} application_name={db_app_name}"
    )

    config = loaded_settings.get("DISPATCHER_CONFIG", None)
    if config and "brokers" in config and "pg_notify" in config["brokers"]:
        config["brokers"]["pg_notify"]["config"].update(
            {"conninfo": dispatcher_conninfo}
        )
        dispatcher_node_id = loaded_settings.get("DISPATCHER_NODE_ID", default="")
        if dispatcher_node_id:
            config["service"]["main_kwargs"]["node_id"] = dispatcher_node_id
        loaded_settings.update(
            {"DATABASES": databases, "DISPATCHER_CONFIG": config},
            loader_identifier="settings:override_database_settings",
        )
    else:
        loaded_settings.update(
            {"DATABASES": databases},
            loader_identifier="settings:override_database_settings",
        )
