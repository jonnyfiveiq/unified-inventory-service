"""Management command: seed_multivendor_data

Seeds realistic inventory data for multiple cloud and infrastructure vendors:
  - AWS EC2 (us-east-1 VPC with EC2 instances, EBS, RDS, EKS, S3)
  - Azure (West Europe VNet with VMs, Managed Disks, AKS, Blob Storage)
  - GCP (us-central1 VPC with Compute Engine instances, Persistent Disks, GKE)
  - OpenStack (Nova instances, Cinder volumes, Neutron networks)
  - OpenShift (Worker nodes, KubeVirt VMs, Pods via CNV)

Usage:
    python manage.py seed_multivendor_data              # seed all vendors
    python manage.py seed_multivendor_data --flush       # flush and re-seed
    python manage.py seed_multivendor_data --flush-only  # flush without re-seeding
    python manage.py seed_multivendor_data --vendor aws  # seed only AWS
"""

import uuid
import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.models import Organization
from apps.inventory.models import (
    CollectionRun,
    Provider,
    Resource,
    ResourceRelationship,
    ResourceSighting,
    ResourceType,
)


# Deterministic UUIDs for canonical_id (seeded from name)
def _canon(name):
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, name))


def _bios(name):
    return str(uuid.uuid5(uuid.NAMESPACE_OID, name))


# ━━━ AWS EC2 Data ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

AWS_PROVIDER = {
    "name": "AWS Production - us-east-1", "vendor": "aws",
    "infrastructure": "public_cloud", "provider_type": "ec2",
    "endpoint": "https://ec2.us-east-1.amazonaws.com",
    "credential_ref": "aap-credential://aws-prod",
    "connection_config": {"region": "us-east-1", "assume_role_arn": ""},
}

AWS_RESOURCES = [
    {"name": "prod-vpc", "type": "vpc", "vendor_type": "VPC", "ems_ref": "vpc-0a1b2c3d4e5f",
     "state": "active", "region": "us-east-1",
     "properties": {"cidr_block": "10.0.0.0/16", "is_default": False, "enable_dns_support": True}},
    {"name": "web-sg", "type": "security_group", "vendor_type": "Security Group", "ems_ref": "sg-web01",
     "state": "active", "region": "us-east-1",
     "properties": {"inbound_rules": [{"port": 443, "protocol": "tcp", "source": "0.0.0.0/0"}]}},
    {"name": "db-sg", "type": "security_group", "vendor_type": "Security Group", "ems_ref": "sg-db01",
     "state": "active", "region": "us-east-1",
     "properties": {"inbound_rules": [{"port": 5432, "protocol": "tcp", "source": "10.0.0.0/16"}]}},
    {"name": "web-prod-01", "type": "virtual_machine", "vendor_type": "EC2 Instance",
     "ems_ref": "i-0aabbccdd01", "state": "running", "power_state": "on",
     "region": "us-east-1", "availability_zone": "us-east-1a",
     "cpu_count": 4, "memory_mb": 16384, "disk_gb": 100,
     "os_type": "linux", "os_name": "Red Hat Enterprise Linux 9.3",
     "ip_addresses": ["10.0.1.10", "54.82.100.10"], "fqdn": "web-prod-01.ec2.internal",
     "flavor": "m5.xlarge", "cloud_tenant": "123456789012",
     "boot_time": -3, "ems_created_on": -90,
     "vendor_identifiers": {"instance_id": "i-0aabbccdd01", "smbios_uuid": None},
     "properties": {"instance_type": "m5.xlarge", "ami_id": "ami-rhel93-001",
                     "subnet_id": "subnet-pub-1a", "ebs_optimized": True, "iam_instance_profile": "web-role"}},
    {"name": "web-prod-02", "type": "virtual_machine", "vendor_type": "EC2 Instance",
     "ems_ref": "i-0aabbccdd02", "state": "running", "power_state": "on",
     "region": "us-east-1", "availability_zone": "us-east-1b",
     "cpu_count": 4, "memory_mb": 16384, "disk_gb": 100,
     "os_type": "linux", "os_name": "Red Hat Enterprise Linux 9.3",
     "ip_addresses": ["10.0.2.10", "54.82.100.11"], "fqdn": "web-prod-02.ec2.internal",
     "flavor": "m5.xlarge", "cloud_tenant": "123456789012",
     "boot_time": -5, "ems_created_on": -90,
     "vendor_identifiers": {"instance_id": "i-0aabbccdd02", "smbios_uuid": None},
     "properties": {"instance_type": "m5.xlarge", "ami_id": "ami-rhel93-001",
                     "subnet_id": "subnet-pub-1b", "ebs_optimized": True}},
    {"name": "db-prod-01", "type": "virtual_machine", "vendor_type": "EC2 Instance",
     "ems_ref": "i-0aabbccdd03", "state": "running", "power_state": "on",
     "region": "us-east-1", "availability_zone": "us-east-1a",
     "cpu_count": 8, "memory_mb": 32768, "disk_gb": 500,
     "os_type": "linux", "os_name": "Red Hat Enterprise Linux 9.3",
     "ip_addresses": ["10.0.10.20"], "fqdn": "db-prod-01.ec2.internal",
     "flavor": "r5.2xlarge", "cloud_tenant": "123456789012",
     "boot_time": -30, "ems_created_on": -180,
     "vendor_identifiers": {"instance_id": "i-0aabbccdd03", "smbios_uuid": None},
     "properties": {"instance_type": "r5.2xlarge", "ami_id": "ami-rhel93-002",
                     "subnet_id": "subnet-priv-1a", "ebs_optimized": True}},
    {"name": "batch-worker-01", "type": "virtual_machine", "vendor_type": "EC2 Instance",
     "ems_ref": "i-0aabbccdd04", "state": "stopped", "power_state": "off",
     "region": "us-east-1", "availability_zone": "us-east-1a",
     "cpu_count": 16, "memory_mb": 65536, "disk_gb": 200,
     "os_type": "linux", "os_name": "Amazon Linux 2023",
     "ip_addresses": ["10.0.10.50"], "fqdn": "batch-worker-01.ec2.internal",
     "flavor": "c5.4xlarge", "cloud_tenant": "123456789012",
     "boot_time": -60, "ems_created_on": -120,
     "vendor_identifiers": {"instance_id": "i-0aabbccdd04", "smbios_uuid": None},
     "properties": {"instance_type": "c5.4xlarge", "ami_id": "ami-al2023-001"}},
    {"name": "web-prod-01-root", "type": "block_storage", "vendor_type": "EBS Volume",
     "ems_ref": "vol-ebs001", "state": "active", "region": "us-east-1", "disk_gb": 100,
     "properties": {"volume_type": "gp3", "iops": 3000, "encrypted": True}},
    {"name": "db-prod-01-data", "type": "block_storage", "vendor_type": "EBS Volume",
     "ems_ref": "vol-ebs002", "state": "active", "region": "us-east-1", "disk_gb": 500,
     "properties": {"volume_type": "io2", "iops": 10000, "encrypted": True}},
    {"name": "prod-artifacts-bucket", "type": "object_storage", "vendor_type": "S3 Bucket",
     "ems_ref": "prod-artifacts-bucket", "state": "active", "region": "us-east-1",
     "properties": {"versioning": True, "encryption": "AES256", "public_access_blocked": True}},
    {"name": "prod-eks-cluster", "type": "container_orchestration_platform", "vendor_type": "EKS Cluster",
     "ems_ref": "eks-prod-01", "state": "active", "region": "us-east-1",
     "properties": {"kubernetes_version": "1.29", "endpoint": "https://EKS-PROD.us-east-1.eks.amazonaws.com",
                     "node_count": 6, "platform_version": "eks.8"}},
    {"name": "prod-postgres-rds", "type": "relational_db", "vendor_type": "RDS Instance",
     "ems_ref": "prod-postgres-rds", "state": "running", "region": "us-east-1",
     "cpu_count": 4, "memory_mb": 16384, "disk_gb": 200,
     "flavor": "db.r5.xlarge", "cloud_tenant": "123456789012",
     "properties": {"engine": "postgres", "engine_version": "16.1", "multi_az": True,
                     "storage_type": "io1", "storage_encrypted": True}},
    {"name": "prod-web-alb", "type": "load_balancer", "vendor_type": "ELB",
     "ems_ref": "arn:aws:elasticloadbalancing:us-east-1:123:loadbalancer/app/prod-web/abc",
     "state": "active", "region": "us-east-1",
     "properties": {"type": "application", "scheme": "internet-facing",
                     "dns_name": "prod-web-alb.us-east-1.elb.amazonaws.com"}},
]

AWS_RELATIONSHIPS = [
    ("web-prod-01", "web-sg", "member_of"), ("web-prod-02", "web-sg", "member_of"),
    ("db-prod-01", "db-sg", "member_of"),
    ("web-prod-01", "prod-vpc", "part_of"), ("web-prod-02", "prod-vpc", "part_of"),
    ("db-prod-01", "prod-vpc", "part_of"),
    ("web-prod-01-root", "web-prod-01", "attached_to"),
    ("db-prod-01-data", "db-prod-01", "attached_to"),
    ("prod-web-alb", "web-prod-01", "load_balances"),
    ("prod-web-alb", "web-prod-02", "load_balances"),
]


# ━━━ Azure Data ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

AZURE_PROVIDER = {
    "name": "Azure Production - West Europe", "vendor": "azure",
    "infrastructure": "public_cloud", "provider_type": "azure_rm",
    "endpoint": "https://management.azure.com",
    "credential_ref": "aap-credential://azure-prod",
    "connection_config": {"subscription_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                          "tenant_id": "t1e2n3a4-n5t6-7890-abcd-000000000001"},
}

AZURE_RESOURCES = [
    {"name": "prod-vnet", "type": "vpc", "vendor_type": "Virtual Network (VNet)",
     "ems_ref": "/subscriptions/a1b2/resourceGroups/prod-rg/providers/Microsoft.Network/virtualNetworks/prod-vnet",
     "state": "active", "region": "westeurope",
     "cloud_tenant": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
     "properties": {"address_space": ["10.1.0.0/16"], "resource_group": "prod-rg"}},
    {"name": "az-web-01", "type": "virtual_machine", "vendor_type": "Virtual Machine",
     "ems_ref": "/subscriptions/a1b2/resourceGroups/prod-rg/providers/Microsoft.Compute/virtualMachines/az-web-01",
     "state": "running", "power_state": "on", "region": "westeurope", "availability_zone": "1",
     "cpu_count": 4, "memory_mb": 16384, "disk_gb": 128,
     "os_type": "linux", "os_name": "Red Hat Enterprise Linux 9.3",
     "ip_addresses": ["10.1.1.10", "20.82.100.10"], "fqdn": "az-web-01.westeurope.cloudapp.azure.com",
     "flavor": "Standard_D4s_v3", "cloud_tenant": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
     "boot_time": -2, "ems_created_on": -60,
     "vendor_identifiers": {"vm_id": "vm-azure-001", "resource_id": "/subscriptions/a1b2/resourceGroups/prod-rg/providers/Microsoft.Compute/virtualMachines/az-web-01"},
     "properties": {"vm_size": "Standard_D4s_v3", "resource_group": "prod-rg",
                     "os_disk_type": "Premium_LRS", "accelerated_networking": True}},
    {"name": "az-web-02", "type": "virtual_machine", "vendor_type": "Virtual Machine",
     "ems_ref": "/subscriptions/a1b2/resourceGroups/prod-rg/providers/Microsoft.Compute/virtualMachines/az-web-02",
     "state": "running", "power_state": "on", "region": "westeurope", "availability_zone": "2",
     "cpu_count": 4, "memory_mb": 16384, "disk_gb": 128,
     "os_type": "linux", "os_name": "Red Hat Enterprise Linux 9.3",
     "ip_addresses": ["10.1.1.11", "20.82.100.11"], "fqdn": "az-web-02.westeurope.cloudapp.azure.com",
     "flavor": "Standard_D4s_v3", "cloud_tenant": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
     "boot_time": -2, "ems_created_on": -60,
     "vendor_identifiers": {"vm_id": "vm-azure-002"},
     "properties": {"vm_size": "Standard_D4s_v3", "resource_group": "prod-rg"}},
    {"name": "az-db-01", "type": "virtual_machine", "vendor_type": "Virtual Machine",
     "ems_ref": "/subscriptions/a1b2/resourceGroups/prod-rg/providers/Microsoft.Compute/virtualMachines/az-db-01",
     "state": "running", "power_state": "on", "region": "westeurope", "availability_zone": "1",
     "cpu_count": 8, "memory_mb": 65536, "disk_gb": 1024,
     "os_type": "linux", "os_name": "Red Hat Enterprise Linux 9.3",
     "ip_addresses": ["10.1.10.20"], "fqdn": "az-db-01.internal.cloudapp.net",
     "flavor": "Standard_E8s_v3", "cloud_tenant": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
     "boot_time": -14, "ems_created_on": -120,
     "vendor_identifiers": {"vm_id": "vm-azure-003"},
     "properties": {"vm_size": "Standard_E8s_v3", "resource_group": "prod-rg",
                     "os_disk_type": "Premium_LRS", "data_disks": 4}},
    {"name": "az-win-ad-01", "type": "virtual_machine", "vendor_type": "Virtual Machine",
     "ems_ref": "/subscriptions/a1b2/resourceGroups/prod-rg/providers/Microsoft.Compute/virtualMachines/az-win-ad-01",
     "state": "running", "power_state": "on", "region": "westeurope", "availability_zone": "1",
     "cpu_count": 4, "memory_mb": 16384, "disk_gb": 256,
     "os_type": "windows", "os_name": "Windows Server 2022 Datacenter",
     "ip_addresses": ["10.1.10.5"], "fqdn": "az-win-ad-01.corp.local",
     "flavor": "Standard_D4s_v3", "cloud_tenant": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
     "boot_time": -30, "ems_created_on": -365,
     "vendor_identifiers": {"vm_id": "vm-azure-004"},
     "properties": {"vm_size": "Standard_D4s_v3", "resource_group": "prod-rg",
                     "os_disk_type": "Premium_LRS", "license_type": "Windows_Server"}},
    {"name": "az-db-01-data-disk-1", "type": "block_storage", "vendor_type": "Managed Disk",
     "ems_ref": "/subscriptions/a1b2/resourceGroups/prod-rg/providers/Microsoft.Compute/disks/az-db-01-data-1",
     "state": "active", "region": "westeurope", "disk_gb": 512,
     "cloud_tenant": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
     "properties": {"sku": "Premium_LRS", "disk_state": "Attached", "encryption": "SSE"}},
    {"name": "prod-aks-cluster", "type": "container_orchestration_platform",
     "vendor_type": "Azure Kubernetes Service",
     "ems_ref": "/subscriptions/a1b2/resourceGroups/prod-rg/providers/Microsoft.ContainerService/managedClusters/prod-aks",
     "state": "active", "region": "westeurope",
     "cloud_tenant": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
     "properties": {"kubernetes_version": "1.29.2", "node_count": 5,
                     "node_vm_size": "Standard_D4s_v3", "network_plugin": "azure"}},
    {"name": "prod-azure-sql", "type": "relational_db", "vendor_type": "Azure SQL",
     "ems_ref": "/subscriptions/a1b2/resourceGroups/prod-rg/providers/Microsoft.Sql/servers/prod-sql/databases/appdb",
     "state": "running", "region": "westeurope",
     "cloud_tenant": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
     "properties": {"edition": "GeneralPurpose", "service_tier": "GP_Gen5_4",
                     "max_size_gb": 500, "geo_redundant_backup": True}},
    {"name": "prod-azure-lb", "type": "load_balancer", "vendor_type": "Azure Load Balancer",
     "ems_ref": "/subscriptions/a1b2/resourceGroups/prod-rg/providers/Microsoft.Network/loadBalancers/prod-lb",
     "state": "active", "region": "westeurope",
     "cloud_tenant": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
     "properties": {"sku": "Standard", "type": "Public", "frontend_ip_count": 1}},
]

AZURE_RELATIONSHIPS = [
    ("az-web-01", "prod-vnet", "part_of"), ("az-web-02", "prod-vnet", "part_of"),
    ("az-db-01", "prod-vnet", "part_of"), ("az-win-ad-01", "prod-vnet", "part_of"),
    ("az-db-01-data-disk-1", "az-db-01", "attached_to"),
    ("prod-azure-lb", "az-web-01", "load_balances"),
    ("prod-azure-lb", "az-web-02", "load_balances"),
]


# ━━━ GCP Data ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GCP_PROVIDER = {
    "name": "GCP Production - us-central1", "vendor": "gcp",
    "infrastructure": "public_cloud", "provider_type": "gce",
    "endpoint": "https://compute.googleapis.com",
    "credential_ref": "aap-credential://gcp-prod",
    "connection_config": {"project_id": "acme-prod-123456", "region": "us-central1"},
}

GCP_RESOURCES = [
    {"name": "prod-vpc-network", "type": "vpc", "vendor_type": "VPC Network",
     "ems_ref": "projects/acme-prod-123456/global/networks/prod-vpc",
     "state": "active", "region": "us-central1",
     "properties": {"routing_mode": "REGIONAL", "auto_create_subnetworks": False,
                     "subnet_cidr": "10.2.0.0/16"}},
    {"name": "gcp-web-01", "type": "virtual_machine", "vendor_type": "Compute Engine Instance",
     "ems_ref": "projects/acme-prod-123456/zones/us-central1-a/instances/gcp-web-01",
     "state": "running", "power_state": "on",
     "region": "us-central1", "availability_zone": "us-central1-a",
     "cpu_count": 4, "memory_mb": 16384, "disk_gb": 100,
     "os_type": "linux", "os_name": "Red Hat Enterprise Linux 9",
     "ip_addresses": ["10.2.1.10", "35.192.100.10"], "fqdn": "gcp-web-01.us-central1-a.c.acme-prod.internal",
     "flavor": "n2-standard-4", "cloud_tenant": "acme-prod-123456",
     "boot_time": -4, "ems_created_on": -45,
     "vendor_identifiers": {"instance_id": "1234567890123456781"},
     "properties": {"machine_type": "n2-standard-4", "preemptible": False,
                     "network_tier": "PREMIUM", "service_account": "web-sa@acme-prod.iam.gserviceaccount.com"}},
    {"name": "gcp-web-02", "type": "virtual_machine", "vendor_type": "Compute Engine Instance",
     "ems_ref": "projects/acme-prod-123456/zones/us-central1-b/instances/gcp-web-02",
     "state": "running", "power_state": "on",
     "region": "us-central1", "availability_zone": "us-central1-b",
     "cpu_count": 4, "memory_mb": 16384, "disk_gb": 100,
     "os_type": "linux", "os_name": "Red Hat Enterprise Linux 9",
     "ip_addresses": ["10.2.1.11", "35.192.100.11"], "fqdn": "gcp-web-02.us-central1-b.c.acme-prod.internal",
     "flavor": "n2-standard-4", "cloud_tenant": "acme-prod-123456",
     "boot_time": -4, "ems_created_on": -45,
     "vendor_identifiers": {"instance_id": "1234567890123456782"},
     "properties": {"machine_type": "n2-standard-4", "preemptible": False}},
    {"name": "gcp-ml-gpu-01", "type": "virtual_machine", "vendor_type": "Compute Engine Instance",
     "ems_ref": "projects/acme-prod-123456/zones/us-central1-a/instances/gcp-ml-gpu-01",
     "state": "running", "power_state": "on",
     "region": "us-central1", "availability_zone": "us-central1-a",
     "cpu_count": 12, "memory_mb": 87040, "disk_gb": 500,
     "os_type": "linux", "os_name": "Ubuntu 22.04 LTS",
     "ip_addresses": ["10.2.20.10"], "fqdn": "gcp-ml-gpu-01.us-central1-a.c.acme-prod.internal",
     "flavor": "a2-highgpu-1g", "cloud_tenant": "acme-prod-123456",
     "boot_time": -1, "ems_created_on": -14,
     "vendor_identifiers": {"instance_id": "1234567890123456783"},
     "properties": {"machine_type": "a2-highgpu-1g", "gpu_type": "nvidia-tesla-a100",
                     "gpu_count": 1, "preemptible": False}},
    {"name": "gcp-web-01-boot", "type": "block_storage", "vendor_type": "Persistent Disk",
     "ems_ref": "projects/acme-prod-123456/zones/us-central1-a/disks/gcp-web-01-boot",
     "state": "active", "region": "us-central1", "disk_gb": 100,
     "properties": {"type": "pd-ssd", "status": "READY"}},
    {"name": "prod-gke-cluster", "type": "container_orchestration_platform", "vendor_type": "GKE Cluster",
     "ems_ref": "projects/acme-prod-123456/locations/us-central1/clusters/prod-gke",
     "state": "active", "region": "us-central1",
     "cloud_tenant": "acme-prod-123456",
     "properties": {"kubernetes_version": "1.29.1-gke.200", "node_count": 4,
                     "node_machine_type": "n2-standard-4", "release_channel": "REGULAR"}},
    {"name": "prod-cloudsql", "type": "relational_db", "vendor_type": "Cloud SQL Instance",
     "ems_ref": "projects/acme-prod-123456/instances/prod-cloudsql",
     "state": "running", "region": "us-central1",
     "cloud_tenant": "acme-prod-123456",
     "properties": {"database_version": "POSTGRES_16", "tier": "db-custom-4-16384",
                     "storage_type": "SSD", "high_availability": True}},
    {"name": "prod-gcs-bucket", "type": "object_storage", "vendor_type": "Cloud Storage Bucket",
     "ems_ref": "acme-prod-artifacts", "state": "active", "region": "us-central1",
     "properties": {"storage_class": "STANDARD", "versioning": True, "uniform_access": True}},
]

GCP_RELATIONSHIPS = [
    ("gcp-web-01", "prod-vpc-network", "part_of"), ("gcp-web-02", "prod-vpc-network", "part_of"),
    ("gcp-ml-gpu-01", "prod-vpc-network", "part_of"),
    ("gcp-web-01-boot", "gcp-web-01", "attached_to"),
]


# ━━━ OpenStack Data ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OPENSTACK_PROVIDER = {
    "name": "OpenStack Private Cloud - RegionOne", "vendor": "openstack",
    "infrastructure": "private_cloud", "provider_type": "openstack",
    "endpoint": "https://openstack.corp.local:5000/v3",
    "credential_ref": "aap-credential://openstack-prod",
    "connection_config": {"region": "RegionOne", "domain": "default", "project": "production"},
}

OPENSTACK_RESOURCES = [
    {"name": "prod-network", "type": "vpc", "vendor_type": "Neutron Network",
     "ems_ref": "net-neutron-001", "state": "active", "region": "RegionOne",
     "cloud_tenant": "project-prod-001",
     "properties": {"network_type": "vxlan", "segmentation_id": 100, "shared": False,
                     "subnet_cidr": "192.168.0.0/24", "dns_nameservers": ["10.0.0.2"]}},
    {"name": "ostack-controller-01", "type": "virtual_machine", "vendor_type": "Nova Instance",
     "ems_ref": "srv-nova-001", "state": "running", "power_state": "on",
     "region": "RegionOne", "availability_zone": "nova",
     "cpu_count": 8, "memory_mb": 32768, "disk_gb": 200,
     "os_type": "linux", "os_name": "Red Hat Enterprise Linux 9.3",
     "ip_addresses": ["192.168.0.10", "10.100.1.10"], "fqdn": "ostack-controller-01.corp.local",
     "flavor": "m1.xlarge", "cloud_tenant": "project-prod-001",
     "boot_time": -7, "ems_created_on": -200,
     "vendor_identifiers": {"server_id": "srv-nova-001"},
     "properties": {"flavor_name": "m1.xlarge", "image_name": "rhel-9.3-x86_64",
                     "key_name": "prod-keypair", "security_groups": ["default", "web-sg"]}},
    {"name": "ostack-worker-01", "type": "virtual_machine", "vendor_type": "Nova Instance",
     "ems_ref": "srv-nova-002", "state": "running", "power_state": "on",
     "region": "RegionOne", "availability_zone": "nova",
     "cpu_count": 4, "memory_mb": 16384, "disk_gb": 100,
     "os_type": "linux", "os_name": "Red Hat Enterprise Linux 9.3",
     "ip_addresses": ["192.168.0.20"], "fqdn": "ostack-worker-01.corp.local",
     "flavor": "m1.large", "cloud_tenant": "project-prod-001",
     "boot_time": -7, "ems_created_on": -200,
     "vendor_identifiers": {"server_id": "srv-nova-002"},
     "properties": {"flavor_name": "m1.large", "image_name": "rhel-9.3-x86_64"}},
    {"name": "ostack-worker-02", "type": "virtual_machine", "vendor_type": "Nova Instance",
     "ems_ref": "srv-nova-003", "state": "running", "power_state": "on",
     "region": "RegionOne", "availability_zone": "nova",
     "cpu_count": 4, "memory_mb": 16384, "disk_gb": 100,
     "os_type": "linux", "os_name": "Red Hat Enterprise Linux 9.3",
     "ip_addresses": ["192.168.0.21"], "fqdn": "ostack-worker-02.corp.local",
     "flavor": "m1.large", "cloud_tenant": "project-prod-001",
     "boot_time": -7, "ems_created_on": -200,
     "vendor_identifiers": {"server_id": "srv-nova-003"},
     "properties": {"flavor_name": "m1.large", "image_name": "rhel-9.3-x86_64"}},
    {"name": "ostack-data-vol-01", "type": "block_storage", "vendor_type": "Cinder Volume",
     "ems_ref": "vol-cinder-001", "state": "active", "region": "RegionOne", "disk_gb": 500,
     "cloud_tenant": "project-prod-001",
     "properties": {"volume_type": "ceph-ssd", "status": "in-use", "bootable": False}},
    {"name": "ostack-default-sg", "type": "security_group", "vendor_type": "Neutron Security Group",
     "ems_ref": "sg-neutron-001", "state": "active", "region": "RegionOne",
     "cloud_tenant": "project-prod-001",
     "properties": {"rules": [{"direction": "ingress", "protocol": "tcp", "port_min": 22, "port_max": 22}]}},
    {"name": "ostack-heat-stack", "type": "orchestration_stack", "vendor_type": "Heat Stack",
     "ems_ref": "stack-heat-001", "state": "active", "region": "RegionOne",
     "cloud_tenant": "project-prod-001",
     "properties": {"stack_name": "prod-infra", "template_description": "Production infrastructure",
                     "stack_status": "CREATE_COMPLETE"}},
]

OPENSTACK_RELATIONSHIPS = [
    ("ostack-controller-01", "prod-network", "part_of"),
    ("ostack-worker-01", "prod-network", "part_of"),
    ("ostack-worker-02", "prod-network", "part_of"),
    ("ostack-data-vol-01", "ostack-controller-01", "attached_to"),
    ("ostack-controller-01", "ostack-default-sg", "member_of"),
    ("ostack-worker-01", "ostack-default-sg", "member_of"),
    ("ostack-worker-02", "ostack-default-sg", "member_of"),
]


# ━━━ OpenShift Data ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OPENSHIFT_PROVIDER = {
    "name": "OpenShift Production - ocp4.prod.local", "vendor": "openshift",
    "infrastructure": "on_premise", "provider_type": "openshift",
    "endpoint": "https://api.ocp4.prod.local:6443",
    "credential_ref": "aap-credential://ocp-prod",
    "connection_config": {"cluster_name": "ocp4-prod", "api_version": "v1"},
}

OPENSHIFT_RESOURCES = [
    {"name": "ocp-sdn", "type": "vpc", "vendor_type": "OpenShift SDN",
     "ems_ref": "ocp-sdn-prod", "state": "active", "region": "ocp4.prod.local",
     "properties": {"network_type": "OVNKubernetes", "cluster_network_cidr": "10.128.0.0/14",
                     "service_network_cidr": "172.30.0.0/16"}},
    {"name": "ocp-worker-01", "type": "physical_server", "vendor_type": "Worker Node",
     "ems_ref": "node/ocp-worker-01.prod.local", "state": "running", "power_state": "on",
     "region": "ocp4.prod.local",
     "cpu_count": 16, "memory_mb": 65536, "disk_gb": 500,
     "os_type": "linux", "os_name": "Red Hat CoreOS 4.14",
     "ip_addresses": ["10.10.1.21"], "fqdn": "ocp-worker-01.prod.local",
     "boot_time": -30, "ems_created_on": -365,
     "properties": {"kubelet_version": "v1.27.8+4fab27b", "container_runtime": "cri-o",
                     "node_labels": {"node-role.kubernetes.io/worker": ""},
                     "allocatable_pods": 250}},
    {"name": "ocp-worker-02", "type": "physical_server", "vendor_type": "Worker Node",
     "ems_ref": "node/ocp-worker-02.prod.local", "state": "running", "power_state": "on",
     "region": "ocp4.prod.local",
     "cpu_count": 16, "memory_mb": 65536, "disk_gb": 500,
     "os_type": "linux", "os_name": "Red Hat CoreOS 4.14",
     "ip_addresses": ["10.10.1.22"], "fqdn": "ocp-worker-02.prod.local",
     "boot_time": -30, "ems_created_on": -365,
     "properties": {"kubelet_version": "v1.27.8+4fab27b", "container_runtime": "cri-o"}},
    {"name": "ocp-worker-03", "type": "physical_server", "vendor_type": "Worker Node",
     "ems_ref": "node/ocp-worker-03.prod.local", "state": "running", "power_state": "on",
     "region": "ocp4.prod.local",
     "cpu_count": 16, "memory_mb": 65536, "disk_gb": 500,
     "os_type": "linux", "os_name": "Red Hat CoreOS 4.14",
     "ip_addresses": ["10.10.1.23"], "fqdn": "ocp-worker-03.prod.local",
     "boot_time": -30, "ems_created_on": -365,
     "properties": {"kubelet_version": "v1.27.8+4fab27b", "container_runtime": "cri-o"}},
    {"name": "cnv-rhel-db-01", "type": "virtual_machine", "vendor_type": "OpenShift VM (KubeVirt/CNV)",
     "ems_ref": "vm/cnv-prod/cnv-rhel-db-01", "state": "running", "power_state": "on",
     "region": "ocp4.prod.local",
     "cpu_count": 4, "memory_mb": 16384, "disk_gb": 200,
     "os_type": "linux", "os_name": "Red Hat Enterprise Linux 9.3",
     "ip_addresses": ["10.128.2.50"], "fqdn": "cnv-rhel-db-01.cnv-prod.svc.cluster.local",
     "boot_time": -10, "ems_created_on": -90,
     "vendor_identifiers": {"vm_uid": "cnv-uid-db-001"},
     "properties": {"namespace": "cnv-prod", "vmi_phase": "Running",
                     "live_migratable": True, "eviction_strategy": "LiveMigrate"}},
    {"name": "cnv-win-legacy-01", "type": "virtual_machine", "vendor_type": "OpenShift VM (KubeVirt/CNV)",
     "ems_ref": "vm/cnv-prod/cnv-win-legacy-01", "state": "running", "power_state": "on",
     "region": "ocp4.prod.local",
     "cpu_count": 4, "memory_mb": 8192, "disk_gb": 100,
     "os_type": "windows", "os_name": "Windows Server 2019 Standard",
     "ip_addresses": ["10.128.2.60"], "fqdn": "cnv-win-legacy-01.cnv-prod.svc.cluster.local",
     "boot_time": -10, "ems_created_on": -180,
     "vendor_identifiers": {"vm_uid": "cnv-uid-win-001"},
     "properties": {"namespace": "cnv-prod", "vmi_phase": "Running",
                     "live_migratable": False, "eviction_strategy": "None"}},
    {"name": "ocp4-kubernetes", "type": "container_orchestration_platform",
     "vendor_type": "OpenShift Kubernetes",
     "ems_ref": "cluster/ocp4-prod", "state": "active", "region": "ocp4.prod.local",
     "properties": {"kubernetes_version": "v1.27.8+4fab27b", "openshift_version": "4.14.12",
                     "platform": "BareMetal", "channel": "stable-4.14"}},
    {"name": "ocp-rook-ceph", "type": "block_storage", "vendor_type": "Rook+Ceph Block Storage",
     "ems_ref": "storageclass/ocs-storagecluster-ceph-rbd",
     "state": "active", "region": "ocp4.prod.local", "disk_gb": 2048,
     "properties": {"provisioner": "openshift-storage.rbd.csi.ceph.com",
                     "reclaim_policy": "Delete", "volume_binding_mode": "Immediate"}},
]

OPENSHIFT_RELATIONSHIPS = [
    ("ocp-worker-01", "ocp-sdn", "part_of"), ("ocp-worker-02", "ocp-sdn", "part_of"),
    ("ocp-worker-03", "ocp-sdn", "part_of"),
    ("cnv-rhel-db-01", "ocp-worker-01", "hosted_on"),
    ("cnv-win-legacy-01", "ocp-worker-02", "hosted_on"),
    ("ocp-rook-ceph", "cnv-rhel-db-01", "attached_to"),
]


# ━━━ Vendor Registry ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

VENDOR_REGISTRY = {
    "aws": (AWS_PROVIDER, AWS_RESOURCES, AWS_RELATIONSHIPS),
    "azure": (AZURE_PROVIDER, AZURE_RESOURCES, AZURE_RELATIONSHIPS),
    "gcp": (GCP_PROVIDER, GCP_RESOURCES, GCP_RELATIONSHIPS),
    "openstack": (OPENSTACK_PROVIDER, OPENSTACK_RESOURCES, OPENSTACK_RELATIONSHIPS),
    "openshift": (OPENSHIFT_PROVIDER, OPENSHIFT_RESOURCES, OPENSHIFT_RELATIONSHIPS),
}


class Command(BaseCommand):
    help = "Seed multi-vendor inventory data (AWS, Azure, GCP, OpenStack, OpenShift)"

    def add_arguments(self, parser):
        parser.add_argument("--flush", action="store_true", help="Flush existing multivendor data before seeding")
        parser.add_argument("--flush-only", action="store_true", help="Flush without re-seeding")
        parser.add_argument("--vendor", type=str, choices=list(VENDOR_REGISTRY.keys()),
                            help="Seed only a specific vendor")

    def handle(self, *args, **options):
        if options["flush"] or options["flush_only"]:
            self._flush(options.get("vendor"))
            if options["flush_only"]:
                return

        vendors = [options["vendor"]] if options.get("vendor") else list(VENDOR_REGISTRY.keys())
        org = Organization.objects.first()
        if not org:
            self.stderr.write("No Organization found. Run seed_vmware_data first.")
            return

        for vendor_key in vendors:
            prov_data, resources_data, rels_data = VENDOR_REGISTRY[vendor_key]
            self._seed_vendor(org, vendor_key, prov_data, resources_data, rels_data)

        self.stdout.write(self.style.SUCCESS(f"Seeded {len(vendors)} vendor(s) successfully."))

    def _flush(self, vendor_filter=None):
        vendors = [vendor_filter] if vendor_filter else list(VENDOR_REGISTRY.keys())
        for vk in vendors:
            prov_data = VENDOR_REGISTRY[vk][0]
            provs = Provider.objects.filter(name=prov_data["name"])
            if provs.exists():
                # Cascade deletes resources, sightings, relationships via FK
                count = provs.count()
                provs.delete()
                self.stdout.write(f"Flushed {count} provider(s) for {vk}")

    def _seed_vendor(self, org, vendor_key, prov_data, resources_data, rels_data):
        now = timezone.now()

        # ── Create Provider ────────────────────────────────────────────
        provider, created = Provider.objects.get_or_create(
            name=prov_data["name"], organization=org,
            defaults={
                "vendor": prov_data["vendor"],
                "infrastructure": prov_data["infrastructure"],
                "provider_type": prov_data["provider_type"],
                "endpoint": prov_data["endpoint"],
                "credential_ref": prov_data["credential_ref"],
                "connection_config": prov_data.get("connection_config", {}),
                "enabled": True,
                "last_refresh_at": now,
            },
        )
        status = "created" if created else "exists"
        self.stdout.write(f"  Provider '{provider.name}' [{status}]")

        # ── Historical collection runs (7 days) ────────────────────────
        runs = []
        for days_ago in range(7, -1, -1):
            run_time = now - timedelta(days=days_ago)
            run = CollectionRun.objects.create(
                provider=provider,
                completed_at=run_time + timedelta(minutes=2),
                status="completed",
                collection_type="full",
                resources_found=len(resources_data),
                resources_created=len(resources_data) if days_ago == 7 else 0,
                resources_updated=0 if days_ago == 7 else len(resources_data),
            )











            runs.append(run)

        # ── Create Resources ───────────────────────────────────────────
        resource_map = {}
        for rdata in resources_data:
            rt = ResourceType.objects.filter(slug=rdata["type"]).first()
            if not rt:
                self.stderr.write(
                    f"    WARNING: ResourceType slug '{rdata['type']}' not found. Skipping '{rdata['name']}'."
                )
                continue

            # Resolve relative timestamps
            boot_time = None
            if rdata.get("boot_time") is not None:
                boot_time = now + timedelta(days=rdata["boot_time"])
            ems_created_on = None
            if rdata.get("ems_created_on") is not None:
                ems_created_on = now + timedelta(days=rdata["ems_created_on"])

            # Build vendor_identifiers with smbios fallback
            vi = rdata.get("vendor_identifiers", {})
            if vi.get("smbios_uuid") is None and rdata["type"] == "virtual_machine":
                vi["smbios_uuid"] = _bios(rdata["name"])

            resource, rc = Resource.objects.get_or_create(
                canonical_id=_canon(rdata["name"]),
                organization=org,
                defaults={
                    "name": rdata["name"],
                    "resource_type": rt,
                    "provider": provider,
                    "ems_ref": rdata["ems_ref"],
                    "vendor_type": rdata.get("vendor_type", ""),
                    "state": rdata.get("state", "active"),
                    "power_state": rdata.get("power_state", ""),
                    "region": rdata.get("region", ""),
                    "availability_zone": rdata.get("availability_zone", ""),
                    "cpu_count": rdata.get("cpu_count"),
                    "memory_mb": rdata.get("memory_mb"),
                    "disk_gb": rdata.get("disk_gb"),
                    "os_type": rdata.get("os_type", ""),
                    "os_name": rdata.get("os_name", ""),
                    "ip_addresses": rdata.get("ip_addresses", []),
                    "fqdn": rdata.get("fqdn", ""),
                    "flavor": rdata.get("flavor", ""),
                    "cloud_tenant": rdata.get("cloud_tenant", ""),
                    "description": rdata.get("description", ""),
                    "boot_time": boot_time,
                    "ems_created_on": ems_created_on,
                    "vendor_identifiers": vi,
                    "properties": rdata.get("properties", {}),
                    "first_discovered_at": now - timedelta(days=7),
                    "last_seen_at": now,
                },
            )
            resource_map[rdata["name"]] = resource

            # ── Sightings for each collection run ──────────────────────
            for run in runs:
                metrics = {}
                if rdata["type"] == "virtual_machine" and rdata.get("power_state") == "on":
                    metrics = {
                        "cpu_usage_percent": round(random.uniform(15, 85), 1),
                        "memory_usage_percent": round(random.uniform(30, 90), 1),
                    }
                ResourceSighting.objects.get_or_create(
                    resource=resource,
                    collection_run=run,
                    defaults={
                        "state": rdata.get("state", "active"),
                        "power_state": rdata.get("power_state", ""),
                        "cpu_count": rdata.get("cpu_count"),
                        "memory_mb": rdata.get("memory_mb"),
                        "disk_gb": rdata.get("disk_gb"),
                        "metrics": metrics,
                    },
                )

        self.stdout.write(f"    {len(resource_map)} resources seeded")

        # ── Create Relationships ───────────────────────────────────────
        rel_count = 0
        for src_name, tgt_name, rel_type in rels_data:
            src = resource_map.get(src_name)
            tgt = resource_map.get(tgt_name)
            if src and tgt:
                ResourceRelationship.objects.get_or_create(
                    source=src, target=tgt, relationship_type=rel_type,
                )
                rel_count += 1
        self.stdout.write(f"    {rel_count} relationships seeded")
