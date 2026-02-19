#!/bin/bash
# setup-aap-dev.sh — Wire inventory-service into a freshly sync'd aap-dev checkout.
#
# Run this from the root of your aap-dev repo after cloning/syncing:
#
#   cd ~/upstream/aap-dev
#   src/inventory-service/setup-aap-dev.sh
#
# Idempotent — safe to re-run. Skips files/patches already applied.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AAP_DEV_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

GREEN='\033[0;32m'; YELLOW='\033[0;33m'; CYAN='\033[0;36m'; RESET='\033[0m'
ok()   { echo -e "  ${GREEN}✓${RESET} $1"; }
skip() { echo -e "  ${YELLOW}⊘${RESET} $1 (already done)"; }
info() { echo -e "  ${CYAN}→${RESET} $1"; }

echo -e "\n${CYAN}━━━ inventory-service aap-dev setup ━━━${RESET}"
echo "aap-dev root: $AAP_DEV_ROOT"

write_file() {
  local path="$1"; shift
  if [ -f "$path" ]; then skip "$path"; return; fi
  mkdir -p "$(dirname "$path")"
  cat > "$path"
  ok "Created $path"
}   podman push --tls-verify=false $IMAGE
            dependencies:
              paths:
                - src/inventory-service/**/*.py
                - src/inventory-service/pyproject.toml
                - src/inventory-service/uv.lock
                - src/inventory-service/Containerfile
          sync:
            manual:
              - src: "src/inventory-service/apps/**/*.py"
                strip: "src/inventory-service"
                dest: "/app"
              - src: "src/inventory-service/inventory_service/**/*.py"
                strip: "src/inventory-service"
                dest: "/app"
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
          - ../../../manifests/overlays/addons/inventory-service
EOF

# ── 4. manifests/base/apps/inventory-service/ ───────────────────────────────
BASE="${AAP_DEV_ROOT}/manifests/base/apps/inventory-service"

write_file "${BASE}/kustomization.yaml" << 'EOF'
---
resources:
  - k8s/deployments.yaml
  - k8s/services.yaml
  - k8s/register-job.yaml
  - k8s/configmap.yaml
  - k8s/secrets.yaml
  - k8s/database.yaml
  - k8s/plugins-pvc.yaml
EOF

write_file "${BASE}/k8s/configmap.yaml" << 'EOF'
---
apiVersion: v1
data:
  init_component_dbs.sh: |
    db_exists=$(psql -tAc "SELECT 1 FROM pg_database WHERE datname='inventory_db'")
    user_exists=$(psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='inventory_svc'")
    if [ -z "$user_exists" ]; then
        psql -c "CREATE USER inventory_svc WITH ENCRYPTED PASSWORD 'helloSvcDevPass123456789abcdef';"
        psql -c "GRANT USAGE, CREATE ON SCHEMA public TO inventory_svc"
    fi
    if [ -z "$db_exists" ]; then
        psql -c "CREATE DATABASE inventory_db WITH OWNER inventory_svc;"
    fi
kind: ConfigMap
metadata:
  labels:
    app.kubernetes.io/component: database
    app.kubernetes.io/instance: postgres-15-inventory-service
    app.kubernetes.io/name: postgres-15
  name: inventory-service-postgresql-init
EOF

write_file "${BASE}/k8s/secrets.yaml" << 'EOF'
---
apiVersion: v1
kind: Secret
metadata:
  name: inventory-service-postgres-configuration
type: Opaque
stringData:
  database: inventory_db
  host: inventory-service-postgres-15
  password: helloSvcDevPass123456789abcdef # notsecret
  port: "5432"
  postgres_admin_password: helloSvcAdminPass987654321xyz # notsecret
  type: managed
  username: inventory_svc
EOF

write_file "${BASE}/k8s/services.yaml" << 'EOF'
---
apiVersion: v1
kind: Service
metadata:
  name: inventory-service
  labels:
    app: inventory-service
spec:
  selector:
    app: inventory-service
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
    app.kubernetes.io/instance: postgres-15-inventory-service
    app.kubernetes.io/name: postgres-15
  name: inventory-service-postgres-15
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
    app.kubernetes.io/instance: postgres-15-inventory-service
    app.kubernetes.io/name: postgres-15
EOF

write_file "${BASE}/k8s/plugins-pvc.yaml" << 'EOF'
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: inventory-service-plugins
  labels:
    app: inventory-service
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
EOF

write_file "${BASE}/k8s/database.yaml" << 'EOF'
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  labels:
    app.kubernetes.io/component: database
    app.kubernetes.io/instance: postgres-15-inventory-service
    app.kubernetes.io/name: postgres-15
    app.kubernetes.io/part-of: inventory-service
  name: inventory-service-postgres-15
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
      app.kubernetes.io/instance: postgres-15-inventory-service
      app.kubernetes.io/name: postgres-15
  serviceName: inventory-service
  template:
    metadata:
      labels:
        app.kubernetes.io/component: database
        app.kubernetes.io/instance: postgres-15-inventory-service
        app.kubernetes.io/name: postgres-15
        app.kubernetes.io/part-of: inventory-service
    spec:
      containers:
        - env:
            - name: POSTGRESQL_ADMIN_PASSWORD
              valueFrom:
                secretKeyRef:
                  key: postgres_admin_password
                  name: inventory-service-postgres-configuration
            - name: POSTGRESQL_MAX_CONNECTIONS
              value: "1024"
            - name: POSTGRESQL_LOG_DESTINATION
              value: /dev/stderr
          image: localhost:5001/aap26/postgresql-15
          imagePullPolicy: IfNotPresent
          livenessProbe:
            exec:
              command: [bash, -c, "pg_isready -p 5432 -d postgres"]
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
            name: inventory-service-postgresql-init
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
EOF

write_file "${BASE}/k8s/deployments.yaml" << 'EOF'
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory-service
  labels:
    app: inventory-service
spec:
  replicas: 1
  selector:
    matchLabels:
      app: inventory-service
  template:
    metadata:
      labels:
        app: inventory-service
    spec:
      containers:
        - name: inventory-service
          image: __INVENTORY_SERVICE_IMAGE__
          imagePullPolicy: Always
          ports:
            - containerPort: 8000
          volumeMounts:
            - name: plugins
              mountPath: /app/plugins
          env:
            - name: INVENTORY_SERVICE_DATABASES__default__ENGINE
              value: django.db.backends.postgresql
            - name: INVENTORY_SERVICE_DATABASES__default__HOST
              valueFrom:
                secretKeyRef:
                  key: host
                  name: inventory-service-postgres-configuration
            - name: INVENTORY_SERVICE_DATABASES__default__NAME
              valueFrom:
                secretKeyRef:
                  key: database
                  name: inventory-service-postgres-configuration
            - name: INVENTORY_SERVICE_DATABASES__default__PORT
              valueFrom:
                secretKeyRef:
                  key: port
                  name: inventory-service-postgres-configuration
            - name: INVENTORY_SERVICE_DATABASES__default__USER
              valueFrom:
                secretKeyRef:
                  key: username
                  name: inventory-service-postgres-configuration
            - name: INVENTORY_SERVICE_DATABASES__default__PASSWORD
              valueFrom:
                secretKeyRef:
                  key: password
                  name: inventory-service-postgres-configuration
            - name: INVENTORY_SERVICE_ALLOWED_HOSTS
              value: '["localhost","127.0.0.1","0.0.0.0","inventory-service"]'
            - name: INVENTORY_SERVICE_AAP_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: myaap-admin-password
                  key: password
            - name: INVENTORY_SERVICE_ANSIBLE_BASE_JWT_KEY
              value: http://myaap-api.aap26.svc.cluster.local
            - name: INVENTORY_SERVICE_ANSIBLE_BASE_JWT_VALIDATE_CERT
              value: "False"
            - name: INVENTORY_SERVICE_SERVICE_PREFIX
              value: "inventory"
        - name: dispatcher
          image: __INVENTORY_SERVICE_IMAGE__
          imagePullPolicy: Always
          command: ["sh", "-c", "uv run --no-sync python manage.py run_dispatcher"]
          volumeMounts:
            - name: plugins
              mountPath: /app/plugins
          env:
            - name: INVENTORY_SERVICE_DATABASES__default__ENGINE
              value: django.db.backends.postgresql
            - name: INVENTORY_SERVICE_DATABASES__default__HOST
              valueFrom:
                secretKeyRef:
                  key: host
                  name: inventory-service-postgres-configuration
            - name: INVENTORY_SERVICE_DATABASES__default__NAME
              valueFrom:
                secretKeyRef:
                  key: database
                  name: inventory-service-postgres-configuration
            - name: INVENTORY_SERVICE_DATABASES__default__PORT
              valueFrom:
                secretKeyRef:
                  key: port
                  name: inventory-service-postgres-configuration
            - name: INVENTORY_SERVICE_DATABASES__default__USER
              valueFrom:
                secretKeyRef:
                  key: username
                  name: inventory-service-postgres-configuration
            - name: INVENTORY_SERVICE_DATABASES__default__PASSWORD
              valueFrom:
                secretKeyRef:
                  key: password
                  name: inventory-service-postgres-configuration
            - name: INVENTORY_SERVICE_ALLOWED_HOSTS
              value: '["localhost","127.0.0.1","0.0.0.0","inventory-service"]'
            - name: INVENTORY_SERVICE_AAP_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: myaap-admin-password
                  key: password
            - name: INVENTORY_SERVICE_ANSIBLE_BASE_JWT_KEY
              value: http://myaap-api.aap26.svc.cluster.local
            - name: INVENTORY_SERVICE_ANSIBLE_BASE_JWT_VALIDATE_CERT
              value: "False"
            - name: INVENTORY_SERVICE_SERVICE_PREFIX
              value: "inventory"
      volumes:
        - name: plugins
          persistentVolumeClaim:
            claimName: inventory-service-plugins
EOF

write_file "${BASE}/k8s/register-job.yaml" << 'EOF'
---
apiVersion: batch/v1
kind: Job
metadata:
  name: register-inventory-service
spec:
  template:
    metadata:
      labels:
        app.kubernetes.io/name: register-inventory-service
    spec:
      restartPolicy: Never
      containers:
        - name: register-inventory-service
          image: __EE_SUPPORTED_IMAGE__
          imagePullPolicy: IfNotPresent
          command: [bash, -c]
          args:
            - |
              set -e
              cat <<'PLAYBOOK' > /tmp/playbook.yaml
              ---
              - name: Register inventory service with AAP Gateway
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
                  - name: Wait for Gateway API
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
                  - name: service_type
                    ansible.platform.service_type:
                      name: "inventory-service"
                      ping_url: "/ping/"
                      service_index_path: "/api/inventory/"
                  - name: service_cluster
                    ansible.platform.service_cluster:
                      name: "inventory-service"
                      service_type: "inventory-service"
                  - name: service_node
                    ansible.platform.service_node:
                      name: "Node inventory-service"
                      service_cluster: "inventory-service"
                      address: "inventory-service"
                  - name: service
                    ansible.platform.service:
                      name: "inventory service api"
                      description: "Inventory Service API"
                      api_slug: "inventory"
                      http_port: "port-8000"
                      service_cluster: "inventory-service"
                      is_service_https: false
                      service_path: "/api/inventory/"
                      service_port: 8000
                      order: 10
                  - name: route
                    ansible.platform.route:
                      name: "inventory service ui"
                      description: "Inventory Service UI"
                      gateway_path: "/inventory-service/"
                      http_port: "port-8000"
                      service_cluster: "inventory-service"
                      is_service_https: false
                      service_path: "/"
                      service_port: 8000
                      enable_gateway_auth: false
              ...
              PLAYBOOK
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
EOF

# ── 5. manifests/overlays/addons/inventory-service/ ─────────────────────────
OVERLAY="${AAP_DEV_ROOT}/manifests/overlays/addons/inventory-service"

write_file "${OVERLAY}/kustomization.yaml" << 'EOF'
---
resources:
  - ../../../base/apps/inventory-service/
images:
  - name: __INVENTORY_SERVICE_IMAGE__
    newName: localhost:5001/aap26/inventory-service
    newTag: latest
  - name: __EE_SUPPORTED_IMAGE__
    newName: localhost:5001/aap26/ee-supported-rhel9
    newTag: latest
namespace: aap26
EOF

echo -e "\n${GREEN}━━━ Setup complete ━━━${RESET}"
echo "All inventory-service files wired into aap-dev. Run ./deploy.sh to deploy."
