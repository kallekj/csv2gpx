# VoxCPM Wyoming Service

Wyoming TCP text-to-speech service powered by VoxCPM.

This service targets Home Assistant Wyoming integration and currently supports:

- `describe` -> `info`
- `synthesize` -> `audio-start` / `audio-chunk` / `audio-stop`

Streaming text synthesis (`synthesize-start` / `synthesize-chunk` / `synthesize-stop`) is intentionally disabled in this release.

## Requirements

- Linux
- NVIDIA GPU + CUDA runtime
- VoxCPM model (local path or HuggingFace repo id)
- `flash-attn` compatible environment if using `nano-vllm-voxcpm`

## Install

Install dev tooling:

```bash
uv sync --extra dev
```

Install VoxCPM runtime extra:

```bash
uv sync --extra voxcpm
```

## Dev Container (CUDA + Docker-in-Docker)

This repository includes a VS Code dev container configuration in `.devcontainer/`.

Prerequisites on the host machine:

- Docker Engine
- NVIDIA Container Toolkit (GPU-enabled Docker runtime)
- VS Code with the Dev Containers extension

Start the dev container:

```bash
code .
```

Then run **Dev Containers: Reopen in Container** from the VS Code command palette.

What this setup provides:

- CUDA-enabled Ubuntu 24.04 base image
- Python 3.12 toolchain
- Docker-in-Docker daemon inside the dev container
- Automatic bootstrap of dev dependencies via `uv sync --extra dev`

Quick checks inside the container:

```bash
nvidia-smi
docker version
make test
```

## Run

Minimal run:

```bash
uv run voxcpm --model /path/to/VoxCPM --host 0.0.0.0 --port 10200 --devices 0
```

Using environment variables:

```bash
export VOXCPM_MODEL=/path/to/VoxCPM
export VOXCPM_HOST=0.0.0.0
export VOXCPM_PORT=10200
export VOXCPM_DEVICES=0
uv run voxcpm
```

## Home Assistant Wyoming

Point Home Assistant Wyoming TTS integration to:

```text
tcp://<service-host>:10200
```

Voice metadata is configurable through CLI/env values:

- `--service-name`
- `--voice-name`
- `--voice-language`
- `--voice-speaker`

## Quality Commands

```bash
make format
make lint
make typecheck
make test
make check
```

## Docker Notes

The included `Dockerfile` keeps a lightweight Python runtime image for packaging workflows.

For production GPU inference, use this project as an application layer in a CUDA-enabled base image and install the `voxcpm` extra in that image:

```bash
pip install "voxcpm-wyomming[voxcpm]"
```
