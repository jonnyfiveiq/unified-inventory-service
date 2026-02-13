"""Management command: seed_vmware_data

Seeds a realistic VMware vSphere inventory for development and testing.
Creates a vCenter provider with datacenters, clusters, ESXi hosts, VMs,
datastores, resource pools, and relationships between them.

Usage:
    python manage.py seed_vmware_data              # seed data
    python manage.py seed_vmware_data --flush      # remove seeded data first
    python manage.py seed_vmware_data --flush-only  # remove without re-seeding
"""

import uuid
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.models import Organization
from apps.inventory.models import (
    CollectionRun,
    Provider,
    Resource,
    ResourceRelationship,
    ResourceType,
)


# ── VMware vSphere Inventory Data ──────────────────────────────────────────
# Modelled on a realistic lab/production vSphere environment

PROVIDER_NAME = "Lab vCenter - vcsa01.lab.local"

DATACENTERS = [
    {
        "name": "Lab-DC1",
        "moid": "datacenter-1",
        "clusters": [
            {
                "name": "Prod-Cluster-01",
                "moid": "domain-c10",
                "ha_enabled": True,
                "drs_enabled": True,
                "hosts": [
                    {
                        "name": "esxi01.lab.local",
                        "moid": "host-101",
                        "cpu_count": 64,
                        "memory_mb": 524288,
                        "os_name": "VMware ESXi 8.0 Update 3",
                        "ip": "10.0.10.101",
                        "model": "PowerEdge R750",
                        "vendor": "Dell Inc.",
                        "serial": "DELLR750-001",
                    },
                    {
                        "name": "esxi02.lab.local",
                        "moid": "host-102",
                        "cpu_count": 64,
                        "memory_mb": 524288,
                        "os_name": "VMware ESXi 8.0 Update 3",
                        "ip": "10.0.10.102",
                        "model": "PowerEdge R750",
                        "vendor": "Dell Inc.",
                        "serial": "DELLR750-002",
                    },
                    {
                        "name": "esxi03.lab.local",
                        "moid": "host-103",
                        "cpu_count": 48,
                        "memory_mb": 393216,
                        "os_name": "VMware ESXi 8.0 Update 2",
                        "ip": "10.0.10.103",
                        "model": "ProLiant DL380 Gen10",
                        "vendor": "HPE",
                        "serial": "HPEDL380-001",
                    },
                ],
                "resource_pools": [
                    {"name": "Production", "moid": "resgroup-201", "cpu_limit": 96000, "memory_limit_mb": 786432},
                    {"name": "Staging", "moid": "resgroup-202", "cpu_limit": 32000, "memory_limit_mb": 262144},
                ],
            },
            {
                "name": "Dev-Cluster-01",
                "moid": "domain-c20",
                "ha_enabled": False,
                "drs_enabled": True,
                "hosts": [
                    {
                        "name": "esxi04.lab.local",
                        "moid": "host-104",
                        "cpu_count": 32,
                        "memory_mb": 262144,
                        "os_name": "VMware ESXi 8.0 Update 3",
                        "ip": "10.0.10.104",
                        "model": "PowerEdge R650",
                        "vendor": "Dell Inc.",
                        "serial": "DELLR650-001",
                    },
                ],
                "resource_pools": [
                    {"name": "Development", "moid": "resgroup-301", "cpu_limit": -1, "memory_limit_mb": -1},
                ],
            },
        ],
        "datastores": [
            {"name": "vsanDatastore-Prod", "moid": "datastore-501", "type": "vsan", "capacity_gb": 20480, "free_gb": 8192},
            {"name": "vsanDatastore-Dev", "moid": "datastore-502", "type": "vsan", "capacity_gb": 10240, "free_gb": 6144},
            {"name": "NFS-ISO-Library", "moid": "datastore-503", "type": "nfs", "capacity_gb": 2048, "free_gb": 1024},
            {"name": "FC-LUN-Backups", "moid": "datastore-504", "type": "vmfs", "capacity_gb": 30720, "free_gb": 15360},
        ],
    },
]

VMS = [
    # Production VMs
    {"name": "aap-controller-01", "moid": "vm-1001", "host": "esxi01.lab.local", "cluster": "Prod-Cluster-01",
     "pool": "Production", "datastore": "vsanDatastore-Prod",
     "cpu": 8, "mem": 32768, "disk": 200, "os_type": "linux", "os_name": "Red Hat Enterprise Linux 9.4",
     "ip": ["10.0.20.10"], "fqdn": "aap-controller-01.lab.local", "state": "running", "power": "poweredOn",
     "tags": {"env": "production", "app": "ansible-aap", "team": "platform-eng"},
     "ansible_group": "aap_controllers", "ansible_conn": "ssh"},
    {"name": "aap-hub-01", "moid": "vm-1002", "host": "esxi02.lab.local", "cluster": "Prod-Cluster-01",
     "pool": "Production", "datastore": "vsanDatastore-Prod",
     "cpu": 4, "mem": 16384, "disk": 500, "os_type": "linux", "os_name": "Red Hat Enterprise Linux 9.4",
     "ip": ["10.0.20.11"], "fqdn": "aap-hub-01.lab.local", "state": "running", "power": "poweredOn",
     "tags": {"env": "production", "app": "ansible-aap", "team": "platform-eng"},
     "ansible_group": "aap_hubs", "ansible_conn": "ssh"},
    {"name": "aap-eda-01", "moid": "vm-1003", "host": "esxi03.lab.local", "cluster": "Prod-Cluster-01",
     "pool": "Production", "datastore": "vsanDatastore-Prod",
     "cpu": 4, "mem": 16384, "disk": 100, "os_type": "linux", "os_name": "Red Hat Enterprise Linux 9.4",
     "ip": ["10.0.20.12"], "fqdn": "aap-eda-01.lab.local", "state": "running", "power": "poweredOn",
     "tags": {"env": "production", "app": "ansible-aap", "team": "platform-eng"},
     "ansible_group": "aap_eda", "ansible_conn": "ssh"},
    {"name": "rhel9-web-01", "moid": "vm-1004", "host": "esxi01.lab.local", "cluster": "Prod-Cluster-01",
     "pool": "Production", "datastore": "vsanDatastore-Prod",
     "cpu": 4, "mem": 8192, "disk": 80, "os_type": "linux", "os_name": "Red Hat Enterprise Linux 9.3",
     "ip": ["10.0.20.20", "10.0.30.20"], "fqdn": "rhel9-web-01.lab.local", "state": "running", "power": "poweredOn",
     "tags": {"env": "production", "app": "web-frontend", "team": "webops"},
     "ansible_group": "webservers", "ansible_conn": "ssh"},
    {"name": "rhel9-web-02", "moid": "vm-1005", "host": "esxi02.lab.local", "cluster": "Prod-Cluster-01",
     "pool": "Production", "datastore": "vsanDatastore-Prod",
     "cpu": 4, "mem": 8192, "disk": 80, "os_type": "linux", "os_name": "Red Hat Enterprise Linux 9.3",
     "ip": ["10.0.20.21", "10.0.30.21"], "fqdn": "rhel9-web-02.lab.local", "state": "running", "power": "poweredOn",
     "tags": {"env": "production", "app": "web-frontend", "team": "webops"},
     "ansible_group": "webservers", "ansible_conn": "ssh"},
    {"name": "rhel9-db-01", "moid": "vm-1006", "host": "esxi03.lab.local", "cluster": "Prod-Cluster-01",
     "pool": "Production", "datastore": "vsanDatastore-Prod",
     "cpu": 16, "mem": 65536, "disk": 1000, "os_type": "linux", "os_name": "Red Hat Enterprise Linux 9.4",
     "ip": ["10.0.20.30"], "fqdn": "rhel9-db-01.lab.local", "state": "running", "power": "poweredOn",
     "tags": {"env": "production", "app": "postgresql", "team": "dba"},
     "ansible_group": "databases", "ansible_conn": "ssh"},
    {"name": "win2022-ad-01", "moid": "vm-1007", "host": "esxi01.lab.local", "cluster": "Prod-Cluster-01",
     "pool": "Production", "datastore": "vsanDatastore-Prod",
     "cpu": 4, "mem": 16384, "disk": 120, "os_type": "windows", "os_name": "Windows Server 2022 Datacenter",
     "ip": ["10.0.20.50"], "fqdn": "win2022-ad-01.lab.local", "state": "running", "power": "poweredOn",
     "tags": {"env": "production", "app": "active-directory", "team": "identity"},
     "ansible_group": "windows_domain_controllers", "ansible_conn": "winrm"},
    {"name": "win2022-iis-01", "moid": "vm-1008", "host": "esxi02.lab.local", "cluster": "Prod-Cluster-01",
     "pool": "Production", "datastore": "vsanDatastore-Prod",
     "cpu": 4, "mem": 8192, "disk": 100, "os_type": "windows", "os_name": "Windows Server 2022 Standard",
     "ip": ["10.0.20.51"], "fqdn": "win2022-iis-01.lab.local", "state": "running", "power": "poweredOn",
     "tags": {"env": "production", "app": "iis-web", "team": "webops"},
     "ansible_group": "windows_webservers", "ansible_conn": "winrm"},
    # Staging VMs
    {"name": "staging-app-01", "moid": "vm-1009", "host": "esxi03.lab.local", "cluster": "Prod-Cluster-01",
     "pool": "Staging", "datastore": "vsanDatastore-Prod",
     "cpu": 2, "mem": 4096, "disk": 60, "os_type": "linux", "os_name": "Red Hat Enterprise Linux 9.2",
     "ip": ["10.0.40.10"], "fqdn": "staging-app-01.lab.local", "state": "running", "power": "poweredOn",
     "tags": {"env": "staging", "app": "web-frontend", "team": "webops"},
     "ansible_group": "staging", "ansible_conn": "ssh"},
    {"name": "staging-db-01", "moid": "vm-1010", "host": "esxi03.lab.local", "cluster": "Prod-Cluster-01",
     "pool": "Staging", "datastore": "vsanDatastore-Prod",
     "cpu": 4, "mem": 8192, "disk": 200, "os_type": "linux", "os_name": "Red Hat Enterprise Linux 9.2",
     "ip": ["10.0.40.11"], "fqdn": "staging-db-01.lab.local", "state": "stopped", "power": "poweredOff",
     "tags": {"env": "staging", "app": "postgresql", "team": "dba"},
     "ansible_group": "staging", "ansible_conn": "ssh"},
    # Dev VMs
    {"name": "dev-rhel9-01", "moid": "vm-2001", "host": "esxi04.lab.local", "cluster": "Dev-Cluster-01",
     "pool": "Development", "datastore": "vsanDatastore-Dev",
     "cpu": 2, "mem": 4096, "disk": 60, "os_type": "linux", "os_name": "Red Hat Enterprise Linux 9.4",
     "ip": ["10.0.50.10"], "fqdn": "dev-rhel9-01.lab.local", "state": "running", "power": "poweredOn",
     "tags": {"env": "development", "team": "platform-eng"},
     "ansible_group": "dev_machines", "ansible_conn": "ssh"},
    {"name": "dev-fedora-01", "moid": "vm-2002", "host": "esxi04.lab.local", "cluster": "Dev-Cluster-01",
     "pool": "Development", "datastore": "vsanDatastore-Dev",
     "cpu": 4, "mem": 8192, "disk": 100, "os_type": "linux", "os_name": "Fedora 41",
     "ip": ["10.0.50.11"], "fqdn": "dev-fedora-01.lab.local", "state": "suspended", "power": "suspended",
     "tags": {"env": "development", "team": "platform-eng"},
     "ansible_group": "dev_machines", "ansible_conn": "ssh"},
    {"name": "template-rhel9-base", "moid": "vm-9001", "host": "esxi01.lab.local", "cluster": "Prod-Cluster-01",
     "pool": "Production", "datastore": "NFS-ISO-Library",
     "cpu": 2, "mem": 2048, "disk": 40, "os_type": "linux", "os_name": "Red Hat Enterprise Linux 9.4",
     "ip": [], "fqdn": "", "state": "inactive", "power": "poweredOff",
     "tags": {"type": "template", "os": "rhel9"},
     "ansible_group": "", "ansible_conn": ""},
    {"name": "template-win2022-base", "moid": "vm-9002", "host": "esxi01.lab.local", "cluster": "Prod-Cluster-01",
     "pool": "Production", "datastore": "NFS-ISO-Library",
     "cpu": 2, "mem": 4096, "disk": 60, "os_type": "windows", "os_name": "Windows Server 2022 Standard",
     "ip": [], "fqdn": "", "state": "inactive", "power": "poweredOff",
     "tags": {"type": "template", "os": "win2022"},
     "ansible_group": "", "ansible_conn": ""},
]


class Command(BaseCommand):
    help = "Seed VMware vSphere inventory data for development and testing."

    def add_arguments(self, parser):
        parser.add_argument("--flush", action="store_true", help="Remove existing seed data before re-seeding.")
        parser.add_argument("--flush-only", action="store_true", help="Remove seed data without re-seeding.")

    def handle(self, *args, **options):
        if options["flush"] or options["flush_only"]:
            self._flush()
            if options["flush_only"]:
                return

        self._seed()

    def _flush(self):
        self.stdout.write("Flushing VMware seed data...")
        provider = Provider.objects.filter(name=PROVIDER_NAME).first()
        if provider:
            count, _ = Resource.objects.filter(provider=provider).delete()
            self.stdout.write(f"  Deleted {count} resources")
            ResourceRelationship.objects.filter(
                source__provider=provider
            ).delete()
            CollectionRun.objects.filter(provider=provider).delete()
            provider.delete()
            self.stdout.write(self.style.SUCCESS(f"  Deleted provider '{PROVIDER_NAME}'"))
        else:
            self.stdout.write("  No VMware seed provider found.")

    def _seed(self):
        self.stdout.write(self.style.MIGRATE_HEADING("Seeding VMware vSphere inventory..."))

        # Get or create org
        org, _ = Organization.objects.get_or_create(
            name="Default",
            defaults={"description": "Default organization"},
        )

        # Create provider
        provider, created = Provider.objects.get_or_create(
            name=PROVIDER_NAME,
            defaults={
                "infrastructure": "private_cloud",
                "vendor": "vmware",
                "provider_type": "vcenter",
                "endpoint": "https://vcsa01.lab.local/sdk",
                "credential_ref": "aap-credential://vmware-vcenter-lab",
                "enabled": True,
                "connection_config": {
                    "validate_certs": False,
                    "port": 443,
                    "datacenter": "Lab-DC1",
                    "username": "administrator@vsphere.local",
                },
                "organization": org,
                "last_refresh_at": timezone.now(),
            },
        )
        action = "Created" if created else "Found existing"
        self.stdout.write(f"  {action} provider: {provider.name} ({provider.id})")

        # Create a completed collection run
        run = CollectionRun.objects.create(
            provider=provider,
            collection_type="full",
            status="completed",
            completed_at=timezone.now(),
            collector_version="0.1.0-dev",
            ansible_collection="vmware.vmware",
        )

        # Look up resource types
        rt = {}
        for slug in ["virtual_machine", "hypervisor_host", "block_storage",
                      "container_orchestration_platform", "auto_scaling_group"]:
            try:
                rt[slug] = ResourceType.objects.get(slug=slug)
            except ResourceType.DoesNotExist:
                self.stderr.write(self.style.ERROR(
                    f"  ResourceType '{slug}' not found. Run migrations first."))
                return

        resources = {}  # name -> Resource for relationship building

        for dc_data in DATACENTERS:
            dc_name = dc_data["name"]
            self.stdout.write(f"\n  Datacenter: {dc_name}")

            for cluster_data in dc_data["clusters"]:
                # Clusters as container_orchestration_platform
                cluster = Resource.objects.create(
                    resource_type=rt["container_orchestration_platform"],
                    provider=provider,
                    name=cluster_data["name"],
                    ems_ref=cluster_data["moid"],
                    vendor_type="vSphere Cluster",
                    state="active",
                    region=dc_name,
                    properties={
                        "ha_enabled": cluster_data["ha_enabled"],
                        "drs_enabled": cluster_data["drs_enabled"],
                        "vsphere_type": "ClusterComputeResource",
                    },
                    collection_run=run,
                    organization=org,
                )
                resources[cluster_data["name"]] = cluster
                self.stdout.write(f"    Cluster: {cluster.name}")

                # Hosts
                for host_data in cluster_data["hosts"]:
                    host = Resource.objects.create(
                        resource_type=rt["hypervisor_host"],
                        provider=provider,
                        name=host_data["name"],
                        ems_ref=host_data["moid"],
                        vendor_type="ESXi Host",
                        state="active",
                        power_state="poweredOn",
                        region=dc_name,
                        cpu_count=host_data["cpu_count"],
                        memory_mb=host_data["memory_mb"],
                        ip_addresses=[host_data["ip"]],
                        fqdn=host_data["name"],
                        os_type="hypervisor",
                        os_name=host_data["os_name"],
                        properties={
                            "hardware_model": host_data["model"],
                            "hardware_vendor": host_data["vendor"],
                            "serial_number": host_data["serial"],
                            "vsphere_type": "HostSystem",
                            "cluster": cluster_data["name"],
                        },
                        ansible_host=host_data["ip"],
                        ansible_connection="ssh",
                        inventory_group="esxi_hosts",
                        collection_run=run,
                        organization=org,
                    )
                    resources[host_data["name"]] = host
                    self.stdout.write(f"      Host: {host.name} ({host_data['cpu_count']} CPU, {host_data['memory_mb'] // 1024}GB RAM)")

                    # host → cluster: part_of
                    ResourceRelationship.objects.create(
                        source=host, target=cluster,
                        relationship_type="part_of",
                    )

                # Resource pools
                for pool_data in cluster_data["resource_pools"]:
                    pool = Resource.objects.create(
                        resource_type=rt["auto_scaling_group"],
                        provider=provider,
                        name=pool_data["name"],
                        ems_ref=pool_data["moid"],
                        vendor_type="vSphere Resource Pool",
                        state="active",
                        region=dc_name,
                        properties={
                            "cpu_limit_mhz": pool_data["cpu_limit"],
                            "memory_limit_mb": pool_data["memory_limit_mb"],
                            "vsphere_type": "ResourcePool",
                            "cluster": cluster_data["name"],
                        },
                        collection_run=run,
                        organization=org,
                    )
                    resources[pool_data["name"]] = pool
                    self.stdout.write(f"      Pool: {pool.name}")

                    # pool → cluster: part_of
                    ResourceRelationship.objects.create(
                        source=pool, target=cluster,
                        relationship_type="part_of",
                    )

            # Datastores
            for ds_data in dc_data["datastores"]:
                ds = Resource.objects.create(
                    resource_type=rt["block_storage"],
                    provider=provider,
                    name=ds_data["name"],
                    ems_ref=ds_data["moid"],
                    vendor_type="vSphere Datastore",
                    state="active",
                    region=dc_name,
                    disk_gb=ds_data["capacity_gb"],
                    properties={
                        "datastore_type": ds_data["type"],
                        "capacity_gb": ds_data["capacity_gb"],
                        "free_space_gb": ds_data["free_gb"],
                        "provisioned_pct": round((1 - ds_data["free_gb"] / ds_data["capacity_gb"]) * 100, 1),
                        "vsphere_type": "Datastore",
                    },
                    collection_run=run,
                    organization=org,
                )
                resources[ds_data["name"]] = ds
                self.stdout.write(f"    Datastore: {ds.name} ({ds_data['type']}, {ds_data['capacity_gb']}GB)")

        # VMs
        self.stdout.write(f"\n  Virtual Machines:")
        for vm_data in VMS:
            mac = f"00:50:56:{uuid.uuid4().hex[:2]}:{uuid.uuid4().hex[:2]}:{uuid.uuid4().hex[:2]}"
            vm = Resource.objects.create(
                resource_type=rt["virtual_machine"],
                provider=provider,
                name=vm_data["name"],
                ems_ref=vm_data["moid"],
                vendor_type="vSphere VM",
                state=vm_data["state"],
                power_state=vm_data["power"],
                region="Lab-DC1",
                cpu_count=vm_data["cpu"],
                memory_mb=vm_data["mem"],
                disk_gb=vm_data["disk"],
                ip_addresses=vm_data["ip"],
                fqdn=vm_data["fqdn"],
                mac_addresses=[mac],
                os_type=vm_data["os_type"],
                os_name=vm_data["os_name"],
                properties={
                    "vsphere_type": "VirtualMachine",
                    "cluster": vm_data["cluster"],
                    "host": vm_data["host"],
                    "resource_pool": vm_data["pool"],
                    "datastore": vm_data["datastore"],
                    "tools_status": "guestToolsRunning" if vm_data["power"] == "poweredOn" else "guestToolsNotRunning",
                    "tools_version": "12352" if vm_data["power"] == "poweredOn" else "",
                    "hardware_version": "vmx-21",
                },
                provider_tags=vm_data["tags"],
                ansible_host=vm_data["ip"][0] if vm_data["ip"] else "",
                ansible_connection=vm_data.get("ansible_conn", ""),
                inventory_group=vm_data.get("ansible_group", ""),
                collection_run=run,
                organization=org,
            )
            resources[vm_data["name"]] = vm
            state_icon = "🟢" if vm_data["state"] == "running" else "🔴" if vm_data["state"] == "stopped" else "🟡"
            self.stdout.write(f"    {state_icon} {vm.name} ({vm_data['os_name']}, {vm_data['cpu']}vCPU/{vm_data['mem']//1024}GB)")

            # VM → host: runs_on
            if vm_data["host"] in resources:
                ResourceRelationship.objects.create(
                    source=vm, target=resources[vm_data["host"]],
                    relationship_type="runs_on",
                )

            # VM → datastore: attached_to
            if vm_data["datastore"] in resources:
                ResourceRelationship.objects.create(
                    source=vm, target=resources[vm_data["datastore"]],
                    relationship_type="attached_to",
                )

            # VM → resource pool: member_of
            if vm_data["pool"] in resources:
                ResourceRelationship.objects.create(
                    source=vm, target=resources[vm_data["pool"]],
                    relationship_type="member_of",
                )

        # Update collection run stats
        total = Resource.objects.filter(provider=provider).count()
        rels = ResourceRelationship.objects.filter(source__provider=provider).count()
        run.resources_found = total
        run.resources_created = total
        run.save(update_fields=["resources_found", "resources_created"])

        self.stdout.write("\n" + self.style.SUCCESS(
            f"Done! Seeded {total} resources and {rels} relationships for '{PROVIDER_NAME}'"
        ))
        self.stdout.write(f"  Provider ID: {provider.id}")
        self.stdout.write(f"  Collection Run ID: {run.id}")
