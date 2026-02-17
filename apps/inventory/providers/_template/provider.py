"""
Skeleton provider implementation.

Copy this directory and rename it to create a new inventory provider.
Then update manifest.yml, requirements.*, and implement the methods below.
"""
from __future__ import annotations

from typing import Iterator

from apps.inventory.providers.base import BaseProvider, ResourceData


class MyProvider(BaseProvider):
    """Collects inventory from My Cloud/Infrastructure."""

    # ------------------------------------------------------------------ #
    # Class attributes — override these for your provider                 #
    # ------------------------------------------------------------------ #
    vendor = "my_vendor"
    provider_type = "my_type"
    display_name = "My Provider"
    supported_resource_types = ["virtual_machine"]

    # ------------------------------------------------------------------ #
    # Lifecycle                                                           #
    # ------------------------------------------------------------------ #
    def connect(self) -> None:
        """Establish connection to the remote system."""
        cred = self.credential
        # self._client = SomeSDK(
        #     host=cred.hostname,
        #     username=cred.username,
        #     password=cred.password,
        #     port=cred.port,
        #     verify_ssl=cred.extra.get("validate_certs", True),
        # )
        raise NotImplementedError("Implement connect()")

    def disconnect(self) -> None:
        """Clean up the remote connection."""
        # if hasattr(self, "_client") and self._client:
        #     self._client.close()
        pass

    # ------------------------------------------------------------------ #
    # Collection                                                          #
    # ------------------------------------------------------------------ #
    def collect(self) -> Iterator[ResourceData]:
        """
        Yield ResourceData objects for every discovered resource.

        Example:
            yield ResourceData(
                ems_ref="vm-12345",
                resource_type_slug="virtual_machine",
                name="my-server-01",
                canonical_id="unique-uuid-here",
                state="running",
                cpu_count=4,
                memory_mb=8192,
                ip_addresses=["10.0.0.1"],
                os_type="linux",
                os_name="Red Hat Enterprise Linux 9",
                properties={
                    "custom_field": "value",
                },
                ansible_host="10.0.0.1",
                ansible_connection="ssh",
                inventory_group="linux",
            )
        """
        raise NotImplementedError("Implement collect()")
