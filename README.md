# Unified Inventory Service

A Django service for the Ansible Automation Platform (AAP), built on the
[ansible-services-framework](https://github.com/ansible/ansible-services-framework) (copier template)
and [django-ansible-base](https://github.com/ansible/django-ansible-base) (DAB).

Provides a foundation for unified inventory management within AAP, with RBAC,
activity streams, feature flags, and gateway authentication out of the box.

## API Endpoints

Once deployed, the service exposes the following at `/api/unified-inventory/v1/`:

- `/activitystream/` — Activity stream
- `/docs/` — API documentation
- `/feature_flags/` — Feature flag management
- `/organizations/` — Organization management
- `/role_definitions/` — RBAC role definitions
- `/teams/` — Team management
- `/users/` — User management
- `/service-index/` — Service index

## Local Development

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager

### Setup

```bash
uv venv
source .venv/bin/activate
uv pip install -e '.[dev]'

# Configure local settings
cp settings.local.py.example settings.local.py

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Run the dev server
python manage.py runserver
```

## Deploying with aap-dev

This service integrates with [aap-dev](https://github.com/ansible/aap-dev) as a
skaffold addon. The following scaffolding changes are required in the aap-dev repo.

### 1. Clone the service source

```bash
cd aap-dev/src/
git clone https://github.com/jonnyfiveiq/unified-inventory-service.git
```

### 2. Create Kubernetes manifests

Create the directory structure:

```
manifests/base/apps/unified-inventory-service/
├── kustomization.yaml
└── k8s/
    ├── configmap.yaml
    ├── database.yaml
    ├── deployments.yaml
    ├── register-job.yaml
    ├── secrets.yaml
    └── services.yaml
```

#### `manifests/base/apps/unified-inventory-service/kustomization.yaml`

```yaml
---
resources:
  - k8s/deployments.yaml
  - k8s/services.yaml
  - k8s/register-job.yaml
  - k8s/configmap.yaml
  - k8s/secrets.yaml
  - k8s/database.yaml
```

#### `manifests/base/apps/unified-inventory-service/k8s/deployments.yaml`

```yaml
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: unified-inventory-service
  labels:
    app: unified-inventory-service
spec:
  replicas: 1
  selector:
    matchLabels:
      app: unified-inventory-service
  template:
    metadata:
      labels:
        app: unified-inventory-service
    spec:
      containers:
        - name: unified-inventory-service
          image: __UNIFIED_INVENTORY_SERVICE_IMAGE__
          imagePullPolicy: Always
          ports:
            - containerPort: 8000
          env:
            - name: UNIFIED_INVENTORY_SERVICE_DATABASES__default__ENGINE
              value: django.db.backends.postgresql
            - name: UNIFIED_INVENTORY_SERVICE_DATABASES__default__HOST
              valueFrom:
                secretKeyRef:
                  key: host
                  name: unified-inventory-service-postgres-configuration
            - name: UNIFIED_INVENTORY_SERVICE_DATABASES__default__NAME
              valueFrom:
                secretKeyRef:
                  key: database
                  name: unified-inventory-service-postgres-configuration
            - name: UNIFIED_INVENTORY_SERVICE_DATABASES__default__PORT
              valueFrom:
                secretKeyRef:
                  key: port
                  name: unified-inventory-service-postgres-configuration
            - name: UNIFIED_INVENTORY_SERVICE_DATABASES__default__USER
              valueFrom:
                secretKeyRef:
                  key: username
                  name: unified-inventory-service-postgres-configuration
            - name: UNIFIED_INVENTORY_SERVICE_DATABASES__default__PASSWORD
              valueFrom:
                secretKeyRef:
                  key: password
                  name: unified-inventory-service-postgres-configuration
            - name: UNIFIED_INVENTORY_SERVICE_ALLOWED_HOSTS
              value: '["localhost","127.0.0.1","0.0.0.0","unified-inventory-service"]'
            - name: UNIFIED_INVENTORY_SERVICE_AAP_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: myaap-admin-password
                  key: password
```

#### `manifests/base/apps/unified-inventory-service/k8s/services.yaml`

```yaml
---
apiVersion: v1
kind: Service
metadata:
  name: unified-inventory-service
  labels:
    app: unified-inventory-service
spec:
  selector:
    app: unified-inventory-service
  ports:
    - port: 8000
      targetPort: 8000
      name: http
---
apiVersion: v1
kind: Service
metadata:
  labels:
    app.kubernetes.io/component: database
    app.kubernetes.io/instance: postgres-15-unified-inventory-service
    app.kubernetes.io/name: postgres-15
  name: unified-inventory-service-postgres-15
spec:
  internalTrafficPolicy: Cluster
  ipFamilies:
    - IPv4
  ipFamilyPolicy: SingleStack
  ports:
    - name: "5432"
      port: 5432
  selector:
    app.kubernetes.io/component: database
    app.kubernetes.io/instance: postgres-15-unified-inventory-service
    app.kubernetes.io/name: postgres-15
```

#### `manifests/base/apps/unified-inventory-service/k8s/secrets.yaml`

```yaml
---
apiVersion: v1
kind: Secret
metadata:
  name: unified-inventory-service-postgres-configuration
type: Opaque
stringData:
  database: unified_inventory_db
  host: unified-inventory-service-postgres-15
  password: helloSvcDevPass123456789abcdef # notsecret
  port: "5432"
  postgres_admin_password: helloSvcAdminPass987654321xyz # notsecret
  type: managed
  username: unified_inventory
```

#### `manifests/base/apps/unified-inventory-service/k8s/configmap.yaml`

```yaml
---
apiVersion: v1
data:
  init_component_dbs.sh: |
    db_exists=$(psql -tAc "SELECT 1 FROM pg_database WHERE datname='unified_inventory_db'")
    user_exists=$(psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='unified_inventory'")
    if [ -z "$user_exists" ]; then
        psql -c "CREATE USER unified_inventory WITH ENCRYPTED PASSWORD 'helloSvcDevPass123456789abcdef';"
        psql -c "GRANT USAGE, CREATE ON SCHEMA public TO unified_inventory"
    fi
    if [ -z "$db_exists" ]; then
        psql -c "CREATE DATABASE unified_inventory_db WITH OWNER unified_inventory;"
    fi
kind: ConfigMap
metadata:
  labels:
    app.kubernetes.io/component: database
    app.kubernetes.io/instance: postgres-15-unified-inventory-service
    app.kubernetes.io/name: postgres-15
  name: unified-inventory-service-postgresql-init
```

#### `manifests/base/apps/unified-inventory-service/k8s/database.yaml`

```yaml
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  labels:
    app.kubernetes.io/component: database
    app.kubernetes.io/instance: postgres-15-unified-inventory-service
    app.kubernetes.io/name: postgres-15
    app.kubernetes.io/part-of: unified-inventory-service
  name: unified-inventory-service-postgres-15
spec:
  persistentVolumeClaimRetentionPolicy:
    whenDeleted: Retain
    whenScaled: Retain
  podManagementPolicy: OrderedReady
  replicas: 1
  revisionHistoryLimit: 10
  selector:
    matchLabels:
      app.kubernetes.io/component: database
      app.kubernetes.io/instance: postgres-15-unified-inventory-service
      app.kubernetes.io/name: postgres-15
  serviceName: unified-inventory-service
  template:
    metadata:
      labels:
        app.kubernetes.io/component: database
        app.kubernetes.io/instance: postgres-15-unified-inventory-service
        app.kubernetes.io/name: postgres-15
        app.kubernetes.io/part-of: unified-inventory-service
    spec:
      containers:
        - env:
            - name: POSTGRESQL_ADMIN_PASSWORD
              valueFrom:
                secretKeyRef:
                  key: postgres_admin_password
                  name: unified-inventory-service-postgres-configuration
            - name: POSTGRESQL_MAX_CONNECTIONS
              value: "1024"
            - name: POSTGRESQL_LOG_DESTINATION
              value: /dev/stderr
          image: localhost:5001/aap26/postgresql-15
          imagePullPolicy: IfNotPresent
          livenessProbe:
            exec:
              command:
                - bash
                - -c
                - pg_isready -p 5432 -d postgres
            failureThreshold: 3
            initialDelaySeconds: 45
            periodSeconds: 10
            successThreshold: 1
            timeoutSeconds: 2
          name: postgres
          ports:
            - containerPort: 5432
              name: postgres-15
              protocol: TCP
          resources:
            requests: {}
          volumeMounts:
            - mountPath: /var/lib/pgsql/data
              name: postgres-data
              subPath: data
            - mountPath: /opt/app-root/src/postgresql-start
              name: postgresql-init
      restartPolicy: Always
      terminationGracePeriodSeconds: 30
      volumes:
        - configMap:
            defaultMode: 420
            name: unified-inventory-service-postgresql-init
          name: postgresql-init
  updateStrategy:
    type: RollingUpdate
  volumeClaimTemplates:
    - apiVersion: v1
      kind: PersistentVolumeClaim
      metadata:
        name: postgres-data
      spec:
        accessModes:
          - ReadWriteOnce
        resources:
          requests:
            storage: 8Gi
        volumeMode: Filesystem
```

#### `manifests/base/apps/unified-inventory-service/k8s/register-job.yaml`

This job registers the service with the AAP gateway. Note: the `api_slug` must be
≤20 characters (gateway constraint), so we use `unified-inventory` as the slug
while keeping the full service name everywhere else.

```yaml
---
apiVersion: batch/v1
kind: Job
metadata:
  name: register-unified-inventory-service
spec:
  template:
    metadata:
      labels:
        app.kubernetes.io/name: register-unified-inventory-service
    spec:
      restartPolicy: Never
      containers:
        - name: register-unified-inventory-service
          image: __EE_SUPPORTED_IMAGE__
          imagePullPolicy: IfNotPresent
          command: [bash, -c]
          args:
            - |
              set -e
              cat <<'EOF' > /tmp/playbook.yaml
              ---
              - name: Playbook to register unified inventory service
                hosts: localhost
                connection: local
                vars:
                  gateway_username: "{{ gateway_admin_username }}"
                  gateway_password: "{{ gateway_admin_password }}"
                  gateway_hostname: "{{ gateway_host }}"
                  gateway_validate_certs: False
                  gateway_state: present
                module_defaults:
                  group/ansible.platform.gateway:
                    gateway_username: "{{ gateway_username }}"
                    gateway_password: "{{ gateway_password }}"
                    gateway_hostname: "{{ gateway_hostname }}"
                    gateway_validate_certs: "{{ gateway_validate_certs }}"
                    state: "{{ gateway_state }}"
                tasks:
                  - name: Check if API is available and returning status 200
                    uri:
                      url: "{{ gateway_hostname }}/api/gateway/v1/me/"
                      validate_certs: "{{ gateway_validate_certs }}"
                      method: GET
                      user: "{{ gateway_username }}"
                      password: "{{ gateway_password }}"
                      force_basic_auth: true
                    register: result
                    until: result.status == 200
                    retries: 60
                    delay: 15

                  - name: Manage service_type for unified inventory service
                    ansible.platform.service_type:
                      name: "unified-inventory-service"
                      ping_url: "/ping/"
                      service_index_path: "/api/unified-inventory-service/"

                  - name: Manage service_cluster for unified inventory service
                    ansible.platform.service_cluster:
                      name: "unified-inventory-service"
                      service_type: "unified-inventory-service"

                  - name: Manage service_node for unified inventory service
                    ansible.platform.service_node:
                      name: "Node unified-inventory-service"
                      service_cluster: "unified-inventory-service"
                      address: "unified-inventory-service"

                  - name: Manage service for unified inventory service
                    ansible.platform.service:
                      name: "unified inventory service api"
                      description: "Unified Inventory Service API"
                      api_slug: "unified-inventory"
                      http_port: "port-8000"
                      service_cluster: "unified-inventory-service"
                      is_service_https: false
                      service_path: "/api/unified-inventory-service/"
                      service_port: 8000
                      order: 10

                  - name: Manage route for unified inventory service
                    ansible.platform.route:
                      name: "unified inventory service ui"
                      description: "Unified Inventory Service UI"
                      gateway_path: "/unified-inventory-service/"
                      http_port: "port-8000"
                      service_cluster: "unified-inventory-service"
                      is_service_https: false
                      service_path: "/"
                      service_port: 8000
                      enable_gateway_auth: false
              ...
              EOF
              ansible-playbook /tmp/playbook.yaml \
                   -e gateway_username=$gateway_admin_username \
                   -e gateway_password=$gateway_admin_password \
                   -e gateway_host=$gateway_host
          env:
            - name: gateway_admin_username
              value: "admin"
            - name: gateway_admin_password
              valueFrom:
                secretKeyRef:
                  name: myaap-admin-password
                  key: password
            - name: gateway_host
              value: http://myaap-api.aap26.svc.cluster.local
```

### 3. Create the kustomize overlay

#### `manifests/overlays/addons/unified-inventory-service/kustomization.yaml`

```yaml
---
resources:
  - ../../../base/apps/unified-inventory-service/

images:
  - name: __UNIFIED_INVENTORY_SERVICE_IMAGE__
    newName: localhost:5001/aap26/unified-inventory-service
    newTag: latest
  - name: __EE_SUPPORTED_IMAGE__
    newName: localhost:5001/aap26/ee-supported-rhel9
    newTag: latest

namespace: aap26
```

### 4. Create the skaffold addon

#### `skaffolding/addons/unified-inventory-service/skaffold.yaml`

```yaml
---
apiVersion: skaffold/v4beta13
kind: Config
metadata:
  name: unified-inventory-service
build:
  tagPolicy:
    sha256: {}
  local:
    push: true
profiles:
  - name: unified-inventory-service
    activation:
      - env: AAP_UNIFIED_INVENTORY_SERVICE=true
      - env: AAP_VERSION=2.6
    requiresAllActivations: true
    build:
      artifacts:
        - image: localhost:5001/aap26/unified-inventory-service
          custom:
            buildCommand: |
              podman build -f ../../../src/unified-inventory-service/Containerfile -t $IMAGE ../../../src/unified-inventory-service/ && podman push --tls-verify=false $IMAGE
    deploy:
      kubectl:
        hooks:
          before:
            - host:
                command:
                  - "sh"
                  - "-c"
                  - "create-namespace-if-missing.sh ${AAP_KUBE_NAMESPACE}"
    manifests:
      kustomize:
        paths:
          - ../../../manifests/overlays/addons/unified-inventory-service
```

### 5. Register the addon in the root skaffold config

Add this entry to the `requires` list in `skaffolding/skaffold.yaml`:

```yaml
requires:
  # ... existing entries ...
  - configs: ["unified-inventory-service"]
    path: addons/unified-inventory-service/skaffold.yaml
```

### 6. Deploy

```bash
export AAP_UNIFIED_INVENTORY_SERVICE=true
export AAP_VERSION=2.6
make clean && make aap
```

The service will be available at `http://localhost:44926/api/unified-inventory/`.

Admin password:

```bash
make admin-password
```

### Verify

```bash
PASS=$(make admin-password 2>/dev/null | tail -1)
curl -s http://localhost:44926/api/unified-inventory/v1/ -u "admin:$PASS" | python3 -m json.tool
```

## Architecture Notes

- **Gateway slug**: `unified-inventory` (20-char gateway limit on `api_slug`)
- **Internal service name**: `unified-inventory-service` (used for K8s service, deployment, DNS)
- **Service prefix middleware**: Automatically strips `/api/unified-inventory-service/` prefix, so Django app routes are clean `/api/v1/...` internally
- **Database**: Dedicated PostgreSQL 15 instance (`unified_inventory_db`)
- **Authentication**: Via AAP gateway JWT — no direct auth on the service

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.
