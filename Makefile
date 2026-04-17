SHELL := /bin/sh

.PHONY: install format lint typecheck test check build docker-build

install:
	uv sync --extra dev

format:
	uv run ruff format src tests

lint:
	uv run ruff check src tests

typecheck:
	uv run mypy

test:
	uv run pytest

check:
	uv run ruff format --check src tests
	uv run ruff check src tests
	uv run mypy
	uv run pytest

build:
	uv build

docker-build:
	docker build --pull --target runtime -t voxcpm-wyomming:latest .
