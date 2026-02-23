"""Run a collection directly, bypassing dispatcherd.

Usage:
    python manage.py run_collection <collection_run_id>
    python manage.py run_collection --provider <provider_id>
"""
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Run an inventory collection directly (bypasses dispatcherd)'

    def add_arguments(self, parser):
        parser.add_argument('collection_run_id', nargs='?', help='Existing CollectionRun UUID')
        parser.add_argument('--provider', help='Provider UUID – creates a new CollectionRun automatically')

    def handle(self, *args, **options):
        from apps.inventory.models import CollectionRun, Provider

        run_id = options['collection_run_id']
        provider_id = options.get('provider')

        if not run_id and not provider_id:
            raise CommandError('Provide either a collection_run_id or --provider <id>')

        if provider_id and not run_id:
            provider = Provider.objects.get(pk=provider_id)
            run = CollectionRun.objects.create(
                provider=provider,
                collection_type='full',
                status=CollectionRun.Status.PENDING,
            )
            run_id = str(run.pk)
            self.stdout.write(f'Created CollectionRun {run_id} for provider {provider.name}')

        from apps.inventory.tasks import run_collection as _run
        # Call the underlying function directly (no dispatcherd)
        result = _run.__wrapped__(run_id) if hasattr(_run, '__wrapped__') else _run(run_id)
        self.stdout.write(self.style.SUCCESS(f'Result: {result}'))
