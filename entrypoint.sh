#!/bin/sh
set -e

uv run --no-sync python manage.py migrate

# Ensure Default organization exists (not synced automatically on fresh clusters)
uv run --no-sync python manage.py shell -c "
from apps.core.models.organization import Organization
org, created = Organization.objects.get_or_create(
    name='Default',
    defaults={'description': 'The default organization for Ansible Automation Platform'}
)
if created:
    print('Created Default organization')
"

exec "$@"
