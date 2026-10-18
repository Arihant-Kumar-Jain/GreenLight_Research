# One container: React UI + FastAPI agents. No GPU: inference runs on Nebius Token Factory.
FROM node:22-slim AS web
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/glr ./glr
RUN uv sync --frozen --no-dev
# api.py serves REPO_DIR/web/dist, so keep backend/ and web/dist side by side.
COPY --from=web /app/web/dist /app/web/dist
RUN useradd --system --uid 10001 glr && mkdir -p /data && chown glr /data
USER glr
ENV GLR_DB_PATH=/data/glr.db PATH=/app/backend/.venv/bin:$PATH
EXPOSE 8100
# One worker on purpose: research runs are asyncio tasks inside this process.
CMD ["uvicorn", "glr.api:app", "--host", "0.0.0.0", "--port", "8100"]
