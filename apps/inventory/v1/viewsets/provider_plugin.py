"""Provider Plugin viewset — read-only API over the external plugin registry.

The provider plugin registry lives in the ``inventory_providers`` package,
which is external to this Django app. Plugins are installed as separate
Python packages and discovered via entry points. This viewset exposes
that registry through the REST API.

Endpoints:

    GET  /api/inventory/v1/provider-plugins/
        List all discovered provider plugins.

    GET  /api/inventory/v1/provider-plugins/{key}/
        Detail view for a single plugin.
        The key is vendor:provider_type (e.g. vmware:vcenter).

    POST /api/inventory/v1/provider-plugins/upload/
        Upload and install a provider plugin from a tarball.

    POST /api/inventory/v1/provider-plugins/{key}/test/
        Test connectivity for all configured Provider instances
        using this plugin.

    POST /api/inventory/v1/provider-plugins/refresh/
        Force re-discovery of provider plugins.

    DELETE /api/inventory/v1/provider-plugins/{key}/
        Uninstall a provider plugin and remove its files.
"""
from __future__ import annotations

import logging
import sys
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path

import yaml
from django.conf import settings
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from apps.inventory.v1.serializers.provider_plugin import (
    ProviderPluginSerializer,
    ProviderPluginTestResultSerializer,
    ProviderPluginUploadSerializer,
)
from inventory_providers import ProviderCredential, registry

logger = logging.getLogger("apps.inventory.views")

# Maximum upload size: 50 MB
MAX_UPLOAD_SIZE = 50 * 1024 * 1024

# Required files in a plugin archive
REQUIRED_FILES = {"manifest.yml", "provider.py"}


class ProviderPluginViewSet(ViewSet):
    """
    API for the external provider plugin registry.

    Supports listing, detail views, upload/install, uninstall, connectivity
    testing, and registry refresh. Plugin data comes from the in-memory
    registry in the ``inventory_providers`` package, backed by the
    ``plugins/`` directory on disk.
    """

    permission_classes = [IsAuthenticated]
    lookup_field = "key"
    lookup_value_regex = r"[a-zA-Z0-9_-]+:[a-zA-Z0-9_-]+"

    def list(self, request):
        """List all discovered provider plugins."""
        plugins = registry.list_providers()
        plugins = self._annotate_instance_counts(plugins)
        serializer = ProviderPluginSerializer(plugins, many=True)
        return Response(serializer.data)

    def retrieve(self, request, key=None):
        """Detail view for a single provider plugin."""
        vendor, provider_type = self._parse_key(key)
        if vendor is None:
            return Response(
                {"detail": f"Invalid plugin key '{key}'. Expected format: vendor:provider_type"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        provider_cls = registry.get(vendor, provider_type)
        if provider_cls is None:
            return Response(
                {"detail": f"No registered provider plugin for '{key}'."},
                status=status.HTTP_404_NOT_FOUND,
            )

        data = provider_cls.metadata()
        data = self._annotate_instance_counts([data])[0]
        serializer = ProviderPluginSerializer(data)
        return Response(serializer.data)

    def destroy(self, request, key=None):
        """
        Uninstall a provider plugin.

        Removes the plugin from the registry and deletes its files from
        the plugins directory. Does not remove Provider model instances
        that reference this plugin — they become orphaned and will show
        a missing-plugin warning.
        """
        vendor, provider_type = self._parse_key(key)
        if vendor is None:
            return Response(
                {"detail": f"Invalid plugin key '{key}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check it exists in the registry
        provider_cls = registry.get(vendor, provider_type)
        if provider_cls is None:
            return Response(
                {"detail": f"No registered provider plugin for '{key}'."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check for active Provider instances using this plugin
        from apps.inventory.models import Provider

        active_count = Provider.objects.filter(
            vendor=vendor,
            provider_type=provider_type,
        ).count()

        if active_count > 0 and not request.query_params.get("force"):
            return Response(
                {
                    "detail": (
                        f"Cannot uninstall: {active_count} Provider instance(s) use this plugin. "
                        f"Delete them first or pass ?force=true to uninstall anyway."
                    ),
                    "active_instances": active_count,
                },
                status=status.HTTP_409_CONFLICT,
            )

        # Remove from registry
        registry.unregister(vendor, provider_type)

        # Remove files from disk
        plugins_dir = self._get_plugins_dir()
        plugin_dir = plugins_dir / vendor / provider_type
        removed_files = False
        if plugin_dir.is_dir():
            shutil.rmtree(plugin_dir)
            removed_files = True
            logger.info("Removed plugin directory: %s", plugin_dir)

            # Clean up empty vendor directory
            vendor_dir = plugins_dir / vendor
            if vendor_dir.is_dir() and not any(vendor_dir.iterdir()):
                vendor_dir.rmdir()
                logger.info("Removed empty vendor directory: %s", vendor_dir)

        return Response(
            {
                "detail": f"Plugin '{key}' uninstalled.",
                "removed_from_registry": True,
                "removed_files": removed_files,
                "orphaned_instances": active_count,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="upload", url_name="upload",
            parser_classes=[MultiPartParser])
    def upload(self, request):
        """
        Upload and install a provider plugin from a tarball or zip archive.

        The archive must contain at minimum:
        - ``manifest.yml`` — plugin identity and metadata
        - ``provider.py``  — BaseProvider subclass

        Optionally:
        - ``requirements.txt`` — Python dependencies (pip-installed server-side)
        - ``requirements.yml`` — Ansible collection dependencies (logged, not installed)
        - ``bindep.txt``       — System dependencies (logged, not installed)

        The plugin is extracted to ``plugins/<vendor>/<provider_type>/``,
        Python dependencies are installed, and the provider class is
        hot-loaded into the registry — no restart required.
        """
        serializer = ProviderPluginUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        archive_file = serializer.validated_data["plugin"]

        # Size check
        if archive_file.size > MAX_UPLOAD_SIZE:
            return Response(
                {"detail": f"Upload too large ({archive_file.size} bytes). Maximum is {MAX_UPLOAD_SIZE} bytes."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Extract to a temp dir first, validate, then move into place
        with tempfile.TemporaryDirectory(prefix="plugin_upload_") as tmpdir:
            tmpdir = Path(tmpdir)

            # Save and extract the archive
            try:
                extract_dir = self._extract_archive(archive_file, tmpdir)
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

            # Validate required files
            missing = REQUIRED_FILES - {f.name for f in extract_dir.iterdir() if f.is_file()}
            if missing:
                return Response(
                    {"detail": f"Archive is missing required files: {', '.join(sorted(missing))}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Parse and validate manifest
            manifest_path = extract_dir / "manifest.yml"
            try:
                manifest = self._parse_manifest(manifest_path)
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

            vendor = manifest["vendor"]
            provider_type = manifest["provider_type"]
            key = f"{vendor}:{provider_type}"
            version = manifest.get("version", "0.0.0")

            # Check if already installed
            existing = registry.get(vendor, provider_type)
            if existing and not request.query_params.get("force"):
                return Response(
                    {
                        "detail": (
                            f"Plugin '{key}' is already installed. "
                            f"Pass ?force=true to overwrite."
                        ),
                        "existing_plugin": existing.metadata(),
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            # Move into the plugins directory
            plugins_dir = self._get_plugins_dir()
            target_dir = plugins_dir / vendor / provider_type
            if target_dir.exists():
                shutil.rmtree(target_dir)
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(extract_dir, target_dir)
            logger.info("Extracted plugin '%s' v%s to %s", key, version, target_dir)

            # Install Python dependencies if requirements.txt exists
            dep_result = self._install_python_deps(target_dir)

            # Hot-load the provider into the registry
            try:
                provider_py = target_dir / "provider.py"
                # Unregister old version if overwriting
                if existing:
                    registry.unregister(vendor, provider_type)
                registry._load_provider_from_path(provider_py, vendor, provider_type)
            except Exception as exc:
                logger.exception("Failed to load plugin '%s' after extraction", key)
                # Clean up on load failure
                shutil.rmtree(target_dir, ignore_errors=True)
                return Response(
                    {"detail": f"Plugin extracted but failed to load: {exc}"},
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )

            # Verify it actually registered
            loaded = registry.get(vendor, provider_type)
            if loaded is None:
                shutil.rmtree(target_dir, ignore_errors=True)
                return Response(
                    {"detail": "Plugin extracted but no BaseProvider subclass was found in provider.py."},
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )

            response_data = {
                "detail": f"Plugin '{key}' v{version} installed successfully.",
                "plugin": ProviderPluginSerializer(loaded.metadata()).data,
                "dependencies": dep_result,
            }

            return Response(response_data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="test", url_name="test")
    def test_connectivity(self, request, key=None):
        """
        Test connectivity for all enabled Provider instances using this plugin.

        Instantiates the plugin for each matching Provider model instance
        and calls ``validate_connection()``. Returns a per-instance result.
        """
        vendor, provider_type = self._parse_key(key)
        if vendor is None:
            return Response(
                {"detail": f"Invalid plugin key '{key}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        provider_cls = registry.get(vendor, provider_type)
        if provider_cls is None:
            return Response(
                {"detail": f"No registered provider plugin for '{key}'."},
                status=status.HTTP_404_NOT_FOUND,
            )

        from apps.inventory.models import Provider

        instances = Provider.objects.filter(
            vendor=vendor,
            provider_type=provider_type,
            enabled=True,
        )

        if not instances.exists():
            return Response(
                {"detail": "No enabled Provider instances configured for this plugin.",
                 "results": []},
                status=status.HTTP_200_OK,
            )

        results = []
        for provider_model in instances:
            try:
                credential = self._resolve_credential(provider_model)
                instance = registry.instantiate(provider_model, credential)
                success, message = instance.validate_connection()
            except Exception as exc:
                success = False
                message = str(exc)

            results.append({
                "provider_id": provider_model.pk,
                "provider_name": provider_model.name,
                "plugin_key": key,
                "success": success,
                "message": message,
            })

        serializer = ProviderPluginTestResultSerializer(results, many=True)
        return Response({"results": serializer.data})

    @action(detail=False, methods=["post"], url_path="refresh", url_name="refresh")
    def refresh(self, request):
        """
        Force re-discovery of provider plugins.

        Resets the registry and re-scans the plugins directory and
        entry points. Useful after manually adding plugin files.
        """
        registry.reset()
        # Re-set the plugins_dir since reset() clears it
        plugins_dir = self._get_plugins_dir()
        registry.plugins_dir = plugins_dir
        registry.discover()
        plugins = registry.list_providers()
        return Response({
            "detail": f"Registry refreshed. {len(plugins)} provider(s) discovered.",
            "providers": ProviderPluginSerializer(plugins, many=True).data,
        })

    # -- Helpers --------------------------------------------------------

    @staticmethod
    def _parse_key(key: str):
        """Split 'vendor:provider_type' into a tuple, or (None, None)."""
        if not key or ":" not in key:
            return None, None
        parts = key.split(":", 1)
        return parts[0], parts[1]

    @staticmethod
    def _get_plugins_dir() -> Path:
        """Return the configured plugins directory, creating it if needed."""
        plugins_dir = Path(getattr(settings, "PLUGINS_DIR", Path(settings.BASE_DIR) / "plugins"))
        plugins_dir.mkdir(parents=True, exist_ok=True)
        return plugins_dir

    @staticmethod
    def _annotate_instance_counts(plugins):
        """Add configured_instances count from the Provider model."""
        from apps.inventory.models import Provider
        from django.db.models import Count

        counts = (
            Provider.objects
            .values("vendor", "provider_type")
            .annotate(count=Count("id"))
        )
        count_map = {
            f"{row['vendor']}:{row['provider_type']}": row["count"]
            for row in counts
        }
        for plugin in plugins:
            plugin["configured_instances"] = count_map.get(plugin["key"], 0)
        return plugins

    @staticmethod
    def _resolve_credential(provider_model) -> ProviderCredential:
        """Build a ProviderCredential from a Provider model instance."""
        creds = provider_model.credentials or {}
        return ProviderCredential(
            hostname=provider_model.endpoint or "",
            port=provider_model.port or 443,
            username=creds.get("username", ""),
            password=creds.get("password", ""),
            extra=creds.get("extra", {}),
        )

    @staticmethod
    def _extract_archive(archive_file, tmpdir: Path) -> Path:
        """
        Extract a tar.gz or zip archive into tmpdir.

        Returns the directory containing the plugin files (handles
        archives that contain a single top-level directory or flat files).
        """
        archive_path = tmpdir / "archive"
        with open(archive_path, "wb") as f:
            for chunk in archive_file.chunks():
                f.write(chunk)

        extract_path = tmpdir / "extracted"
        extract_path.mkdir()

        # Try tarball first, then zip
        if tarfile.is_tarfile(str(archive_path)):
            with tarfile.open(str(archive_path), "r:*") as tar:
                # Security: check for path traversal
                for member in tar.getmembers():
                    member_path = Path(member.name)
                    if member_path.is_absolute() or ".." in member_path.parts:
                        raise ValueError(f"Archive contains unsafe path: {member.name}")
                tar.extractall(extract_path, filter="data")
        elif zipfile.is_zipfile(str(archive_path)):
            with zipfile.ZipFile(str(archive_path), "r") as zf:
                for info in zf.infolist():
                    member_path = Path(info.filename)
                    if member_path.is_absolute() or ".." in member_path.parts:
                        raise ValueError(f"Archive contains unsafe path: {info.filename}")
                zf.extractall(extract_path)
        else:
            raise ValueError("Uploaded file is not a recognized archive (tar.gz, tgz, or zip).")

        # If there's a single top-level directory, descend into it
        children = [c for c in extract_path.iterdir() if not c.name.startswith(".")]
        if len(children) == 1 and children[0].is_dir():
            return children[0]
        return extract_path

    @staticmethod
    def _parse_manifest(manifest_path: Path) -> dict:
        """Parse and validate the plugin manifest.yml."""
        try:
            with open(manifest_path) as f:
                manifest = yaml.safe_load(f)
        except Exception as exc:
            raise ValueError(f"Cannot parse manifest.yml: {exc}")

        if not isinstance(manifest, dict):
            raise ValueError("manifest.yml must be a YAML mapping.")

        # Validate required fields
        for field in ("vendor", "provider_type"):
            # Also accept legacy field names from galaxy.yml conventions
            value = manifest.get(field) or manifest.get("name" if field == "provider_type" else field)
            if not value:
                raise ValueError(f"manifest.yml is missing required field: '{field}'")

        # Normalize: the manifest may use 'name' instead of 'provider_type'
        if "provider_type" not in manifest and "name" in manifest:
            manifest["provider_type"] = manifest["name"]

        vendor = manifest["vendor"]
        provider_type = manifest["provider_type"]

        # Sanity check: vendor and provider_type should be simple identifiers
        import re
        ident_re = re.compile(r"^[a-zA-Z0-9_-]+$")
        if not ident_re.match(vendor):
            raise ValueError(f"Invalid vendor identifier: '{vendor}'")
        if not ident_re.match(provider_type):
            raise ValueError(f"Invalid provider_type identifier: '{provider_type}'")

        return manifest

    @staticmethod
    def _install_python_deps(plugin_dir: Path) -> dict:
        """
        Install Python dependencies from requirements.txt if present.

        Installs into a shared ``plugins/.deps/`` directory that is added
        to ``sys.path`` so all plugins can import their dependencies without
        requiring a writable virtualenv.

        Returns a dict with install status for the API response.
        """
        requirements_txt = plugin_dir / "requirements.txt"
        if not requirements_txt.exists():
            return {"python": "no requirements.txt — skipped"}

        # Install to a writable deps directory alongside the plugins dir.
        # The venv may be read-only in container images, so --target avoids that.
        deps_dir = plugin_dir.parent.parent / ".deps"
        deps_dir.mkdir(parents=True, exist_ok=True)

        # Ensure deps_dir is on sys.path so imports work at runtime
        deps_str = str(deps_dir)
        if deps_str not in sys.path:
            sys.path.insert(0, deps_str)

        # Build candidate commands — use full paths and sys.executable fallback
        import shutil as _shutil
        candidates = []

        uv_path = _shutil.which("uv") or "/usr/local/bin/uv"
        if Path(uv_path).exists():
            candidates.append([uv_path, "pip", "install", "--target", deps_str])

        pip_path = _shutil.which("pip")
        if pip_path:
            candidates.append([pip_path, "install", "--target", deps_str])

        # Always have a fallback via the running interpreter
        candidates.append([sys.executable, "-m", "pip", "install", "--target", deps_str])

        errors = []
        for cmd in candidates:
            try:
                result = subprocess.run(
                    [*cmd, "--no-input", "-r", str(requirements_txt)],
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout
                )
                if result.returncode == 0:
                    installer = Path(cmd[0]).name
                    logger.info(
                        "Installed Python deps for plugin from %s (using %s -> %s)",
                        requirements_txt, installer, deps_dir,
                    )
                    return {
                        "python": "installed",
                        "installer": installer,
                        "target": deps_str,
                    }
                errors.append(f"{cmd[0]}: {result.stderr.strip()[:200]}")
                logger.warning("%s install failed (rc=%d): %s", cmd[0], result.returncode, result.stderr)
            except FileNotFoundError:
                errors.append(f"{cmd[0]}: not found")
                continue
            except subprocess.TimeoutExpired:
                return {"python": "install timed out (300s)"}

        return {"python": "install failed", "errors": errors}
