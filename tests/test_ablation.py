"""Tests for Phase 1 ablation expansion (Task 1.4) + the `atp ablation` CLI.

Pure config algebra — no GPU/Lean. Drives the real `configs/phase1_ablation.yaml` so the test
guards the actual sweep the team will launch, plus a tiny synthetic sweep for edge cases.
"""

from __future__ import annotations

import pytest

from atp.agents import WholeProofAgent
from atp.cli import main
from atp.config import CONFIGS_DIR, ExperimentConfig, config_hash, dump_config, load_config
from atp.eval.ablation import (
    BASELINE,
    ablation_manifest,
    expand_ablation,
    validate_cells,
)

PHASE1 = CONFIGS_DIR / "phase1_ablation.yaml"

# The retrieval cell validates against the BM25 premise corpus, a large build artifact that lives in
# gitignored scratch/ (built by scripts/build_premise_corpus.py). Absent in a fresh clone.
_PREMISE_CORPUS = list((CONFIGS_DIR.parent / "scratch" / "premises").glob("*.jsonl"))
needs_premise_corpus = pytest.mark.skipif(
    not _PREMISE_CORPUS,
    reason="needs scratch/premises/*.jsonl (build with scripts/build_premise_corpus.py)",
)
PHASE1_SMOKE = CONFIGS_DIR / "phase1_ablation_smoke.yaml"


def _names(cells):
    return [c.name for c in cells]


def test_expand_phase1_baseline_first_and_runnable_axes():
    cells = expand_ablation(load_config(PHASE1))
    assert cells[0].name == BASELINE and cells[0].axis == BASELINE
    axes = {c.axis for c in cells} - {BASELINE}
    # The currently-runnable axes (generation_mode's bfs variant is deferred → that axis's only
    # remaining variant equals baseline and dedups away, so it's absent until BFS lands).
    assert axes == {"budget_alloc", "memory", "reviewer", "retrieval", "tactic_skeletons"}
    # Names + configs are unique (hash-dedup removed the baseline-equal control variants).
    assert len(set(_names(cells))) == len(cells)
    hashes = [config_hash(c.config) for c in cells]
    assert len(set(hashes)) == len(hashes)
    assert all(isinstance(c.config, ExperimentConfig) for c in cells)


def test_baseline_cell_has_all_components_off():
    base = next(c for c in expand_ablation(load_config(PHASE1)) if c.name == BASELINE)
    comp = base.config.agent.components
    assert not (comp.memory.enabled or comp.reviewer.enabled
                or comp.retrieval.enabled or comp.tactic_skeletons.enabled)


def test_ofat_each_variant_differs_only_in_its_axis():
    cells = expand_ablation(load_config(PHASE1))
    base = next(c for c in cells if c.name == BASELINE)
    base_d = dump_config(base.config)
    # The memory "on" variant flips exactly memory.enabled and nothing else outside that subtree.
    mem_on = next(
        c for c in cells if c.axis == "memory" and c.config.agent.components.memory.enabled
    )
    d = dump_config(mem_on.config)
    assert d["agent"]["components"]["memory"]["enabled"] is True
    # Everything outside the memory toggle is identical to the baseline cell.
    base_d["agent"]["components"]["memory"] = d["agent"]["components"]["memory"]
    assert d == base_d


def test_retrieval_bm25_cell_carries_corpus():
    cells = expand_ablation(load_config(PHASE1))
    bm25 = next(
        c for c in cells if c.axis == "retrieval" and c.config.agent.components.retrieval.enabled
    )
    r = bm25.config.agent.components.retrieval
    assert r.backend == "bm25" and r.corpus and r.corpus.endswith(".jsonl")


def test_expand_requires_sweep_block():
    from atp.config import BASE_CONFIG

    with pytest.raises(ValueError, match="no `sweep` block"):
        expand_ablation(load_config(BASE_CONFIG))


def test_invalid_override_raises_with_cell_name(tmp_path):
    cfg_dict = dump_config(load_config(CONFIGS_DIR / "base.yaml"))
    cfg_dict["sweep"] = {
        "baseline": {},
        "axes": {"bad": [{"agent": {"mode": "not_a_mode"}}]},  # invalid enum
    }
    cfg = ExperimentConfig.model_validate(cfg_dict)
    with pytest.raises(ValueError, match=r"ablation cell 'bad__0' is invalid"):
        expand_ablation(cfg)


def test_validate_cells_flags_retrieval_without_corpus():
    cfg_dict = dump_config(load_config(CONFIGS_DIR / "base.yaml"))
    cfg_dict["sweep"] = {
        "baseline": {},
        "axes": {"retrieval": [{"agent": {"components": {"retrieval": {"enabled": True}}}}]},
    }
    cells = expand_ablation(ExperimentConfig.model_validate(cfg_dict))  # schema-valid
    with pytest.raises(ValueError, match=r"retrieval__0' components invalid"):
        validate_cells(cells)  # but semantically broken: bm25 needs a corpus


def test_manifest_maps_names_to_axis_and_hash():
    cells = expand_ablation(load_config(PHASE1))
    man = ablation_manifest(cells)
    assert {m["name"] for m in man} == set(_names(cells))
    assert all({"name", "axis", "override", "config_hash"} == set(m) for m in man)


def test_cli_ablation_list(capsys):
    rc = main(["ablation", "--config", str(PHASE1), "--list"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "baseline" in out and "tactic_skeletons__" in out


def test_cli_ablation_cell_id_out_of_range():
    rc = main(["ablation", "--config", str(PHASE1), "--cell-id", "999"])
    assert rc == 2


@needs_premise_corpus
def test_phase1_cells_pass_check():
    # The shipped config must be fully runnable: every expanded cell validates (schema+components).
    validate_cells(expand_ablation(load_config(PHASE1)))


def test_smoke_config_is_tiny_and_same_shape_as_phase1():
    smoke = load_config(PHASE1_SMOKE)
    # Tiny by construction (won't accidentally launch a full run).
    assert smoke.data.limit == 3 and smoke.eval.seeds == [0]
    # Same runnable cell set as the real ablation, so the smoke exercises every component cell.
    smoke_axes = {c.axis for c in expand_ablation(smoke)}
    real_axes = {c.axis for c in expand_ablation(load_config(PHASE1))}
    assert smoke_axes == real_axes


def test_validate_cells_flags_unimplemented_bfs_mode():
    cfg_dict = dump_config(load_config(CONFIGS_DIR / "base.yaml"))
    cfg_dict["sweep"] = {"baseline": {}, "axes": {"gen": [{"agent": {"mode": "bfs"}}]}}
    cells = expand_ablation(ExperimentConfig.model_validate(cfg_dict))  # schema-valid
    with pytest.raises(ValueError, match="not implemented yet"):
        validate_cells(cells)


def test_whole_proof_agent_rejects_bfs_mode():
    from atp.config import BASE_CONFIG

    d = dump_config(load_config(BASE_CONFIG))
    d["agent"]["mode"] = "bfs"
    cfg = ExperimentConfig.model_validate(d)
    with pytest.raises(NotImplementedError, match="whole_proof"):
        WholeProofAgent.from_config(cfg, client=None, verifier=None)
