"""Task 0.1 smoke tests: package imports work and configs round-trip + validate.

Fast suite only (no slow/gpu/lean markers): must run on a login node in well under a second.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from pydantic import ValidationError

import atp
from atp.config import (
    BASE_CONFIG,
    CONFIGS_DIR,
    ExperimentConfig,
    apply_env,
    config_hash,
    dump_config,
    load_config,
)

# Every src/atp subpackage should import cleanly with no heavy (torch/vllm/lean) deps.
ATP_SUBMODULES = [
    "atp",
    "atp.cli",
    "atp.config",
    "atp.lean",
    "atp.models",
    "atp.agents",
    "atp.agents.components",
    "atp.budget",
    "atp.data",
    "atp.eval",
]

CONFIG_FILES = sorted(CONFIGS_DIR.glob("*.yaml"))


def test_version_exposed():
    assert isinstance(atp.__version__, str) and atp.__version__


@pytest.mark.parametrize("modname", ATP_SUBMODULES)
def test_submodule_imports(modname):
    importlib.import_module(modname)


def test_config_files_present():
    # base + the three experiment configs the plan references.
    names = {p.name for p in CONFIG_FILES}
    assert {"base.yaml", "phase0_baseline.yaml", "phase1_ablation.yaml", "smoke.yaml"} <= names


def test_base_config_loads_and_validates():
    cfg = load_config(BASE_CONFIG)
    assert isinstance(cfg, ExperimentConfig)
    assert cfg.budget.unit == "tokens"
    assert len(cfg.eval.seeds) >= 3  # variance rule: >=3 seeds for headline numbers


@pytest.mark.parametrize("path", CONFIG_FILES, ids=lambda p: p.name)
def test_every_config_validates(path):
    cfg = load_config(path)
    assert isinstance(cfg, ExperimentConfig)


@pytest.mark.parametrize("path", CONFIG_FILES, ids=lambda p: p.name)
def test_config_round_trips(path):
    """load -> dump -> re-validate -> dump must be byte-identical (lossless round-trip)."""
    cfg = load_config(path)
    dumped = dump_config(cfg)
    reloaded = ExperimentConfig.model_validate(dumped)
    assert dump_config(reloaded) == dumped
    assert config_hash(reloaded) == config_hash(cfg)


def test_defaults_merge_overrides_base():
    base = load_config(BASE_CONFIG)
    smoke = load_config(CONFIGS_DIR / "smoke.yaml")
    # smoke.yaml overrides split -> valid and caps problem count; base stays test/unlimited.
    assert base.data.split == "test"
    assert smoke.data.split == "valid"
    assert smoke.data.limit == 5
    # untouched fields are inherited from base.
    assert smoke.project.root == base.project.root


def test_defaults_chain_transitively(tmp_path):
    """`defaults` resolves recursively: a config extending an experiment config (which itself
    extends base) inherits the whole chain — so smoke configs can extend an experiment config."""
    import shutil

    cfgdir = tmp_path / "configs"
    cfgdir.mkdir()
    shutil.copy(BASE_CONFIG, cfgdir / "base.yaml")
    # mid layer overrides a base field; top layer overrides a different one.
    (cfgdir / "mid.yaml").write_text("defaults: base\ndata:\n  benchmark: proofnet_sharp\n")
    (cfgdir / "top.yaml").write_text("defaults: mid\neval:\n  seeds: [0]\n")
    cfg = load_config(cfgdir / "top.yaml")
    assert cfg.data.benchmark == "proofnet_sharp"  # inherited from mid
    assert cfg.eval.seeds == [0]                    # set by top
    assert cfg.model.name == load_config(BASE_CONFIG).model.name  # inherited transitively from base


def test_defaults_cycle_raises(tmp_path):
    cfgdir = tmp_path / "configs"
    cfgdir.mkdir()
    (cfgdir / "a.yaml").write_text("defaults: b\n")
    (cfgdir / "b.yaml").write_text("defaults: a\n")
    with pytest.raises(ValueError, match="cyclic"):
        load_config(cfgdir / "a.yaml")


def test_unknown_key_is_rejected(tmp_path):
    """A typo'd config key must fail validation (extra='forbid')."""
    bad = tmp_path / "bad.yaml"
    bad.write_text("defaults: base\nbudget:\n  values: [1000]\n  not_a_real_key: 1\n")
    # point the loader at the real configs dir for the `defaults: base` lookup.
    import shutil

    cfgdir = tmp_path / "configs"
    cfgdir.mkdir()
    shutil.copy(BASE_CONFIG, cfgdir / "base.yaml")
    (cfgdir / "bad.yaml").write_text(bad.read_text())
    with pytest.raises(ValidationError):
        load_config(cfgdir / "bad.yaml")


def test_apply_env_sets_hf_home(monkeypatch):
    monkeypatch.delenv("HF_HOME", raising=False)
    cfg = load_config(BASE_CONFIG)
    changed = apply_env(cfg)
    assert changed["HF_HOME"].endswith("scratch/hf-cache")
    assert Path(changed["HF_HOME"]).is_absolute()
