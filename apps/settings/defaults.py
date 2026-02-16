"""
Top level settings file for all apps.

The settings here overrides any setting previously loaded
from the `inventory_service.settings`.
"""

extra_applications = [
    "django_filters",
]
"""Extra applications added after PSF templating."""

dab_applications = [
    "ansible_base.activitystream",
    "ansible_base.api_documentation",
    "ansible_base.feature_flags",
    "ansible_base.jwt_consumer",
    "ansible_base.rbac",
    "ansible_base.resource_registry",
    "ansible_base.rest_filters",
    "ansible_base.rest_pagination",
]
"""Default DAB applications layd out from PSF, add/remove according to the project needs,
adjust `pyproject` dab extra dependencies acording to apps added/removed here.
"""

project_applications = [
    "apps.core",
    "apps.inventory",
]
"""List of applications from the apps/ folder."""


INSTALLED_APPS = [
    "dynaconf_merge_unique",  # DO NOT REMOVE THIS
    *dab_applications,
    *project_applications,
    *extra_applications,
]
"""Final state of the INSTALLED_APPS that will merge with the rest of the settings."""

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "UNAUTHENTICATED_USER": None,
    "UNAUTHENTICATED_TOKEN": None,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "apps.core.renderers.ServiceBrowsableAPIRenderer",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.NamespaceVersioning",
    "DEFAULT_VERSION": "v1",
    "ALLOWED_VERSIONS": ["v1"],
}
"""REST framework settings."""

SPECTACULAR_SETTINGS__TITLE = "inventory_service API"
"""Title of Swagger the API documentation."""
SPECTACULAR_SETTINGS__DESCRIPTION = "API documentation for the inventory_service"
"""Description of Swagger the API documentation."""
SPECTACULAR_SETTINGS__VERSION = "v1"
"""Version of Swagger the API documentation."""
SPECTACULAR_SETTINGS__COMPONENT_SPLIT_REQUEST = True
"""Split components into request and response for generating clients."""

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "default",
    },
}
CSRF_TRUSTED_ORIGINS = []

# Dispatcher configuration for dispatcherd (pg_notify broker)
# The conninfo string is overridden at runtime by apps/settings/database.py
# based on INVENTORY_SERVICE_DB_* environment variables.
DISPATCHER_CONFIG = {
    "version": 2,
    "service": {
        "main_kwargs": {"node_id": "inventory-service-a"},
        "process_manager_kwargs": {},
    },
    "brokers": {
        "pg_notify": {
            "config": {
                "conninfo": (
                    "dbname=inventory_db user=inventory password=inventory123 "
                    "host=127.0.0.1 port=5432 application_name=dispatcher_inventory_service"
                )
            },
            "sync_connection_factory": "dispatcherd.brokers.pg_notify.connection_saver",
            "channels": ["inventory-service-tasks"],
            "default_publish_channel": "inventory-service-tasks",
        },
        "socket": {"socket_path": "inventory_service_dispatcher.sock"},
    },
    "publish": {"default_control_broker": "socket", "default_broker": "pg_notify"},
}
