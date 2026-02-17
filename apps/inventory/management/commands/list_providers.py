"""Management command: list registered inventory provider plugins.

Usage:
    python manage.py list_providers
    python manage.py list_providers --verbose
    python manage.py list_providers --format=json
    python manage.py list_providers --test
"""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from inventory_providers import registry


class Command(BaseCommand):
    help = "List registered inventory provider plugins"

    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose", "-v",
            action="store_true",
            help="Show full class path and supported resource types",
        )
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Output format (default: text)",
        )
        parser.add_argument(
            "--test",
            action="store_true",
            help="Test connectivity for each provider that has a "
                 "Provider model instance configured",
        )

    def handle(self, **options):
        providers = registry.list_providers()

        if options["format"] == "json":
            self.stdout.write(json.dumps(providers, indent=2))
            return

        if not providers:
            self.stdout.write(self.style.WARNING("No providers registered."))
            return

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Registered Provider Plugins ({len(providers)})"
        ))
        for info in providers:
            self._print_provider(info, verbose=options["verbose"])

        if options["test"]:
            self._test_connectivity()

    def _print_provider(self, info: dict, verbose: bool = False):
        self.stdout.write(
            self.style.SUCCESS(f"\n{'='*60}")
        )
        self.stdout.write(
            self.style.SUCCESS(f"  {info['display_name']}  [{info['key']}]")
        )
        self.stdout.write(f"  Vendor: {info['vendor']}")
        self.stdout.write(f"  Type: {info['provider_type']}")
        self.stdout.write(f"  Resource types: {', '.join(info['supported_resource_types'])}")
        if verbose:
            self.stdout.write(f"  Class: {info['class']}")

    def _test_connectivity(self):
        """Test connectivity for all configured provider instances."""
        from inventory_providers import ProviderCredential
        from apps.inventory.models import Provider

        self.stdout.write("\n" + self.style.MIGRATE_HEADING("Testing Provider Connections"))

        configured = Provider.objects.filter(enabled=True)
        if not configured.exists():
            self.stdout.write(self.style.WARNING(
                "  No enabled providers configured in the database."
            ))
            return

        for provider_model in configured:
            key = f"{provider_model.vendor}:{provider_model.provider_type}"
            self.stdout.write(f"\n  {provider_model.name} ({key})")
            self.stdout.write(f"    Endpoint: {provider_model.endpoint}")

            try:
                credential = self._resolve_credential(provider_model)
                instance = registry.instantiate(provider_model, credential)
                ok, msg = instance.validate_connection()
                if ok:
                    self.stdout.write(self.style.SUCCESS(f"    OK: {msg}"))
                else:
                    self.stdout.write(self.style.ERROR(f"    FAIL: {msg}"))
            except ValueError as exc:
                self.stdout.write(self.style.ERROR(f"    No plugin: {exc}"))
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"    Error: {exc}"))

    @staticmethod
    def _resolve_credential(provider_model) -> "ProviderCredential":
        """Build a ProviderCredential from a Provider model instance."""
        from inventory_providers import ProviderCredential

        return ProviderCredential(
            hostname=provider_model.endpoint or "",
            port=provider_model.port or 443,
            username=provider_model.credentials.get("username", "") if provider_model.credentials else "",
            password=provider_model.credentials.get("password", "") if provider_model.credentials else "",
            extra=provider_model.credentials.get("extra", {}) if provider_model.credentials else {},
        )
