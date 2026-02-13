# Inventory Service

A Django service for the Ansible Automation Platform (AAP), built on the
[ansible-services-framework](https://github.com/ansible/ansible-services-framework) (copier template)
and [django-ansible-base](https://github.com/ansible/django-ansible-base) (DAB).

Provides unified inventory management for AAP — discovering, cataloguing and
tracking infrastructure resources across VMware vSphere, public cloud and
bare-metal providers. Includes RBAC, activity streams, feature flags and
gateway authentication out of the box.

## Inventory API

Once deployed behind the AAP gateway the inventory endpoints are available at
`/api/inventory/v1/`:

| Endpoint | Description |
|---|---|
| `/providers/` | Infrastructure providers (VMware vCenter, AWS, Azure…) |
| `/providers/{id}/collect/` | Trigger a collection run for a provider |
| `/collection-runs/` | Collection run status and history |
| `/resources/` | Discovered resources (VMs, hosts, datastores…) |
| `/resource-relationships/` | Relationships between resources (runs_on, attached_to…) |
| `/resource-categories/` | Taxonomy — top-level resource categories |
| `/resource-types/` | Taxonomy — resource types within each category |
| `/vendor-type-mappings/` | Taxonomy — maps vendor-specific types to canonical types |

### Filtering and search

Resources support filtering and full-text search:

```
GET /api/inventory/v1/resources/?state=running
GET /api/inventory/v1/resources/?search=esxi
GET /api/inventory/v1/resources/?provider__id=<uuid>
GET /api/inventory/v1/resources/?os_type=linux
GET /api/inventory/v1/resources/?region=Lab-DC1
```

Providers support filtering by vendor:

```
GET /api/inventory/v1/providers/?vendor=vmware
```

### Platform endpoints (via django-ansible-base)

| Endpoint | Description |
|---|---|
| `/organizations/` | Organization management |
| `/users/` | User management |
| `/teams/` | Team management |
| `/role_definitions/` | RBAC role definitions |
| `/activitystream/` | Activity stream |
| `/feature_flags/` | Feature flag management |
| `/service-index/` | Service index |
| `/docs/` | API documentation |

## Data model

```
Provider
 └── CollectionRun          (one provider → many runs)
 └── Resource               (one provider → many resources)
      ├── resource_type → ResourceType → ResourceCategory
      └── ResourceRelationship (source → target)
              types: runs_on, attached_to, member_of, part_of, manages

ResourceType ← VendorTypeMapping (maps vendor-specific names → canonical types)
```

The taxonomy (categories, types and vendor mappings) is seeded by migration and
covers 15 categories, 82 resource types and 20+ VMware vSphere mappings.

## Local development

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager

### Setup

```bash
uv venv
source .venv/bin/activate
uv pip install -e '.[dev]'

cp settings.local.py.example settings.local.py
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

### Seed VMware sample data

The `seed_vmware_data` management command populates a realistic vSphere lab
environment for development and testing:

- 1 vCenter provider (`vcsa01.lab.local`)
- 1 datacenter with 2 clusters (Prod + Dev)
- 4 ESXi hosts with real hardware specs
- 4 datastores (vSAN, NFS, FC/VMFS)
- 2 resource pools (Production, Staging)
- 14 VMs — AAP stack, RHEL web/db servers, Windows AD/IIS, dev boxes, templates
- Full relationship graph (runs_on, attached_to, member_of, part_of)

```bash
python manage.py seed_vmware_data          # seed
python manage.py seed_vmware_data --flush  # flush and re-seed
```

When deployed in aap-dev:

```bash
kubectl exec -it deploy/inventory-service -n aap26 -- \
  uv run --no-sync python manage.py seed_vmware_data
```

### Run the API test suite

`test_api.sh` exercises all API endpoints end-to-end (21 tests):

```bash
./test_api.sh                         # auto-detects password from aap-dev cluster
./test_api.sh -H localhost:8080       # custom host
./test_api.sh -u myuser -p mypass     # custom credentials
```

Tests cover: connectivity, taxonomy endpoints, provider CRUD, collection run
lifecycle, resource listing, filtered queries, and cleanup.

## Deploying with aap-dev

This service integrates with [aap-dev](https://github.com/ansible/aap-dev) as a
skaffold addon.

### 1. Clone the service source

```bash
cd aap-dev/src/
git clone https://github.com/jonnyfiveiq/unified-inventory-service.git inventory-service
```

### 2. Create Kubernetes manifests

Create the directory structure:

```
manifests/base/apps/inventory-service/
├── kustomization.yaml
└── k8s/
    ├── configmap.yaml
    ├── database.yaml
    ├── deployments.yaml
    ├── register-job.yaml
    ├── secrets.yaml
    └── services.yaml
```

See the [aap-dev deployment docs](https://github.com/ansible/aap-dev) for
the full manifest content. Key configuration points:

- **Gateway API slug**: `inventory` — external path is `/api/inventory/v1/`
- **Internal service name**: `inventory-service` (K8s service, deployment, DNS)
- **Database**: Dedicated PostgreSQL 15 instance (`inventory_db`)

### 3. Create the skaffold addon

```
skaffolding/addons/inventory-service/skaffold.yaml
```

Activated with:

```bash
export AAP_INVENTORY_SERVICE=true
```

### 4. Deploy

```bash
export AAP_INVENTORY_SERVICE=true
export AAP_VERSION=2.6
make clean && make aap
```

The service will be available at `http://localhost:44926/api/inventory/v1/`.

Admin password:

```bash
make admin-password
```

### Verify

```bash
PASS=$(make admin-password 2>/dev/null | tail -1)
curl -s http://localhost:44926/api/inventory/v1/providers/ -u "admin:$PASS" | python3 -m json.tool
```

## Architecture notes

- **Gateway slug**: `inventory` (20-char gateway limit on `api_slug`)
- **Internal service name**: `inventory-service` (K8s service, deployment, DNS)
- **Service prefix middleware**: Strips `/api/inventory/` prefix so Django routes
  are clean `/api/v1/...` internally
- **Database**: Dedicated PostgreSQL 15 instance (`inventory_db`)
- **Authentication**: Via AAP gateway JWT — no direct auth on the service
- **Taxonomy**: Seeded by data migration — 15 categories, 82 types, VMware mappings

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.
