UV ?= uv
RUN := $(UV) run --offline
SOURCE_PATHS := pocket tests evals scripts

.PHONY: format lint test eval gate

format:
	$(RUN) ruff format $(SOURCE_PATHS)
	$(RUN) ruff check --fix $(SOURCE_PATHS)

lint:
	$(RUN) ruff format --check $(SOURCE_PATHS)
	$(RUN) ruff check $(SOURCE_PATHS)

test:
	$(RUN) pytest -q tests

eval:
	$(RUN) pytest -q evals/deterministic

gate: lint
	$(RUN) python -m compileall -q pocket tests evals scripts
	$(RUN) pytest -q tests evals/deterministic
