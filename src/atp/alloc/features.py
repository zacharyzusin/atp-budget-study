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
    # label / bookkeeping (never a feature)
    eventual_solve: bool
    tokens_to_solve: int | None

    FEATURE_NAMES = (
        "tokens_so_far", "n_attempts", "best_depth", "last_depth",
        "depth_growth", "stalled_attempts", "distinct_openings", "compiled_past_step1",
    )

    def features(self) -> dict[str, float]:
        return {k: float(getattr(self, k)) for k in self.FEATURE_NAMES}


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
        openings: set[str] = set()
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
            d = attempt_depth(bool(a.get("ok")), str(a.get("feedback") or ""))
            depths.append(d)
            op = opening_tactic(str(a.get("proof") or ""))
            if op:
                openings.add(op)
            if a.get("ok"):
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
        return CheckpointRow(
            problem_name=self.problem_name, seed=self.seed, checkpoint=c,
            tokens_so_far=toks, n_attempts=n, best_depth=best_depth, last_depth=last_depth,
            depth_growth=depth_growth, stalled_attempts=stalled,
            distinct_openings=len(openings),
            compiled_past_step1=int(best_depth >= 2),
            solved_by_c=solved_by_c,
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
