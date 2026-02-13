"""
Inventory app settings.

These are loaded by the dynaconf framework in the order defined by
LOADED_APPS. They can be overridden by environment variables prefixed
with INVENTORY_SERVICE_.

Example overrides:
    INVENTORY_SERVICE_DISPATCHER_MAX_WORKERS=8
    INVENTORY_SERVICE_DISPATCHER_TASK_TIMEOUT=7200
"""

# Dispatcherd worker pool settings (used by apps/inventory/dispatcher.py)
DISPATCHER_MAX_WORKERS = 4
DISPATCHER_MIN_WORKERS = 1
DISPATCHER_TASK_TIMEOUT = 3600  # seconds — default max runtime per collection
