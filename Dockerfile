# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

FROM base AS builder
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip install --upgrade pip build
RUN python -m build --wheel --outdir /tmp/dist

FROM base AS runtime
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home --no-log-init app

COPY --from=builder /tmp/dist/*.whl /tmp/dist/
RUN python -m pip install --no-cache-dir /tmp/dist/*.whl && rm -rf /tmp/dist

ENV VOXCPM_HOST=0.0.0.0 \
    VOXCPM_PORT=10200
EXPOSE 10200

USER app
CMD ["python", "-m", "voxcpm_wyomming"]
