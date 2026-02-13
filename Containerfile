# =============================================================================
# DEVELOPMENT ONLY - DO NOT USE IN PRODUCTION
# =============================================================================
# This Containerfile is for local development and testing only.
# It uses Django's runserver which is not suitable for production workloads.
# =============================================================================

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_LINK_MODE=copy
ENV UV_NO_CACHE=1

WORKDIR /app

# Install git (required for django-ansible-base and dispatcherd from git)
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml uv.lock* ./

# Install dependencies — regenerate lock if needed (dev convenience)
# Retry logic: github.com can be unreachable during parallel podman builds
RUN for i in 1 2 3 4 5; do \
      (uv lock --upgrade-package dispatcherd 2>/dev/null; uv sync --no-install-project) && break; \
      echo "=== Attempt $i failed, retrying in 5s... ==="; \
      sleep 5; \
    done

# Copy application code
COPY . .

# Ensure files are writable for Skaffold sync (dev container runs as uid 1000)
RUN chmod -R a+rw /app

# Install the project
RUN uv sync

EXPOSE 8000

# Default: run web server.  Override CMD to run the dispatcher worker:
#   CMD ["uv", "run", "--no-sync", "python", "manage.py", "run_dispatcher"]
CMD ["/bin/sh", "-c", "uv run --no-sync python manage.py migrate && uv run --no-sync python manage.py runserver 0.0.0.0:8000"]
