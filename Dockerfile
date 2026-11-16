# One immutable image for every process (ADR-0004):
#   web:     gunicorn sallimha.wsgi (default command) — API, webhook and the built console on one origin
#   worker:  python manage.py run_worker
#   release: python manage.py migrate --noinput && python manage.py deploy_check
# No secrets are baked in; SALLIMHA_ENV and all keys come from the platform's secret store at run time.

FROM node:24-slim AS console
WORKDIR /src/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY apps/web/ ./
COPY brand/ /src/brand/
RUN npm run build

FROM python:3.14-slim AS app
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH" CONSOLE_DIST=/app/console
WORKDIR /app/api
COPY services/api/pyproject.toml services/api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY services/api/ ./
COPY --from=console /src/apps/web/dist /app/console
RUN useradd --system --uid 10001 --home /app sallimha && chown -R sallimha /app
USER sallimha
EXPOSE 8000
CMD ["gunicorn", "sallimha.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "30", \
     "--access-logfile", "-"]
