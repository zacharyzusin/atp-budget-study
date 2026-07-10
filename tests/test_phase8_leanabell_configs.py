"""Phase 8 second matched pair — Leanabell-Prover-GD-SFT/GD-RL config-loader regression tests.

Locks in the pin-triage findings (results/phase8/ZOO.md, PROGRESS.md 2026-07-06): both pins are
INFERRED (no GH-confirmable code for this lineage — the Leanabell-Prover GitHub repo has no code, just
a README/paper), so this is a stronger form of the STP precedent (configs/stp_proofnet.yaml). A future
edit that silently drifts a revision/pin/template should be caught by `pytest -q`, not discovered live.

PROMPT FORMAT REVISED 2026-07-06: the original `whole_proof`/chat_completions choice failed at real
battery scale (0/2025 solves — fence-truncation + out-of-context tactic errors, see PROGRESS.md same
date). Reverted to the already-validated raw-completion `goedel_sft` template (same one Goedel-Prover-
SFT and the V1.5 triple use) — these tests now lock in THAT choice, not the failed one.
"""
from __future__ import annotations

import pytest

from atp.config import load_config

_CONFIGS = [
    ("configs/leanabell_gdsft_minif2f.yaml", "stoney0062/Leanabell-Prover-GD-SFT",
     "7af62def7a964d3df962d14b6653601eec705620"),
    ("configs/leanabell_gdsft_proofnet.yaml", "stoney0062/Leanabell-Prover-GD-SFT",
     "7af62def7a964d3df962d14b6653601eec705620"),
    ("configs/leanabell_gdrl_minif2f.yaml", "stoney0062/Leanabell-Prover-GD-RL",
     "30f4ddf3dd1352dbaf2985df090131fb13b5236d"),
    ("configs/leanabell_gdrl_proofnet.yaml", "stoney0062/Leanabell-Prover-GD-RL",
     "30f4ddf3dd1352dbaf2985df090131fb13b5236d"),
]


@pytest.mark.parametrize("path,hf_repo,revision", _CONFIGS)
def test_leanabell_config_pin_and_format(path, hf_repo, revision):
    cfg = load_config(path)
    assert cfg.model.hf_repo == hf_repo
    assert cfg.model.revision == revision
    assert cfg.model.max_model_len == 8192   # config.json's own max_position_embeddings
    assert cfg.model.prompt_template == "goedel_sft"
    assert cfg.model.chat_completions is False
    # inferred, not GH-confirmed (no code in the Leanabell-Prover repo) — best-evidence reuse of the
    # Goedel pin, same class of inference as STP's config.
    assert cfg.lean.mathlib_commit == "2f65ba7f1a9144b20c8e7358513548e317d26de1"


def test_leanabell_gdsft_and_gdrl_are_distinct_checkpoints():
    sft = load_config("configs/leanabell_gdsft_proofnet.yaml")
    rl = load_config("configs/leanabell_gdrl_proofnet.yaml")
    assert sft.model.hf_repo != rl.model.hf_repo
    assert sft.model.revision != rl.model.revision


def test_leanabell_smoke_configs_are_small():
    # Bumped from 2 to 8 problems for the post-fix re-smoke (coordinator's ask: "a handful of
    # problems," bigger than the original 2-problem smoke that didn't catch the format problem).
    for path in ["configs/leanabell_gdsft_smoke.yaml", "configs/leanabell_gdrl_smoke.yaml"]:
        cfg = load_config(path)
        assert cfg.data.limit == 8
        assert cfg.budget.values == [8000]
        assert cfg.eval.seeds == [0]


_LEANABELL_BATTERY = [
    f"configs/leanabell_{model}_{bench}_battery.yaml"
    for model in ["gdsft", "gdrl"]
    for bench in ["proofnet", "minif2f"]
]


@pytest.mark.parametrize("path", _LEANABELL_BATTERY)
def test_leanabell_battery_config_caps_budget_at_32k(path):
    # Capped at 32k (not the coordinator's literally-requested 128k) — coordinator approved this
    # scope 2026-07-06 to stay apples-to-apples with the V1.5 triple's own battery cap and to keep
    # incremental GPU-h under the ask-first threshold (full 128k estimated at 300+ GPU-h incremental).
    cfg = load_config(path)
    assert cfg.budget.values == [2000, 8000, 32000]
    assert cfg.eval.seeds == [0, 1, 2]
