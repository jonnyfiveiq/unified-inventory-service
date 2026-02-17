"""Management command: list registered inventory providers with dependency info.

Usage:
    python manage.py list_providers
    python manage.py list_providers --verbose
    python manage.py list_providers --deps
    python manage.py list_providers --deps --format=yml
    python manage.py list_providers --test
"""
from __future__ import annotations

import json
import sys

import yaml
from django.core.management.base import BaseCommand

from apps.inventory.providers import registry


class Command(BaseCommand):
    help = "List registered inventory provider plugins and their dependencies"

    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose", "-v",
            action="store_true",
            help="Show full manifest and connection parameter details",
        )
        parser.add_argument(
            "--deps",
            action="store_true",
            help="Show aggregated dependency files (requirements.txt, "
                 "requirements.yml, bindep.txt) across all providers",
        )
        parser.add_argument(
            "--format",
            choices=["text", "json", "yml"],
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
        # Force discovery
        providers = registry.list_providers()

        if options["deps"]:
            return self._show_deps(options["format"])

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
        self.stdout.write(f"  Class: {info['class']}")
        self.stdout.write(f"  Resource types: {', '.join(info['supported_resource_types'])}")

        manifest = info.get("manifest")
        if manifest:
            self.stdout.write(f"  Version: {manifest['version']}")
            self.stdout.write(f"  Infrastructure: {manifest.get('infrastructure', 'n/a')}")
            if manifest.get("ansible_collection"):
                self.stdout.write(f"  Ansible collection: {manifest['ansible_collection']}")

            dep_flags = []
            if manifest.get("has_python_requirements"):
                dep_flags.append("requirements.txt")
            if manifest.get("has_collection_requirements"):
                dep_flags.append("requirements.yml")
            if manifest.get("has_system_requirements"):
                dep_flags.append("bindep.txt")
            if dep_flags:
                self.stdout.write(f"  Dependency files: {', '.join(dep_flags)}")

            if verbose and manifest.get("connection_parameters"):
                self.stdout.write(f"\n  Connection parameters:")
                for param in manifest["connection_parameters"]:
                    required = " (required)" if param.get("required") else ""
                    secret = " [secret]" if param.get("secret") else ""
                    default = f" default={param['default']}" if "default" in param else ""
                    self.stdout.write(
                        f"    - {param['name']}: {param.get('type', 'string')}"
                        f"{required}{secret}{default}"
                    )
                    if param.get("description"):
                        self.stdout.write(f"      {param['description']}")
        else:
            self.stdout.write(
                self.style.WARNING("  (no manifest.yml — legacy provider)")
            )

    def _show_deps(self, fmt: str):
        """Show aggregated dependencies across all providers."""
        self.stdout.write(self.style.MIGRATE_HEADING("Aggregated Dependencies"))

        # Python requirements
        python_reqs = registry.aggregated_python_requirements()
        if python_reqs:
            self.stdout.write(self.style.SUCCESS("\n--- requirements.txt ---"))
            if fmt == "json":
                self.stdout.write(json.dumps(python_reqs.splitlines(), indent=2))
            else:
                self.stdout.write(python_reqs)

        # Collection requirements
        collection_reqs = registry.aggregated_collection_requirements()
        if collection_reqs.get("collections"):
            self.stdout.write(self.style.SUCCESS("\n--- requirements.yml ---"))
            if fmt == "json":
                self.stdout.write(json.dumps(collection_reqs, indent=2))
            else:
                self.stdout.write(yaml.dump(collection_reqs, default_flow_style=False))

        # System requirements
        system_reqs = registry.aggregated_system_requirements()
        if system_reqs:
            self.stdout.write(self.style.SUCCESS("\n--- bindep.txt ---"))
            if fmt == "json":
                self.stdout.write(json.dumps(system_reqs.splitlines(), indent=2))
            else:
                self.stdout.write(system_reqs)

    def _test_connectivity(self):
        """Test connectivity for all configured provider instances."""
        from apps.inventory.models import Provider

        self.stdout.write("\n" + self.style.MIGRATE_HEADING("Testing Provider Connections"))

        configured = Provider.objects.filter(enabled=True)
        if not configured.exists():
            self.stdout.write(self.style.WARNING("  No enabled providers configured in the database."))
            return

        for provider_model in configured:
            key = f"{provider_model.vendor}:{provider_model.provider_type}"
            self.stdout.write(f"\n  {provider_model.name} ({key})")
            self.stdout.write(f"    Endpoint: {provider_model.endpoint}")

            try:
                instance = registry.instantiate(provider_model)
                ok, msg = instance.validate_connection()
                if ok:
                    self.stdout.write(self.style.SUCCESS(f"    ✓ {msg}"))
                else:
                    self.stdout.write(self.style.ERROR(f"    ✗ {msg}"))
            except ValueError as exc:
                self.stdout.write(self.style.ERROR(f"    ✗ No plugin: {exc}"))
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"    ✗ Error: {exc}"))
