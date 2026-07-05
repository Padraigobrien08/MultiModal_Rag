.PHONY: test lint format eval install-dev lock

install-dev:
	pip install -e ".[dev]"

lock:
	./scripts/lock-deps.sh

test:
	pytest tests/ -v

lint:
	ruff check stepwise tests scripts

format:
	ruff check --fix stepwise tests scripts
	ruff format stepwise tests scripts

eval:
	python scripts/run_eval.py --auto
