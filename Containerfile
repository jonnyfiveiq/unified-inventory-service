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

# Install git (used by uv build tooling)
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy all source including vendor deps before installing
COPY pyproject.toml uv.lock* ./
COPY _vendor ./_vendor

# Install dependencies (vendor paths only, no network needed)
RUN uv sync --no-install-project

# Copy application code
COPY . .

# Ensure files are writable for Skaffold sync (dev container runs as uid 1000)
RUN chmod -R a+rw /app

# Install the project
RUN uv sync

EXPOSE 8000

ENTRYPOINT ["/bin/sh", "entrypoint.sh"]

# Default: run web server.  Override CMD to run the dispatcher worker:
#   CMD ["uv", "run", "--no-sync", "python", "manage.py", "run_dispatcher"]
CMD ["uv", "run", "--no-sync", "python", "manage.py", "runserver", "0.0.0.0:8000"]
