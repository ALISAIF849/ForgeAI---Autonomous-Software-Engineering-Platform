# Development image: optimizes for correctness and hot-reload, not image size or
# build-cache layering — see docs/engineering/07-docker-strategy.md for why a leaner,
# multi-stage production image is separate, later work (tied to deployment, out of
# scope for Sprint 1). Copies the whole repo because this is a uv workspace — apps/api
# depends on services/core, which depends on the workspace root's lockfile.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY . .
RUN uv sync --all-packages

EXPOSE 8000

CMD ["uv", "run", "--package", "forgeai-api", "uvicorn", "forgeai_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
