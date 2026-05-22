# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder

WORKDIR /app

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/venv/bin:$PATH

RUN python -m venv /opt/venv

COPY pyproject.toml README.md ./
COPY src ./src

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip build && \
    python -m build --wheel --outdir /tmp/dist && \
    pip install /tmp/dist/*.whl

FROM python:3.12-slim AS runtime

WORKDIR /app

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && \
    apt-get install --no-install-recommends --yes ffmpeg && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home --no-log-init app
USER app

CMD ["csv2gpx-web", "--host", "0.0.0.0"]
