# Makefile — convenience targets. See README.md §7 and CONVENTIONS.md.

PROJECT_ROOT := /insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study
ENV_PATH     := $(PROJECT_ROOT)/scratch/conda-envs/atp

CONFIG ?= configs/phase0_baseline.yaml
NAME   ?= baseline

.PHONY: test test-all smoke lint format env eval baseline verify help

help:
	@echo "verify    - fast suite + lint. The gate before any commit."
	@echo "test      - fast suite (login-node safe; excludes slow/gpu/lean)"
	@echo "test-all  - full suite incl. slow/gpu/lean (run on a GPU node)"
	@echo "smoke     - tiny 2-5 problem end-to-end sanity run"
	@echo "lint      - ruff check (src, tests, scripts)"
	@echo "format    - ruff format + import sort"
	@echo "env       - print the conda activate line for this cluster"
	@echo "eval      - run the eval sweep locally (needs a live vLLM endpoint + Goedel-pin env)"
	@echo "baseline  - sbatch the one-command baseline (vLLM + sweep) on an l40s GPU node"

test:
	pytest -m "not slow and not gpu and not lean"

test-all:
	pytest

smoke:
	python -m atp.cli prove --config configs/smoke.yaml --resume

lint:
	ruff check src tests scripts

format:
	ruff format src tests scripts && ruff check --fix src tests scripts

verify: test lint
	@echo "verify: OK (fast suite green, lint clean)"

env:
	@echo "module load anaconda/2023.09 && conda activate $(ENV_PATH)"

eval:
	python -m atp.cli sweep --config $(CONFIG) --name $(NAME) --resume

baseline:
	sbatch slurm/sweep.sh $(CONFIG) $(NAME)
