FROM python:3.13-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN python -m pip install --no-cache-dir --upgrade pip uv

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src

RUN uv sync --frozen --no-dev --no-editable


FROM python:3.13-slim AS runtime

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CRUCIBLE_ENV=docker \
    CRUCIBLE_DASHBOARD_HOST=0.0.0.0 \
    CRUCIBLE_RUNS_DIR=/data/runs \
    CRUCIBLE_CACHE_DIR=/data/cache \
    CRUCIBLE_REPORTS_DIR=/data/reports \
    CRUCIBLE_SQLITE_PATH=/data/crucible.sqlite

WORKDIR /workspace

RUN groupadd --system crucible \
    && useradd --system --gid crucible --home-dir /workspace crucible \
    && mkdir -p /data /workspace \
    && chown -R crucible:crucible /data /workspace

COPY --from=builder --chown=crucible:crucible /app/.venv /app/.venv

USER crucible

VOLUME ["/data", "/workspace"]
EXPOSE 7777 7788

ENTRYPOINT ["crucible"]
CMD ["serve", "--host", "0.0.0.0", "--port", "7777"]
