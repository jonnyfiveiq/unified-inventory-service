# Inventory Service

A Django service for the Ansible Automation Platform (AAP), built on the
[ansible-services-framework](https://github.com/ansible/ansible-services-framework) (copier template)
and [django-ansible-base](https://github.com/ansible/django-ansible-base) (DAB).

Provides unified inventory management for AAP — discovering, cataloguing and
tracking infrastructure resources across VMware vSphere, public cloud and
bare-metal providers. Includes RBAC, activity streams, feature flags and
gateway authentication out of the box.

## Database Schema

The full entity-relationship diagram shows every model, field, and foreign-key
relationship in the inventory service PostgreSQL database:

![Inventory Service Schema](schema.svg)

> **Tip:** open the SVG directly in a browser to pan / zoom on the full diagram.

### VMware vSphere seed data example

The following diagram shows the topology created by the `seed_vmware_data`
management command — a realistic vSphere lab with 27 resources and 49
relationships. It illustrates how the schema above maps to real VMware objects
(vCenter, clusters, ESXi hosts, datastores, resource pools and VMs) and the
relationship types (`runs_on`, `attached_to`, `member_of`, `part_of`)
that connect them:

![VMware Seed Data Topology](vmware-seed-example.svg)

## Data Model

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

## Inventory API

Once deployed behind the AAP gateway the inventory endpoints are available at
`/api/inventory/v1/`. All endpoints require authentication.

### Providers — full CRUD

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/providers/` | List all providers (filterable, searchable) |
| `POST` | `/providers/` | Register a new infrastructure provider |
| `GET` | `/providers/{id}/` | Provider detail |
| `PATCH` | `/providers/{id}/` | Update provider fields |
| `PUT` | `/providers/{id}/` | Replace a provider |
| `DELETE` | `/providers/{id}/` | Remove a provider and its resources |
| `POST` | `/providers/{id}/collect/` | Trigger an inventory collection run |

**Filters:** `vendor`, `infrastructure`, `enabled`, `organization`
**Search:** `name`, `vendor`, `provider_type`
**Ordering:** `name`, `vendor`, `created`, `modified`

The `collect` action creates a `CollectionRun` in `pending` state and dispatches
an async task via dispatcherd. Returns `202 Accepted` with the run object, or
`409 Conflict` if the provider is disabled or a collection is already in progress.

```json
POST /api/inventory/v1/providers/{id}/collect/
{
    "collection_type": "full",
    "target_resource_types": ["virtual_machine", "vpc"]
}
```

### Collection Runs — read-only + cancel

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/collection-runs/` | List all collection runs (filterable) |
| `GET` | `/collection-runs/{id}/` | Run detail with status and timing |
| `POST` | `/collection-runs/{id}/cancel/` | Cancel a running or pending collection |

**Filters:** `status`, `provider`, `collection_type`
**Search:** `provider__name`, `task_uuid`
**Ordering:** `started_at`, `completed_at`, `status`

Collection runs are created exclusively through the provider `collect` action,
never directly via POST to this endpoint. The `cancel` action sends a cancel
command to the dispatcherd worker and marks the run as `canceled`.

### Resources — read-only

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/resources/` | List discovered resources (filterable, searchable) |
| `GET` | `/resources/{id}/` | Resource detail |

**Filters:** `provider`, `resource_type`, `state`, `region`, `os_type`, `organization`
**Search:** `name`, `ems_ref`, `fqdn`, `vendor_type`
**Ordering:** `name`, `state`, `first_discovered_at`, `last_seen_at`

Resources are created by collection tasks, not directly via the API.

```
GET /api/inventory/v1/resources/?state=running
GET /api/inventory/v1/resources/?search=esxi
GET /api/inventory/v1/resources/?provider=<uuid>
GET /api/inventory/v1/resources/?os_type=linux
GET /api/inventory/v1/resources/?region=Lab-DC1
```

### Resource Relationships — read-only

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/resource-relationships/` | List all resource relationships |
| `GET` | `/resource-relationships/{id}/` | Relationship detail |

**Filters:** `relationship_type`, `source`, `target`
**Ordering:** `relationship_type`

### Taxonomy — read-only reference data

The taxonomy endpoints expose the normalized resource classification hierarchy:
`ResourceCategory` → `ResourceType` → `VendorTypeMapping`.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/resource-categories/` | Top-level resource categories |
| `GET` | `/resource-categories/{id}/` | Category detail |
| `GET` | `/resource-types/` | Resource types within each category |
| `GET` | `/resource-types/{id}/` | Type detail |
| `GET` | `/vendor-type-mappings/` | Maps vendor-specific types to canonical types |
| `GET` | `/vendor-type-mappings/{id}/` | Mapping detail |

**Resource Categories** — Search: `name`, `slug` · Ordering: `sort_order`, `name`
**Resource Types** — Filters: `category`, `is_countable` · Search: `name`, `slug` · Ordering: `sort_order`, `name`, `category`
**Vendor Type Mappings** — Filters: `vendor`, `resource_type` · Search: `vendor`, `vendor_resource_type` · Ordering: `vendor`, `vendor_resource_type`

```
GET /api/inventory/v1/resource-types/?search=virtual_machine
GET /api/inventory/v1/vendor-type-mappings/?vendor=vmware
```

### Platform endpoints (via django-ansible-base)

These endpoints are provided by the framework and cover org/user/team
management, RBAC, activity streams and service discovery.

| Method | Endpoint | Description |
|---|---|---|
| `GET/POST` | `/organizations/` | Organization management |
| `GET/PATCH` | `/organizations/{id}/` | Organization detail |
| `GET` | `/organizations/{id}/teams/` | Teams in an organization |
| `GET/POST` | `/teams/` | Team management |
| `GET/PATCH` | `/teams/{id}/` | Team detail |
| `GET` | `/users/` | User listing |
| `GET` | `/users/{id}/` | User detail |
| `GET` | `/role_definitions/` | RBAC role definitions |
| `GET` | `/activitystream/` | Activity stream |
| `GET` | `/feature_flags/` | Feature flag management |
| `GET` | `/service-index/` | Service index |
| `GET` | `/docs/` | API documentation (browsable) |

### Health and operational endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/ping/` | Lightweight liveness check |
| `GET` | `/health/` | Service health status |

## API Endpoint Summary

| Endpoint | Access | Methods | Notes |
|---|---|---|---|
| `/providers/` | CRUD | GET, POST, PATCH, PUT, DELETE | Full lifecycle management |
| `/providers/{id}/collect/` | Action | POST | Triggers async collection |
| `/collection-runs/` | Read-only | GET | + POST cancel action |
| `/resources/` | Read-only | GET | Created by collection tasks |
| `/resource-relationships/` | Read-only | GET | Created by collection tasks |
| `/resource-categories/` | Read-only | GET | Seeded by migration |
| `/resource-types/` | Read-only | GET | Seeded by migration |
| `/vendor-type-mappings/` | Read-only | GET | Seeded by migration |
| `/organizations/` | CRUD | GET, POST, PATCH | Via DAB |
| `/teams/` | CRUD | GET, POST, PATCH | Via DAB |
| `/users/` | Read-only | GET | Via DAB |

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
