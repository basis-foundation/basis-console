.PHONY: install test lint format typecheck check run

install:
	python -m pip install -e ".[dev]"

test:
	python -m pytest

lint:
	ruff check .

format:
	ruff format --check .

typecheck:
	mypy src

check: lint format typecheck test

run:
	uvicorn basis_console.main:app --host $(or $(HOST),127.0.0.1) --port $(or $(PORT),8080)
