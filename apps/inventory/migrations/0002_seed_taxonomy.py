"""
Seed data migration: Ansible Normalized Resource Taxonomy v1.0

This migration pre-populates the ResourceCategory, ResourceType, and
VendorTypeMapping tables with the full taxonomy from the Ansible Normalized
Resource Taxonomy document.

This ensures the service deploys with a working, queryable taxonomy so
inventory collectors can immediately start populating resources.
"""

from django.db import migrations

# ─── Taxonomy seed data ────────────────────────────────────────────────────

CATEGORIES = [
    # (slug, name, description, sort_order)
    ("compute", "Compute", "Virtual machines, containers, hypervisors, bare metal, serverless, auto-scaling", 10),
    ("storage", "Storage", "Object, block, file, and archive storage", 20),
    ("database", "Database", "Relational, NoSQL, data warehouse, time series, in-memory", 30),
    ("networking", "Networking", "Switches, routers, firewalls, load balancers, VPCs, DNS, VPNs, SDN", 40),
    ("security_identity", "Security & Identity", "IAM, key management, certificate management, firewall policies", 50),
    ("monitoring", "Monitoring", "Logs, metrics, audit trails", 60),
    ("app_integration", "App Integration & Messaging", "Message queues, pub/sub, event streams, ESBs, API endpoints", 70),
    ("data_processing", "Data Processing & Analytics", "Stream processing, batch processing, data lakes, BI tools", 80),
    ("ai_ml", "AI/ML", "ML platforms, model hosting, inference engines, pre-trained AI services", 90),
    ("devops", "DevOps", "CI/CD, IaC, container registries, code repos, artifact repos", 100),
    ("containers", "Containers", "Container registries and orchestration platforms", 110),
    ("serverless", "Serverless", "Functions and workflow orchestration", 120),
    ("governance_ops", "Governance & Operations", "ITSM, CMDB, cost management, vulnerability management, secrets, DLP", 130),
    ("hybrid_edge", "Hybrid & Edge", "Dedicated connections, edge compute, edge orchestration", 140),
    ("migration", "Migration & Data Transfer", "Data migration, VM migration, data transfer services", 150),
]


# (slug, category_slug, name, is_countable, ltsv, sto, sort_order)
RESOURCE_TYPES = [
    # ─── Compute ───
    ("virtual_machine", "compute", "Virtual Machine", True, 5, 5, 10),
    ("container", "compute", "Container", True, 5, 4, 20),
    ("hypervisor_host", "compute", "Hypervisor Host", True, 5, 5, 30),
    ("bare_metal", "compute", "Bare Metal Server", True, 4, 4, 40),
    ("container_orchestration_platform", "compute", "Container Orchestration Platform", True, 5, 4, 50),
    ("serverless_function", "compute", "Serverless Function", True, 4, 3, 60),
    ("paas_instance", "compute", "PaaS Instance", True, 4, 3, 70),
    ("auto_scaling_group", "compute", "Auto-Scaling Group/Configuration", True, 4, 3, 80),

    # ─── Storage ───
    ("object_storage", "storage", "Object Storage", True, 4, 3, 10),
    ("block_storage", "storage", "Block Storage", True, 4, 4, 20),
    ("file_storage", "storage", "File Storage", True, 4, 3, 30),
    ("archive_storage", "storage", "Archive Storage", True, 3, 3, 40),

    # ─── Database ───
    ("relational_db", "database", "Relational Database (SQL)", True, 4, 4, 10),
    ("nosql_db", "database", "NoSQL Database", True, 4, 3, 20),
    ("hierarchical_db", "database", "Hierarchical Database", True, 1, 1, 30),
    ("newsql_db", "database", "NewSQL Database", True, 2, 1, 40),
    ("object_oriented_db", "database", "Object-Oriented Database", True, 2, 1, 50),
    ("time_series_db", "database", "Time Series Database", True, 3, 2, 60),
    ("in_memory_db", "database", "In-Memory Database/Cache", True, 3, 3, 70),
    ("network_db", "database", "Network Database", True, 2, 3, 80),
    ("data_warehouse", "database", "Data Warehouse / Analytics Database", True, 4, 2, 90),

    # ─── Networking ───
    ("switch", "networking", "Switch", True, 5, 5, 10),
    ("router", "networking", "Router", True, 5, 5, 20),
    ("firewall", "networking", "Firewall", True, 5, 5, 30),
    ("gateway", "networking", "Gateway", True, 5, 5, 40),
    ("load_balancer", "networking", "Load Balancer", True, 5, 4, 50),
    ("vpn", "networking", "VPN", True, 4, 3, 60),
    ("dns_service", "networking", "DNS Service / DHCP / IPAM", True, 4, 4, 70),
    ("wireless_ap", "networking", "Wireless Access Point / Controller", True, 4, 3, 80),
    ("proxy", "networking", "Proxy / API Gateway", True, 5, 5, 90),
    ("vlan_segment", "networking", "VLAN / Network Segment", True, 4, 4, 100),
    ("sdn_controller", "networking", "SDN Controller/Instance", True, 4, 3, 110),
    ("network_monitor", "networking", "Network Monitoring/Logging Node", True, 4, 3, 120),
    ("network_aaa", "networking", "Network Authentication / AAA Server", True, 4, 3, 130),
    ("vpc", "networking", "Virtual Private Cloud / VPC / VNet", True, 5, 3, 140),
    ("subnet", "networking", "Subnet", True, 4, 3, 150),
    ("cdn", "networking", "CDN", True, 3, 3, 160),
    ("security_group", "networking", "Firewall Rule / Security Group / Network ACL", True, 5, 4, 170),
    ("virtual_network_appliance", "networking", "Virtual Network Appliance", True, 4, 4, 180),

    # ─── Security & Identity ───
    ("iam", "security_identity", "IAM / Identity & Access Management", True, 4, 2, 10),
    ("key_management", "security_identity", "Key Management System (KMS)", True, 4, 2, 20),
    ("firewall_policy", "security_identity", "Firewall Policy / Network Policy", True, 4, 3, 30),
    ("certificate_management", "security_identity", "Certificate Management", True, 4, 2, 40),

    # ─── Monitoring ───
    ("logs_metrics", "monitoring", "Logs & Metrics", True, 4, 2, 10),
    ("audit_trail", "monitoring", "Audit Trail", True, 4, 2, 20),

    # ─── App Integration & Messaging ───
    ("message_queue", "app_integration", "Message Queue (MQ)", True, 4, 3, 10),
    ("pubsub", "app_integration", "Pub/Sub Service", True, 4, 3, 20),
    ("event_stream", "app_integration", "Event Stream Broker", True, 4, 3, 30),
    ("esb", "app_integration", "Enterprise Service Bus (ESB)", True, 3, 2, 40),
    ("api_endpoint", "app_integration", "Web Service / API Endpoint", True, 4, 3, 50),
    ("workflow_orchestration", "app_integration", "Workflow/Orchestration Service", True, 4, 2, 60),

    # ─── Data Processing & Analytics ───
    ("stream_processing", "data_processing", "Stream Processing Engine", True, 4, 2, 10),
    ("batch_processing", "data_processing", "Batch Processing Engine", True, 4, 2, 20),
    ("data_lake", "data_processing", "Data Lake", True, 4, 2, 30),
    ("bi_tool", "data_processing", "Business Intelligence Tool", True, 2, 1, 40),

    # ─── AI/ML ───
    ("ml_platform", "ai_ml", "ML Platform / Notebook Service", True, 5, 2, 10),
    ("model_hosting", "ai_ml", "Model Hosting / Inference Endpoint", True, 5, 2, 20),
    ("ai_service", "ai_ml", "Pre-trained AI Service", True, 4, 1, 30),

    # ─── DevOps ───
    ("cicd_pipeline", "devops", "CI/CD Pipeline", True, 5, 5, 10),
    ("iac", "devops", "Infrastructure as Code", True, 5, 4, 20),
    ("container_registry", "devops", "Container Registry", True, 4, 3, 30),
    ("code_repo", "devops", "Code Repository", True, 3, 2, 40),
    ("artifact_repo", "devops", "Artifact Repository", True, 3, 2, 50),
    ("sdk_cli", "devops", "SDK / CLI", True, 3, 3, 60),

    # ─── Governance & Operations ───
    ("itsm", "governance_ops", "IT Service Management / ITSM", True, 3, 1, 10),
    ("cmdb", "governance_ops", "Configuration Management DB / CMDB", True, 3, 1, 20),
    ("monitoring_logging_platform", "governance_ops", "Monitoring & Logging Platform", True, 4, 2, 30),
    ("siem_soar", "governance_ops", "SIEM / SOAR Platform", True, 4, 1, 40),
    ("vulnerability_scanner", "governance_ops", "Vulnerability Management Platform/Scanner", True, 4, 2, 50),
    ("patch_management", "governance_ops", "Patch Management System", True, 5, 3, 60),
    ("secrets_management", "governance_ops", "Secrets Management Platform", True, 5, 3, 70),
    ("dlp", "governance_ops", "Data Loss Prevention (DLP)", True, 3, 1, 80),
    ("cost_management", "governance_ops", "Cost Management Tool", True, 3, 1, 90),
    ("cspm", "governance_ops", "Cloud Security Posture Management (CSPM)", True, 4, 1, 100),
    ("threat_detection", "governance_ops", "Threat Detection & Response Service", True, 4, 1, 110),
    ("resource_tagging", "governance_ops", "Resource Tagging / Management", True, 5, 4, 120),

    # ─── Hybrid & Edge ───
    ("dedicated_connection", "hybrid_edge", "Dedicated Connection", True, 4, 2, 10),
    ("edge_compute_device", "hybrid_edge", "Edge Compute Device / Gateway", True, 5, 3, 20),
    ("edge_orchestration", "hybrid_edge", "Edge Software Orchestration Platform", True, 5, 2, 30),

    # ─── Migration ───
    ("data_migration_tool", "migration", "Data Migration / Transfer Tool", True, 3, 1, 10),
    ("vm_migration_tool", "migration", "VM Migration Tool", True, 3, 1, 20),
    ("db_migration_service", "migration", "Database Migration Service", True, 2, 1, 30),
]


# ─── Vendor-to-normalized mappings from the taxonomy document ──────────────
# (vendor, vendor_resource_type, resource_type_slug, ansible_collection)

VENDOR_MAPPINGS = [
    # === Public Cloud — AWS ===
    ("aws", "EC2 Instance", "virtual_machine", "amazon.aws"),
    ("aws", "Auto Scaling Group", "auto_scaling_group", "amazon.aws"),
    ("aws", "EC2 Bare Metal", "bare_metal", "amazon.aws"),
    ("aws", "S3 Bucket", "object_storage", "amazon.aws"),
    ("aws", "EBS Volume", "block_storage", "amazon.aws"),
    ("aws", "EFS", "file_storage", "amazon.aws"),
    ("aws", "FSx", "file_storage", "amazon.aws"),
    ("aws", "VPC", "vpc", "amazon.aws"),
    ("aws", "ELB", "load_balancer", "amazon.aws"),
    ("aws", "CloudFront Distribution", "cdn", "amazon.aws"),
    ("aws", "Route 53 Hosted Zone", "dns_service", "amazon.aws"),
    ("aws", "RDS Instance", "relational_db", "amazon.aws"),
    ("aws", "DynamoDB Table", "nosql_db", "amazon.aws"),
    ("aws", "Redshift Cluster", "data_warehouse", "amazon.aws"),
    ("aws", "IAM", "iam", "amazon.aws"),
    ("aws", "KMS Key", "key_management", "amazon.aws"),
    ("aws", "Security Group", "security_group", "amazon.aws"),
    ("aws", "ACM Certificate", "certificate_management", "amazon.aws"),
    ("aws", "CloudWatch", "logs_metrics", "amazon.aws"),
    ("aws", "CloudTrail", "audit_trail", "amazon.aws"),
    ("aws", "SQS Queue", "message_queue", "amazon.aws"),
    ("aws", "SNS Topic", "pubsub", "amazon.aws"),
    ("aws", "SageMaker", "ml_platform", "amazon.aws"),
    ("aws", "SageMaker Endpoint", "model_hosting", "amazon.aws"),
    ("aws", "Kinesis Stream", "stream_processing", "amazon.aws"),
    ("aws", "AWS Batch", "batch_processing", "amazon.aws"),
    ("aws", "EMR Cluster", "batch_processing", "amazon.aws"),
    ("aws", "CodePipeline", "cicd_pipeline", "amazon.aws"),
    ("aws", "CodeBuild Project", "cicd_pipeline", "amazon.aws"),
    ("aws", "CloudFormation Stack", "iac", "amazon.aws"),
    ("aws", "ECR Repository", "container_registry", "amazon.aws"),
    ("aws", "EKS Cluster", "container_orchestration_platform", "amazon.aws"),
    ("aws", "Lambda Function", "serverless_function", "amazon.aws"),
    ("aws", "Step Functions", "workflow_orchestration", "amazon.aws"),
    ("aws", "Snowball", "data_migration_tool", "amazon.aws"),
    ("aws", "DMS", "db_migration_service", "amazon.aws"),
    ("aws", "MGN", "vm_migration_tool", "amazon.aws"),
    ("aws", "Outposts", "edge_compute_device", "amazon.aws"),
    ("aws", "Direct Connect", "dedicated_connection", "amazon.aws"),

    # === Public Cloud — Azure ===
    ("azure", "Virtual Machine", "virtual_machine", "azure.azcollection"),
    ("azure", "Virtual Machine Scale Set", "auto_scaling_group", "azure.azcollection"),
    ("azure", "BareMetal Infrastructure", "bare_metal", "azure.azcollection"),
    ("azure", "Blob Storage", "object_storage", "azure.azcollection"),
    ("azure", "Managed Disk", "block_storage", "azure.azcollection"),
    ("azure", "Azure Files", "file_storage", "azure.azcollection"),
    ("azure", "NetApp Files", "file_storage", "azure.azcollection"),
    ("azure", "Virtual Network (VNet)", "vpc", "azure.azcollection"),
    ("azure", "Azure Load Balancer", "load_balancer", "azure.azcollection"),
    ("azure", "Application Gateway", "load_balancer", "azure.azcollection"),
    ("azure", "Azure CDN", "cdn", "azure.azcollection"),
    ("azure", "Azure DNS", "dns_service", "azure.azcollection"),
    ("azure", "Azure SQL", "relational_db", "azure.azcollection"),
    ("azure", "Azure PostgreSQL", "relational_db", "azure.azcollection"),
    ("azure", "Azure MySQL", "relational_db", "azure.azcollection"),
    ("azure", "Cosmos DB", "nosql_db", "azure.azcollection"),
    ("azure", "Azure Synapse", "data_warehouse", "azure.azcollection"),
    ("azure", "Azure AD / RBAC", "iam", "azure.azcollection"),
    ("azure", "Key Vault", "key_management", "azure.azcollection"),
    ("azure", "NSG", "security_group", "azure.azcollection"),
    ("azure", "Azure Firewall", "firewall", "azure.azcollection"),
    ("azure", "Azure Monitor", "logs_metrics", "azure.azcollection"),
    ("azure", "Activity Log", "audit_trail", "azure.azcollection"),
    ("azure", "Azure Queue Storage", "message_queue", "azure.azcollection"),
    ("azure", "Event Grid", "pubsub", "azure.azcollection"),
    ("azure", "Service Bus", "pubsub", "azure.azcollection"),
    ("azure", "Azure Machine Learning", "ml_platform", "azure.azcollection"),
    ("azure", "ML Studio Inference", "model_hosting", "azure.azcollection"),
    ("azure", "Azure Stream Analytics", "stream_processing", "azure.azcollection"),
    ("azure", "Azure Data Factory", "batch_processing", "azure.azcollection"),
    ("azure", "HDInsight Cluster", "batch_processing", "azure.azcollection"),
    ("azure", "Azure Pipelines", "cicd_pipeline", "azure.azcollection"),
    ("azure", "ARM Template", "iac", "azure.azcollection"),
    ("azure", "Bicep Deployment", "iac", "azure.azcollection"),
    ("azure", "Azure Container Registry", "container_registry", "azure.azcollection"),
    ("azure", "AKS Cluster", "container_orchestration_platform", "azure.azcollection"),
    ("azure", "Azure Functions", "serverless_function", "azure.azcollection"),
    ("azure", "Durable Functions", "workflow_orchestration", "azure.azcollection"),
    ("azure", "Logic Apps", "workflow_orchestration", "azure.azcollection"),
    ("azure", "Data Box", "data_migration_tool", "azure.azcollection"),
    ("azure", "Azure Migrate", "vm_migration_tool", "azure.azcollection"),
    ("azure", "Azure Stack", "edge_compute_device", "azure.azcollection"),
    ("azure", "ExpressRoute", "dedicated_connection", "azure.azcollection"),

    # === Public Cloud — GCP ===
    ("gcp", "Compute Engine Instance", "virtual_machine", "google.cloud"),
    ("gcp", "Managed Instance Group", "auto_scaling_group", "google.cloud"),
    ("gcp", "Bare Metal Solution", "bare_metal", "google.cloud"),
    ("gcp", "Cloud Storage Bucket", "object_storage", "google.cloud"),
    ("gcp", "Persistent Disk", "block_storage", "google.cloud"),
    ("gcp", "Filestore", "file_storage", "google.cloud"),
    ("gcp", "VPC Network", "vpc", "google.cloud"),
    ("gcp", "Cloud Load Balancing", "load_balancer", "google.cloud"),
    ("gcp", "Cloud CDN", "cdn", "google.cloud"),
    ("gcp", "Cloud DNS Zone", "dns_service", "google.cloud"),
    ("gcp", "Cloud SQL Instance", "relational_db", "google.cloud"),
    ("gcp", "Firestore", "nosql_db", "google.cloud"),
    ("gcp", "Datastore", "nosql_db", "google.cloud"),
    ("gcp", "BigQuery Dataset", "data_warehouse", "google.cloud"),
    ("gcp", "IAM", "iam", "google.cloud"),
    ("gcp", "Cloud KMS", "key_management", "google.cloud"),
    ("gcp", "VPC Firewall Rule", "security_group", "google.cloud"),
    ("gcp", "Certificate Manager", "certificate_management", "google.cloud"),
    ("gcp", "Cloud Monitoring", "logs_metrics", "google.cloud"),
    ("gcp", "Cloud Audit Logs", "audit_trail", "google.cloud"),
    ("gcp", "Pub/Sub Topic", "pubsub", "google.cloud"),
    ("gcp", "Vertex AI", "ml_platform", "google.cloud"),
    ("gcp", "Vertex AI Endpoint", "model_hosting", "google.cloud"),
    ("gcp", "Dataflow Job", "stream_processing", "google.cloud"),
    ("gcp", "Dataproc Cluster", "batch_processing", "google.cloud"),
    ("gcp", "Cloud Build", "cicd_pipeline", "google.cloud"),
    ("gcp", "Deployment Manager", "iac", "google.cloud"),
    ("gcp", "Artifact Registry", "container_registry", "google.cloud"),
    ("gcp", "GKE Cluster", "container_orchestration_platform", "google.cloud"),
    ("gcp", "Cloud Function", "serverless_function", "google.cloud"),
    ("gcp", "Workflows", "workflow_orchestration", "google.cloud"),
    ("gcp", "Transfer Appliance", "data_migration_tool", "google.cloud"),
    ("gcp", "Migrate for Compute Engine", "vm_migration_tool", "google.cloud"),
    ("gcp", "Anthos", "edge_compute_device", "google.cloud"),
    ("gcp", "Interconnect", "dedicated_connection", "google.cloud"),

    # === Private Cloud — VMware ===
    ("vmware", "vSphere VM", "virtual_machine", "vmware.vmware"),
    ("vmware", "ESXi Host", "hypervisor_host", "vmware.vmware"),
    ("vmware", "vRealize Automation", "auto_scaling_group", "vmware.vmware"),
    ("vmware", "vSphere Bare Metal Extensions", "bare_metal", "vmware.vmware"),
    ("vmware", "vSAN Object Store", "object_storage", "vmware.vmware"),
    ("vmware", "vSAN Datastore", "block_storage", "vmware.vmware"),
    ("vmware", "vSAN File Services", "file_storage", "vmware.vmware"),
    ("vmware", "NSX-T Segment", "vpc", "vmware.vmware"),
    ("vmware", "NSX Load Balancer", "load_balancer", "vmware.vmware"),
    ("vmware", "NSX DFW", "firewall_policy", "vmware.vmware"),
    ("vmware", "Tanzu SQL", "relational_db", "vmware.vmware"),
    ("vmware", "Tanzu GemFire", "nosql_db", "vmware.vmware"),
    ("vmware", "vCenter SSO", "iam", "vmware.vmware"),
    ("vmware", "vSphere KMS Integration", "key_management", "vmware.vmware"),
    ("vmware", "vRealize Log Insight", "logs_metrics", "vmware.vmware"),
    ("vmware", "Tanzu Kubernetes Grid", "container_orchestration_platform", "vmware.vmware"),
    ("vmware", "Harbor Registry", "container_registry", "vmware.vmware"),
    ("vmware", "Knative on Tanzu", "serverless_function", "vmware.vmware"),
    ("vmware", "HCX", "vm_migration_tool", "vmware.vmware"),
    ("vmware", "VMware Edge Compute Stack", "edge_compute_device", "vmware.vmware"),

    # === Private Cloud — OpenStack ===
    ("openstack", "Nova Instance", "virtual_machine", "openstack.cloud"),
    ("openstack", "Nova Compute Node", "hypervisor_host", "openstack.cloud"),
    ("openstack", "Ironic Node", "bare_metal", "openstack.cloud"),
    ("openstack", "Swift Container", "object_storage", "openstack.cloud"),
    ("openstack", "Cinder Volume", "block_storage", "openstack.cloud"),
    ("openstack", "Manila Share", "file_storage", "openstack.cloud"),
    ("openstack", "Neutron Network", "vpc", "openstack.cloud"),
    ("openstack", "Octavia Load Balancer", "load_balancer", "openstack.cloud"),
    ("openstack", "Designate Zone", "dns_service", "openstack.cloud"),
    ("openstack", "Neutron Security Group", "security_group", "openstack.cloud"),
    ("openstack", "Trove Instance", "relational_db", "openstack.cloud"),
    ("openstack", "Keystone", "iam", "openstack.cloud"),
    ("openstack", "Barbican Secret", "key_management", "openstack.cloud"),
    ("openstack", "Heat Stack", "iac", "openstack.cloud"),
    ("openstack", "Magnum Cluster", "container_orchestration_platform", "openstack.cloud"),

    # === Private Cloud — OpenShift ===
    ("openshift", "OpenShift VM (KubeVirt/CNV)", "virtual_machine", "redhat.openshift"),
    ("openshift", "Worker Node", "hypervisor_host", "redhat.openshift"),
    ("openshift", "OpenShift Metal Node", "bare_metal", "redhat.openshift"),
    ("openshift", "Rook + Ceph Block", "block_storage", "redhat.openshift"),
    ("openshift", "CephFS / NFS", "file_storage", "redhat.openshift"),
    ("openshift", "OpenShift SDN", "vpc", "redhat.openshift"),
    ("openshift", "OpenShift Router / HAProxy", "load_balancer", "redhat.openshift"),
    ("openshift", "External DNS Operator", "dns_service", "redhat.openshift"),
    ("openshift", "NetworkPolicy", "security_group", "redhat.openshift"),
    ("openshift", "Crunchy Postgres Operator", "relational_db", "redhat.openshift"),
    ("openshift", "OpenShift RBAC / OAuth", "iam", "redhat.openshift"),
    ("openshift", "cert-manager Certificate", "certificate_management", "redhat.openshift"),
    ("openshift", "Prometheus / Loki / Grafana", "logs_metrics", "redhat.openshift"),
    ("openshift", "OpenShift Kubernetes", "container_orchestration_platform", "redhat.openshift"),
    ("openshift", "Quay.io Registry", "container_registry", "redhat.openshift"),
    ("openshift", "OpenShift Pipelines (Tekton)", "cicd_pipeline", "redhat.openshift"),
    ("openshift", "ArgoCD / GitOps", "iac", "redhat.openshift"),
    ("openshift", "OpenShift Serverless (Knative)", "serverless_function", "redhat.openshift"),
    ("openshift", "Open Data Hub / RHODS", "ml_platform", "redhat.openshift"),
    ("openshift", "RHODS + KServe", "model_hosting", "redhat.openshift"),
    ("openshift", "Single Node OpenShift (SNO)", "edge_compute_device", "redhat.openshift"),

    # === Networking — Cisco ===
    ("cisco", "Nexus 9000 (NX-OS/ACI)", "switch", "cisco.nxos"),
    ("cisco", "Nexus 3000", "switch", "cisco.nxos"),
    ("cisco", "Catalyst 9K", "switch", "cisco.ios"),
    ("cisco", "ACI (APIC)", "sdn_controller", "cisco.aci"),
    ("cisco", "Catalyst 9800 WLAN Controller", "wireless_ap", "cisco.ios"),
    ("cisco", "Aironet AP", "wireless_ap", "cisco.ios"),
    ("cisco", "ASR Router", "router", "cisco.iosxr"),
    ("cisco", "Catalyst 8000", "router", "cisco.iosxr"),
    ("cisco", "ISR Router", "router", "cisco.ios"),
    ("cisco", "Cisco SD-WAN (Viptela)", "router", "cisco.sdwan"),
    ("cisco", "Secure Firewall (Firepower)", "firewall", "cisco.fmcv"),
    ("cisco", "ISE", "network_aaa", "cisco.ise"),
    ("cisco", "Cisco Umbrella", "proxy", ""),
    ("cisco", "Secure ADC", "load_balancer", ""),
    ("cisco", "CSR1000v / vEdge", "virtual_network_appliance", "cisco.ios"),
    ("cisco", "ThousandEyes", "network_monitor", ""),

    # === Networking — Cisco Meraki ===
    ("meraki", "MS Switch", "switch", "cisco.meraki"),
    ("meraki", "MR Wireless AP", "wireless_ap", "cisco.meraki"),
    ("meraki", "MX Security Appliance", "firewall", "cisco.meraki"),
    ("meraki", "MX Router / SD-WAN", "router", "cisco.meraki"),
    ("meraki", "VMX Cloud Router", "virtual_network_appliance", "cisco.meraki"),

    # === Networking — Arista ===
    ("arista", "7000/7200 Series (EOS)", "switch", "arista.eos"),
    ("arista", "720XP / 750 Series", "switch", "arista.eos"),
    ("arista", "CloudVision CVP", "sdn_controller", "arista.eos"),
    ("arista", "CloudEOS", "virtual_network_appliance", "arista.eos"),
    ("arista", "7500R / 7280R Router", "router", "arista.eos"),

    # === Networking — Juniper ===
    ("juniper", "QFX Series", "switch", "junipernetworks.junos"),
    ("juniper", "EX Series", "switch", "junipernetworks.junos"),
    ("juniper", "MX Series", "router", "junipernetworks.junos"),
    ("juniper", "ACX Router", "router", "junipernetworks.junos"),
    ("juniper", "Session Smart Router (128T)", "router", "junipernetworks.junos"),
    ("juniper", "SRX Series Firewall", "firewall", "junipernetworks.junos"),
    ("juniper", "Apstra Controller", "sdn_controller", "junipernetworks.junos"),
    ("juniper", "Mist AP", "wireless_ap", "junipernetworks.junos"),
    ("juniper", "CN2 (Contrail Networking 2.0)", "sdn_controller", "junipernetworks.junos"),
    ("juniper", "vMX / vSRX", "virtual_network_appliance", "junipernetworks.junos"),
    ("juniper", "Paragon Insights", "network_monitor", "junipernetworks.junos"),

    # === Storage — NetApp ===
    ("netapp", "ONTAP SAN (iSCSI/FC)", "block_storage", "netapp.ontap"),
    ("netapp", "ONTAP NAS (NFS/SMB)", "file_storage", "netapp.ontap"),
    ("netapp", "StorageGRID Bucket", "object_storage", "netapp.ontap"),
    ("netapp", "Cloud Volumes ONTAP", "block_storage", "netapp.ontap"),
    ("netapp", "SnapMirror", "data_migration_tool", "netapp.ontap"),
    ("netapp", "Astra Trident CSI", "block_storage", "netapp.ontap"),
    ("netapp", "Active IQ Unified Manager", "monitoring_logging_platform", "netapp.ontap"),

    # === Storage — Dell EMC ===
    ("dell_emc", "PowerMax", "block_storage", "dellemc.enterprise_sonic"),
    ("dell_emc", "Unity XT", "block_storage", "dellemc.enterprise_sonic"),
    ("dell_emc", "PowerScale (Isilon)", "file_storage", "dellemc.enterprise_sonic"),
    ("dell_emc", "ECS Object Storage", "object_storage", "dellemc.enterprise_sonic"),
    ("dell_emc", "PowerFlex", "block_storage", "dellemc.enterprise_sonic"),
    ("dell_emc", "RecoverPoint", "data_migration_tool", "dellemc.enterprise_sonic"),
    ("dell_emc", "Dell CSI Drivers", "block_storage", "dellemc.enterprise_sonic"),
    ("dell_emc", "CloudIQ", "monitoring_logging_platform", "dellemc.enterprise_sonic"),

    # === Storage — IBM ===
    ("ibm_storage", "FlashSystem", "block_storage", "ibm.storage_virtualize"),
    ("ibm_storage", "DS8000", "block_storage", "ibm.storage_virtualize"),
    ("ibm_storage", "Spectrum Scale (GPFS)", "file_storage", "ibm.storage_virtualize"),
    ("ibm_storage", "Cloud Object Storage (COS)", "object_storage", "ibm.storage_virtualize"),
    ("ibm_storage", "Spectrum Virtualize", "block_storage", "ibm.storage_virtualize"),
    ("ibm_storage", "Spectrum Protect", "data_migration_tool", "ibm.storage_virtualize"),
    ("ibm_storage", "IBM CSI for Spectrum Scale", "block_storage", "ibm.storage_virtualize"),
    ("ibm_storage", "Storage Insights", "monitoring_logging_platform", "ibm.storage_virtualize"),
]


def seed_taxonomy(apps, schema_editor):
    """Populate the normalized resource taxonomy."""
    ResourceCategory = apps.get_model("inventory", "ResourceCategory")
    ResourceType = apps.get_model("inventory", "ResourceType")
    VendorTypeMapping = apps.get_model("inventory", "VendorTypeMapping")

    # Create categories
    cat_map = {}
    for slug, name, description, sort_order in CATEGORIES:
        cat, _ = ResourceCategory.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "description": description,
                "sort_order": sort_order,
            },
        )
        cat_map[slug] = cat

    # Create resource types
    rt_map = {}
    for slug, cat_slug, name, is_countable, ltsv, sto, sort_order in RESOURCE_TYPES:
        rt, _ = ResourceType.objects.get_or_create(
            slug=slug,
            defaults={
                "category": cat_map[cat_slug],
                "name": name,
                "is_countable": is_countable,
                "long_term_strategic_value": ltsv,
                "short_term_opportunity": sto,
                "sort_order": sort_order,
            },
        )
        rt_map[slug] = rt

    # Create vendor mappings
    for vendor, vendor_type, rt_slug, collection in VENDOR_MAPPINGS:
        VendorTypeMapping.objects.get_or_create(
            vendor=vendor,
            vendor_resource_type=vendor_type,
            defaults={
                "resource_type": rt_map[rt_slug],
                "ansible_collection": collection,
            },
        )


def reverse_taxonomy(apps, schema_editor):
    """Remove seed data."""
    VendorTypeMapping = apps.get_model("inventory", "VendorTypeMapping")
    ResourceType = apps.get_model("inventory", "ResourceType")
    ResourceCategory = apps.get_model("inventory", "ResourceCategory")
    VendorTypeMapping.objects.all().delete()
    ResourceType.objects.all().delete()
    ResourceCategory.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_taxonomy, reverse_taxonomy),
    ]
