"""Per-cell *checkpoint* features for the realizable allocation policies (Task 4.1 / 4.3).

For each (problem, seed) cell we replay its logged attempts and snapshot, at each spend checkpoint
`c ∈ {2k,4k,8k,16k,32k}`, only what a policy could observe by then. The decision rule a realizable
policy uses lives downstream (`realizable.py`); this module just produces leakage-free feature rows.

Design choices (per the 2026-06-20 guidance):
- **Depth is real, not a proxy.** The whole-proof verifier already logs `Failed at step N` (97.8% of
  ProofNet# failures), so `attempt_depth` is the genuine "deepest step reached," free of any
  error-locus parsing. Solved/infra attempts are handled explicitly.
- **The workhorse is progress, not absolute depth.** `best_depth` (max so far) and especially
  `depth_growth` / `stalled_attempts` (is the best-so-far still climbing, or plateaued?) are the
  stuck-detector signals expected to discriminate trapped from winnable within the hard set.
- **F1 diversity is included but not leaned on** (`distinct_openings`): the ~1.8-approach collapse
  is a property of hard problems generally, so it is weakly discriminative within the hard set.

Causality (asserted in `test_alloc`): a checkpoint-`c` row uses only attempts whose cumulative token
END is `≤ c`, and never references `tokens_to_solve` or any post-`c` attempt.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

CHECKPOINTS: tuple[int, ...] = (2000, 4000, 8000, 16000, 32000)
_STEP_RE = re.compile(r"Failed at step (\d+)")
# the whole-proof template opens the tactic block with `:= by`; the opening tactic is the first
# token of the first non-empty line after it. Cheap heuristic — only used for F1 diversity.
_BY_RE = re.compile(r":=\s*by\b", re.IGNORECASE)


def attempt_depth(ok: bool, feedback: str) -> int:
    """Deepest proof step the verifier reached on this attempt.

    Solved → a large sentinel (it reached the end). Failed → the `N` in `Failed at step N`. Infra
    errors / unparseable → 0 (no informative progress). This is the genuine F3 depth, not a proxy.
    """
    if ok:
        return 10_000  # sentinel: reached the end (relevant only if solved by checkpoint c)
    m = _STEP_RE.search(feedback or "")
    return int(m.group(1)) if m else 0


def opening_tactic(proof: str) -> str:
    """First tactic after `:= by` — a cheap fingerprint of the proof's *approach* (F1 diversity)."""
    if not proof:
        return ""
    m = _BY_RE.search(proof)
    tail = proof[m.end():] if m else proof
    for line in tail.splitlines():
        s = line.strip()
        if s and not s.startswith("--"):
            return s.split()[0] if s.split() else ""
    return ""


# ---------------------------------------------------------------- WS6 item 4: richer features
# Pre-registered in results/phase4/PREDICTOR_V2_DESIGN.md (2026-07-26), all derivable from already-
# logged attempt data (no GPU re-run). Additive: FEATURE_NAMES_V2 is a strict superset of the original
# 8, so v1 behavior/tests are byte-for-byte unchanged.

_ERROR_KINDS = ("syntax", "elaboration", "infra", "step", "other")


def error_kind(ok: bool, feedback: str) -> str:
    """Coarse classification of a failed attempt's feedback (richer than raw depth alone)."""
    if ok:
        return "solved"
    fb = feedback or ""
    if "REPL_INFRA_ERROR" in fb or "infra" in fb.lower():
        return "infra"
    if _STEP_RE.search(fb):
        return "step"
    if "unsolved goals" in fb or "unknown identifier" in fb.lower():
        return "elaboration"
    if "error:" in fb.lower() or "unexpected token" in fb.lower():
        return "syntax"
    return "other"


_BACKTICK_RE = re.compile(r"`[^`]*`")


def normalized_error(feedback: str) -> str:
    """Strip goal-state/identifier specifics so repeated hits on the SAME wall dedupe; used only for
    the error_diversity count, never as a feature value itself (too high-cardinality to encode raw)."""
    fb = (feedback or "").strip()
    fb = _STEP_RE.sub("Failed at step N", fb)
    fb = _BACKTICK_RE.sub("`_`", fb)  # the specific failing tactic/identifier varies per attempt
    return fb.splitlines()[0][:120] if fb else ""


@dataclass
class CheckpointRow:
    """Leakage-free features for a cell observed by spend `checkpoint`, plus its eventual label."""
    problem_name: str
    seed: int
    checkpoint: int
    # observed-by-c features
    tokens_so_far: int
    n_attempts: int
    best_depth: int          # max step reached over attempts completed by c (F3, real)
    last_depth: int          # depth of the most recent attempt by c
    depth_growth: int        # best_depth(recent half) - best_depth(early half): still climbing?
    stalled_attempts: int    # attempts since best_depth last improved (plateau / stuck detector)
    distinct_openings: int   # F1 diversity (included, not leaned on)
    compiled_past_step1: int # 1 if any attempt by c reached depth >= 2
    solved_by_c: bool        # already solved within c (not a decision target)
    # WS6 item 4 (2026-07-26): richer features, additive, all default 0.0 so existing v1 call sites
    # (tests, older callers) that never set them still construct a valid row.
    frac_syntax_error: float = 0.0       # fraction of attempts classified error_kind=="syntax"
    frac_elaboration_error: float = 0.0  # fraction classified "elaboration"
    frac_infra_error: float = 0.0        # fraction classified "infra"
    depth_slope: float = 0.0             # linear-fit slope of best-depth-so-far vs. cumulative tokens
    depth_slope_resid: float = 0.0       # residual std of that fit (0 if <3 points)
    tokens_per_depth: float = 0.0        # tokens_so_far / max(best_depth, 1) -- efficiency
    frac_refine: float = 0.0             # fraction of attempts with kind=="refine"
    error_diversity: int = 0             # count of distinct normalized error messages seen
    # label / bookkeeping (never a feature)
    eventual_solve: bool = False
    tokens_to_solve: int | None = None

    FEATURE_NAMES = (
        "tokens_so_far", "n_attempts", "best_depth", "last_depth",
        "depth_growth", "stalled_attempts", "distinct_openings", "compiled_past_step1",
    )
    FEATURE_NAMES_V2 = FEATURE_NAMES + (
        "frac_syntax_error", "frac_elaboration_error", "frac_infra_error",
        "depth_slope", "depth_slope_resid", "tokens_per_depth", "frac_refine", "error_diversity",
    )

    def features(self, names: tuple[str, ...] | None = None) -> dict[str, float]:
        names = names or self.FEATURE_NAMES
        return {k: float(getattr(self, k)) for k in names}


@dataclass
class CellTrace:
    problem_name: str
    seed: int
    solved: bool
    tokens_to_solve: int | None
    # ordered attempts; each dict has completion_tokens / ok / feedback / proof
    attempts: list[dict] = field(default_factory=list)

    def checkpoint_row(self, c: int) -> CheckpointRow:
        """Snapshot features from only the attempts whose cumulative-token END is ≤ c."""
        cum = 0
        depths: list[int] = []
        cum_at_depth: list[int] = []  # cumulative tokens AFTER each attempt, paired with depths
        openings: set[str] = set()
        error_kinds: list[str] = []
        norm_errors: set[str] = set()
        n_refine = 0
        toks = 0
        n = 0
        solved_by_c = False
        for a in self.attempts:
            ct = int(a.get("completion_tokens") or 0)
            if cum + ct > c:
                break  # this attempt finishes after the checkpoint — not yet observable
            cum += ct
            toks = cum
            n += 1
            ok = bool(a.get("ok"))
            fb = str(a.get("feedback") or "")
            d = attempt_depth(ok, fb)
            depths.append(d)
            cum_at_depth.append(cum)
            op = opening_tactic(str(a.get("proof") or ""))
            if op:
                openings.add(op)
            error_kinds.append(error_kind(ok, fb))
            if not ok:
                norm_errors.add(normalized_error(fb))
            if str(a.get("kind") or "") == "refine":
                n_refine += 1
            if ok:
                solved_by_c = True

        best_depth = max(depths) if depths else 0
        last_depth = depths[-1] if depths else 0
        # depth_growth: best over recent half minus best over early half (≥0 ⇒ still climbing)
        if len(depths) >= 2:
            mid = len(depths) // 2
            early = max(depths[:mid]) if depths[:mid] else 0
            recent = max(depths[mid:]) if depths[mid:] else 0
            depth_growth = recent - early
        else:
            depth_growth = 0
        # stalled_attempts: how many attempts since best_depth was last achieved (plateau detector)
        stalled = 0
        if depths:
            last_best_idx = max(i for i, d in enumerate(depths) if d == best_depth)
            stalled = len(depths) - 1 - last_best_idx

        # -- WS6 item 4 richer features (all from data already collected above) --
        n_fail = max(len(error_kinds), 1)
        frac_syntax = error_kinds.count("syntax") / n_fail
        frac_elab = error_kinds.count("elaboration") / n_fail
        frac_infra = error_kinds.count("infra") / n_fail
        frac_refine = n_refine / n_fail
        tokens_per_depth = toks / max(best_depth, 1)
        # depth_slope: OLS slope of depth vs. cumulative tokens (progress rate, continuous not binary)
        slope, resid = 0.0, 0.0
        if len(depths) >= 3:
            xs = [float(t) for t in cum_at_depth]
            ys = [float(d) for d in depths]
            n_pts = len(xs)
            mean_x, mean_y = sum(xs) / n_pts, sum(ys) / n_pts
            var_x = sum((x - mean_x) ** 2 for x in xs)
            if var_x > 0:
                slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / var_x
                intercept = mean_y - slope * mean_x
                resids = [y - (slope * x + intercept) for x, y in zip(xs, ys)]
                resid = (sum(r ** 2 for r in resids) / n_pts) ** 0.5

        return CheckpointRow(
            problem_name=self.problem_name, seed=self.seed, checkpoint=c,
            tokens_so_far=toks, n_attempts=n, best_depth=best_depth, last_depth=last_depth,
            depth_growth=depth_growth, stalled_attempts=stalled,
            distinct_openings=len(openings),
            compiled_past_step1=int(best_depth >= 2),
            solved_by_c=solved_by_c,
            frac_syntax_error=frac_syntax, frac_elaboration_error=frac_elab,
            frac_infra_error=frac_infra, depth_slope=slope, depth_slope_resid=resid,
            tokens_per_depth=tokens_per_depth, frac_refine=frac_refine,
            error_diversity=len(norm_errors),
            eventual_solve=self.solved, tokens_to_solve=self.tokens_to_solve,
        )


def load_cell_traces(run_dir: str | Path) -> list[CellTrace]:
    """Join each cell's per-cell summary (solved/tokens_to_solve) with its agent_states attempts."""
    run_dir = Path(run_dir)
    states = run_dir / "agent_states"
    out: list[CellTrace] = []
    for pj in sorted((run_dir / "problems").glob("*.json")):
        try:
            summ = json.loads(pj.read_text())
        except json.JSONDecodeError:
            continue
        stem = pj.stem  # e.g. Foo__exercise_1__seed0
        sj = states / f"{stem}.json"
        attempts: list[dict] = []
        if sj.exists():
            try:
                attempts = json.loads(sj.read_text()).get("attempts", []) or []
            except json.JSONDecodeError:
                attempts = []
        out.append(CellTrace(
            problem_name=summ["problem_name"], seed=int(summ["seed"]),
            solved=bool(summ["solved"]),
            tokens_to_solve=summ.get("tokens_to_solve"),
            attempts=attempts,
        ))
    return out


def build_feature_rows(run_dir: str | Path,
                       checkpoints: tuple[int, ...] = CHECKPOINTS) -> list[CheckpointRow]:
    rows: list[CheckpointRow] = []
    for cell in load_cell_traces(run_dir):
        for c in checkpoints:
            rows.append(cell.checkpoint_row(c))
    return rows
