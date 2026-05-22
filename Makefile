SHELL := /bin/sh

.PHONY: install format lint typecheck test check build docker-build docker-run

install:
	uv sync --extra dev

format:
	uv run --extra dev ruff format src tests

lint:
	uv run --extra dev ruff check src tests

typecheck:
	uv run --extra dev mypy

test:
	uv run --extra dev pytest

check:
	uv run --extra dev ruff format --check src tests
	uv run --extra dev ruff check src tests
	uv run --extra dev mypy
	uv run --extra dev pytest

build:
	uv build

docker-build:
	docker build --pull --target runtime -t csv2gpx:latest .

docker-run:
	docker run --rm -p 8000:8000 csv2gpx:latest
