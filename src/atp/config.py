"""Config loader + schema for atp experiments.

`configs/base.yaml` is the canonical schema; every other config sets `defaults: base` and
overrides a subset of fields. This module:

  * deep-merges a config on top of its `defaults` base,
  * validates the merged result against typed pydantic models (typos / wrong types are
    rejected via `extra="forbid"`),
  * round-trips losslessly (load -> dump -> load is stable),
  * exposes `config_hash` (for run_manifest.json) and `apply_env` (sets HF_HOME into scratch).

Kept dependency-light on purpose (pydantic + pyyaml only) so it imports on a login node.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

# Repo root = three parents up from this file: src/atp/config.py -> repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = REPO_ROOT / "configs"
BASE_CONFIG = CONFIGS_DIR / "base.yaml"


# --------------------------------------------------------------------------------------
# Typed schema (mirrors configs/base.yaml). extra="forbid" turns config typos into errors.
# --------------------------------------------------------------------------------------
class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectCfg(_Strict):
    root: str
    results_dir: str = "results"
    hf_cache: str = "scratch/hf-cache"


class LeanCfg(_Strict):
    toolchain: str
    mathlib_commit: str
    mathlib_repo: str = "https://github.com/leanprover-community/mathlib4.git"
    cache_dir: str = "scratch/lean-cache"
    verify_timeout_s: int = 120
    reject_loopholes: list[str] = Field(default_factory=lambda: ["sorry", "admit", "native_decide"])


class ModelCfg(_Strict):
    name: str
    hf_repo: str
    revision: str
    endpoint_file: str = "results/_vllm_endpoint.txt"
    max_model_len: int = 16384
    temperature: float = 1.0
    top_p: float = 0.95
    prompt_template: Literal["whole_proof", "tactic"] = "whole_proof"
    # Goedel-Prover-V2-8B is a Qwen3-based *reasoning* prover trained with a chat template; it must
    # be driven via /v1/chat/completions (server applies the template) — raw /v1/completions makes
    # it ramble in prose instead of emitting a ```lean4 block. See DECISIONS.md 2026-06-06.
    chat_completions: bool = True
    # HTTP read timeout per vLLM request. One request generates up to max_model_len//2 tokens
    # (~20k @ len 40960); under n_workers concurrency per-stream throughput drops to ~6-15 tok/s, so
    # a single request can run 30-45 min. The old 600s default timed out and (pre-fix) killed the
    # whole sweep — baseline 10272937 died at 165 cells. Size this WELL above the worst case.
    request_timeout_s: int = 3600
    request_max_retries: int = 4  # SDK-level retries for transient connection/5xx blips


class BudgetCfg(_Strict):
    unit: Literal["tokens"] = "tokens"
    values: list[int]
    stop_on_first_success: bool = True


class RefinementCfg(_Strict):
    enabled: bool = True
    max_iters: int = 4
    alloc_split: float = Field(0.5, ge=0.0, le=1.0)


class MemoryCfg(_Strict):
    enabled: bool = False
    # How many of the most-recent failed attempts to carry into a fresh proposal as "don't repeat".
    max_items: int = Field(3, ge=1)


class ReviewerCfg(_Strict):
    enabled: bool = False
    # Token budget for one critic call. Small: the critic emits a short verdict + critique, and it
    # is charged against the same per-problem budget, so an oversized critic would starve proving.
    max_tokens: int = Field(256, ge=1)


class RetrievalCfg(_Strict):
    enabled: bool = False
    backend: Literal["none", "bm25", "reprover"] = "bm25"
    k: int = Field(8, ge=1)
    # Path to a premises JSONL ({"name","decl"} per line) to retrieve over. Required for bm25; the
    # corpus is a separate data-prep artifact (a Mathlib declaration dump), not produced at runtime.
    corpus: str | None = None


class SkeletonsCfg(_Strict):
    enabled: bool = False
    schedule: str = "default"


class DiversityCfg(_Strict):
    # Phase 2 Step C: approach-conditioned diversity injection. On each *fresh* proposal, list the
    # opening tactics already tried on this problem and instruct a fundamentally different approach —
    # targeting the approach-level collapse located in MECHANISM.md F1. The decisive interventional
    # test of causal-vs-symptomatic (F5 predicts a null: diversity rises, solves stay flat).
    enabled: bool = False
    # How many distinct prior opening tactics to list back to the model (cap to keep the prompt tight).
    max_listed: int = Field(6, ge=1)


class ComponentsCfg(_Strict):
    memory: MemoryCfg = Field(default_factory=MemoryCfg)
    reviewer: ReviewerCfg = Field(default_factory=ReviewerCfg)
    retrieval: RetrievalCfg = Field(default_factory=RetrievalCfg)
    tactic_skeletons: SkeletonsCfg = Field(default_factory=SkeletonsCfg)
    diversity: DiversityCfg = Field(default_factory=DiversityCfg)


class AgentCfg(_Strict):
    mode: Literal["whole_proof", "bfs"] = "whole_proof"
    refinement: RefinementCfg = Field(default_factory=RefinementCfg)
    components: ComponentsCfg = Field(default_factory=ComponentsCfg)


class SearchCfg(_Strict):
    beam: int = 8
    length_norm: bool = True
    max_depth: int = 50


class DataCfg(_Strict):
    benchmark: Literal["minif2f", "proofnet_sharp", "lean_workbook"] = "minif2f"
    split: Literal["train", "valid", "test", "novel"] = "test"
    exclude_unprovable: bool = True
    use_novel_split: bool = False
    novel_names_file: str | None = None  # newline- or JSON-list file of held-out problem names,
    #                       resolved relative to project.root. Required when use_novel_split=True.
    limit: int | None = None  # smoke configs cap the problem count
    # Data source dirs (None → loader defaults: miniF2F to the sibling copy; ProofNet# unset).
    minif2f_dir: str | None = None
    proofnet_dir: str | None = None
    # Phase 6 training corpus (decontaminated Lean Workbook); None → §0 clean-corpus default path.
    lean_workbook_path: str | None = None
    exclusions_file: str | None = None  # override the built-in miniF2F exclusion list


class EvalCfg(_Strict):
    seeds: list[int]
    metrics: list[str] = Field(
        default_factory=lambda: ["pass_at_b", "tokens_to_first_proof", "effective_accuracy"]
    )
    reviewer_false_accept: bool = True
    n_workers: int = 1  # concurrent (problem,seed) cells; >1 lets vLLM batch (each worker its own
    #                     Lean REPL). 1 = sequential (default; safe for tests/smoke).


class LoggingCfg(_Strict):
    log_dir: str = "logs"
    per_problem_json: bool = True
    write_manifest: bool = True


class ExperimentConfig(_Strict):
    """Fully-merged, validated experiment config."""

    project: ProjectCfg
    lean: LeanCfg
    model: ModelCfg
    budget: BudgetCfg
    agent: AgentCfg = Field(default_factory=AgentCfg)
    search: SearchCfg = Field(default_factory=SearchCfg)
    data: DataCfg = Field(default_factory=DataCfg)
    eval: EvalCfg
    logging: LoggingCfg = Field(default_factory=LoggingCfg)
    # Phase 1 sweep configs carry an extra `sweep` block; keep it as opaque data so the
    # base schema validates without enumerating every axis shape.
    sweep: dict[str, Any] | None = None


# --------------------------------------------------------------------------------------
# Loading / merging
# --------------------------------------------------------------------------------------
def _read_yaml(path: str | os.PathLike[str]) -> dict[str, Any]:
    with open(path) as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config {path} did not parse to a mapping")
    return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge `override` onto a copy of `base` (override wins on leaves)."""
    out = dict(base)
    for key, val in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def _resolve_defaults(
    raw: dict[str, Any], configs_dir: Path, _seen: tuple[str, ...] = ()
) -> dict[str, Any]:
    """Pop `defaults: <name>` and deep-merge raw onto that base config.

    Chains recursively: `defaults: proofnet_baseline` (which itself sets `defaults: base`) merges
    the whole chain, so a smoke/variant config can extend a full experiment config. Cycles raise.
    """
    defaults = raw.pop("defaults", None)
    if defaults is None:
        return raw
    name = "base" if defaults in (None, "base") else defaults
    if name in _seen:
        raise ValueError(f"cyclic config defaults: {' -> '.join((*_seen, name))}")
    base_raw = _read_yaml(configs_dir / f"{name}.yaml")
    base_raw = _resolve_defaults(base_raw, configs_dir, (*_seen, name))  # resolve base's own chain
    return _deep_merge(base_raw, raw)


def load_config(path: str | os.PathLike[str]) -> ExperimentConfig:
    """Load a YAML config, merge it onto its `defaults` base, and validate it."""
    path = Path(path)
    configs_dir = path.parent if path.parent.name == "configs" else CONFIGS_DIR
    raw = _read_yaml(path)
    merged = _resolve_defaults(raw, configs_dir)
    return ExperimentConfig.model_validate(merged)


def dump_config(config: ExperimentConfig) -> dict[str, Any]:
    """Plain-dict view of a config (round-trip safe with `ExperimentConfig.model_validate`)."""
    return config.model_dump(mode="json")


def config_hash(config: ExperimentConfig) -> str:
    """Stable short hash of the fully-resolved config, for run_manifest.json."""
    blob = json.dumps(dump_config(config), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def apply_env(config: ExperimentConfig) -> dict[str, str]:
    """Set process env from the config (HF_HOME -> scratch cache) and return what changed.

    Paths in the config are relative to the project root; resolve them so jobs launched
    from anywhere point HF at the shared scratch cache (storage-hygiene rule).
    """
    root = Path(config.project.root)
    hf_home = str((root / config.project.hf_cache).resolve())
    os.environ["HF_HOME"] = hf_home
    return {"HF_HOME": hf_home}
