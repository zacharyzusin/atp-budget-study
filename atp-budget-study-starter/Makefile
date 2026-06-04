# Makefile — convenience targets. See CLAUDE.md / PROJECT_PLAN.md.

PROJECT_ROOT := /insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study
ENV_PATH     := $(PROJECT_ROOT)/scratch/conda-envs/atp

.PHONY: test test-all smoke lint format env help

help:
	@echo "test      - fast suite (login-node safe; excludes slow/gpu/lean)"
	@echo "test-all  - full suite incl. slow/gpu/lean (run on a GPU node)"
	@echo "smoke     - tiny 2-5 problem end-to-end sanity run"
	@echo "lint      - ruff check"
	@echo "format    - ruff format + import sort"
	@echo "env       - print the conda activate line for this cluster"

test:
	pytest -m "not slow and not gpu and not lean"

test-all:
	pytest

smoke:
	python -m atp.cli prove --config configs/smoke.yaml --resume

lint:
	ruff check src tests

format:
	ruff format src tests && ruff check --fix src tests

env:
	@echo "module load anaconda/2023.09 && conda activate $(ENV_PATH)"
