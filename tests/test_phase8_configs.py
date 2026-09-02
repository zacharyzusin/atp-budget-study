"""Phase 8 Cluster A pin triage — the new zoo configs load and carry the expected pins/formats.

These are config-loader regression tests, not behavioral tests: they lock in the pin-triage findings
(results/phase8/ZOO.md) so a future edit that silently drifts a revision/pin/template is caught by
`pytest -q` rather than discovered live in a GPU job.
"""

from __future__ import annotations

import pytest

from atp.config import load_config

# (config path, hf_repo) — all Cluster A "confirmed pin" configs share the Goedel Lean env
# (base.yaml's lean: section) unchanged, so no per-config lean.* override is expected.
_V15_TRIPLE = [
    ("configs/deepseek_v15_base_proofnet.yaml", "deepseek-ai/DeepSeek-Prover-V1.5-Base"),
    ("configs/deepseek_v15_sft_proofnet.yaml", "deepseek-ai/DeepSeek-Prover-V1.5-SFT"),
    ("configs/deepseek_v15_rl_proofnet.yaml", "deepseek-ai/DeepSeek-Prover-V1.5-RL"),
    ("configs/deepseek_v15_base_minif2f.yaml", "deepseek-ai/DeepSeek-Prover-V1.5-Base"),
    ("configs/deepseek_v15_sft_minif2f.yaml", "deepseek-ai/DeepSeek-Prover-V1.5-SFT"),
    ("configs/deepseek_v15_rl_minif2f.yaml", "deepseek-ai/DeepSeek-Prover-V1.5-RL"),
]


@pytest.mark.parametrize("path,hf_repo", _V15_TRIPLE)
def test_v15_triple_configs_share_the_goedel_pin(path, hf_repo):
    cfg = load_config(path)
    assert cfg.model.hf_repo == hf_repo
    assert cfg.model.prompt_template == "deepseek_v15"
    assert cfg.model.chat_completions is False
    assert cfg.model.max_model_len == 4096
    # Goedel's pin (base.yaml), NOT deepseek-lean-env's standard-mathlib pin — the triage finding.
    assert cfg.lean.toolchain == "leanprover/lean4:v4.9.0-rc1"
    assert "xinhjBrant" in cfg.lean.mathlib_repo
    assert cfg.lean.mathlib_commit == "2f65ba7f1a9144b20c8e7358513548e317d26de1"


def test_v15_triple_revisions_are_distinct():
    revisions = {load_config(p).model.revision for p, _ in _V15_TRIPLE[:3]}
    assert len(revisions) == 3, "each stage must pin its OWN revision, not accidentally share one"


_GOEDEL_SFT_CONFIGS = ["configs/goedel_sft_proofnet.yaml", "configs/goedel_sft_minif2f.yaml"]


@pytest.mark.parametrize("path", _GOEDEL_SFT_CONFIGS)
def test_goedel_sft_config(path):
    cfg = load_config(path)
    assert cfg.model.hf_repo == "Goedel-LM/Goedel-Prover-SFT"
    assert cfg.model.prompt_template == "goedel_sft"
    assert cfg.model.chat_completions is False
    assert cfg.lean.mathlib_commit == "2f65ba7f1a9144b20c8e7358513548e317d26de1"


def test_stp_config_flags_inferred_pin():
    cfg = load_config("configs/stp_proofnet.yaml")
    assert cfg.model.hf_repo == "kfdong/STP_model_Lean"
    # inferred (same lineage/benchmarks as the V1.5 triple), not GH-confirmed — see the config's own
    # header caveat; still expected to load and share the Goedel pin as its best-evidence default.
    assert cfg.model.prompt_template == "deepseek_v15"
    assert cfg.lean.mathlib_commit == "2f65ba7f1a9144b20c8e7358513548e317d26de1"


# Phase 8 step 3 — metric battery configs. These just override budget.values on top of the already-
# validated per-model configs above, so the only new thing worth locking in is the budget cap itself
# (atp-phase8-plan: "128k optional/lower priority given cost" — the battery runs 2k/8k/32k, not the
# full 128k ceiling every earlier phase used for the two-model headline).
_BATTERY_CONFIGS = [
    f"configs/{model}_{bench}_battery.yaml"
    for model in ["deepseek_v15_base", "deepseek_v15_sft", "deepseek_v15_rl", "goedel_sft"]
    for bench in ["proofnet", "minif2f"]
]


@pytest.mark.parametrize("path", _BATTERY_CONFIGS)
def test_battery_config_caps_budget_at_32k(path):
    cfg = load_config(path)
    assert cfg.budget.values == [2000, 8000, 32000]
    # headline numbers still need >=3 seeds (CONVENTIONS.md rule 7)
    assert cfg.eval.seeds == [0, 1, 2]


def test_battery_configs_still_carry_their_base_config_pin():
    # A battery override must not accidentally clobber the pin/template fields it doesn't touch.
    base_cfg = load_config("configs/deepseek_v15_rl_proofnet.yaml")
    battery_cfg = load_config("configs/deepseek_v15_rl_proofnet_battery.yaml")
    assert battery_cfg.model.hf_repo == base_cfg.model.hf_repo
    assert battery_cfg.model.revision == base_cfg.model.revision
    assert battery_cfg.lean.mathlib_commit == base_cfg.lean.mathlib_commit
