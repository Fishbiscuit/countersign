# Countersign: console + agent endpoint + gateway in one container.

FROM node:22.11-slim AS console
WORKDIR /app/console
COPY console/package.json console/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY console/ ./
RUN npx vite build

FROM python:3.12.8-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    COUNTERSIGN_HOST=0.0.0.0 \
    COUNTERSIGN_DATA_DIR=/data
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY gateway/ gateway/
COPY countersign/ countersign/
COPY demo/ demo/
COPY bench/ bench/
RUN uv sync --frozen --no-dev
COPY --from=console /app/console/dist console/dist
RUN mkdir -p /data && useradd --create-home countersign && chown -R countersign /data /app
USER countersign
EXPOSE 8484
HEALTHCHECK CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8484\")}/api/status')"
CMD ["countersign", "serve"]
