# Dependency installation uses the same lockfile as local development and CI.
FROM ghcr.io/astral-sh/uv:0.12.23@sha256:61d393e44e249f2e4b526b6c7ddcecce245946826e608e11c93ad4f5bba55b21 AS uv
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS builder
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock README.md ./
COPY system_monitoring ./system_monitoring
# Optional CA bundle supports enterprise/cloud HTTPS proxies without copying
# their trust configuration into the image or disabling certificate validation.
RUN --mount=type=secret,id=ca-certificates \
    if [ -f /run/secrets/ca-certificates ]; then \
      export SSL_CERT_FILE=/run/secrets/ca-certificates UV_SYSTEM_CERTS=true; \
    fi; \
    uv sync --locked --no-dev --no-editable

FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS runtime
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MONITOR_DATABASE_PATH=/var/lib/system-monitoring/monitoring.sqlite3
RUN groupadd --gid 10001 monitoring \
    && useradd --uid 10001 --gid monitoring --no-create-home monitoring \
    && mkdir -p /var/lib/system-monitoring \
    && chown monitoring:monitoring /var/lib/system-monitoring
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
USER monitoring
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=2)"]
CMD ["uvicorn", "system_monitoring.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
