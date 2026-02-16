CONTAINER_RUNTIME ?= podman
COMPOSE_COMMAND ?= podman compose
IMAGE_NAME ?= inventory-service
IMAGE_TAG ?= latest

# Database defaults (matches compose.yaml / settings.local.py)
DB_NAME ?= inventory_db
DB_USER ?= inventory
DB_PASS ?= inventory123
DB_HOST ?= localhost
DB_PORT ?= 5532

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-24s\033[0m %s\n", $$1, $$2}'

# ── Container Compose ────────────────────────────────────────────────
.PHONY: compose-build
compose-build: ## Build container images
	$(COMPOSE_COMMAND) -f tools/podman/compose.yaml build

.PHONY: compose-up
compose-up: ## Start all services (postgres + api)
	$(COMPOSE_COMMAND) -f tools/podman/compose.yaml up --remove-orphans $(COMPOSE_UP_OPTS)

.PHONY: compose-down
compose-down: ## Stop and remove containers, volumes
	$(COMPOSE_COMMAND) -f tools/podman/compose.yaml down --remove-orphans --rmi local -v

.PHONY: compose-restart
compose-restart: compose-down compose-up ## Full restart

# ── Local dev (postgres via compose, Django on host) ─────────────────
.PHONY: db-up
db-up: ## Start postgres only (for local dev)
	$(COMPOSE_COMMAND) -f tools/podman/compose.yaml up -d postgres

.PHONY: db-down
db-down: ## Stop postgres
	$(COMPOSE_COMMAND) -f tools/podman/compose.yaml down postgres

.PHONY: db-shell
db-shell: ## Open psql shell to inventory_db
	PGPASSWORD=$(DB_PASS) psql -h $(DB_HOST) -p $(DB_PORT) -U $(DB_USER) -d $(DB_NAME)

.PHONY: db-inspect
db-inspect: ## Run inventory inspection queries
	./inspect_inventory.sh

# ── Django management ────────────────────────────────────────────────
.PHONY: migrate
migrate: ## Run Django migrations
	.venv/bin/python manage.py migrate

.PHONY: seed
seed: ## Seed multi-vendor test data (flush + re-seed)
	.venv/bin/python manage.py seed_multivendor_data --flush

.PHONY: runserver
runserver: ## Run Django dev server
	.venv/bin/python manage.py runserver

.PHONY: superuser
superuser: ## Create superuser
	.venv/bin/python manage.py createsuperuser
