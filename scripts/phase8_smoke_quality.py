#!/usr/bin/env python3
"""Phase 8 — smoke-quality diagnostic: the check that WOULD have caught the Leanabell
whole_proof/chat_completions incident before it reached full-battery scale (see
PROGRESS.md/DECISIONS.md 2026-07-06). The original 2-problem smoke only eyeballed "does this look
like coherent Lean text" — too shallow a bar; it missed a format that produced 0/2025 real solves.

This scans a run's `agent_states/*.json` for the two concrete failure signatures found in that
incident:

1. **Leftover fence marker** — `proof` text that still starts with a ` ```` ` fence marker means
   `extract_lean_block`/the template's own extraction fell back to the raw completion because no
   matched closing fence was found (usually: the completion got truncated before the model closed
   its own fence). Every such attempt is a guaranteed Lean parse error, not a real proof attempt.
2. **Out-of-context tactic error** — a `feedback` string containing "unknown namespace" means Lean
   tried to parse a bare tactic call as a top-level command, i.e. the extracted text isn't being
   assembled into proper `theorem ... := by <tactics>` context for this model's output shape.

Run this on ANY smoke before scaling to a real battery, not just Leanabell's.
"""
import glob
import json
from dataclasses import dataclass


@dataclass
class SmokeQualityReport:
    n_attempts: int
    fence_leftover_count: int
    out_of_context_count: int

    @property
    def fence_leftover_rate(self):
        return self.fence_leftover_count / self.n_attempts if self.n_attempts else 0.0

    @property
    def out_of_context_rate(self):
        return self.out_of_context_count / self.n_attempts if self.n_attempts else 0.0

    @property
    def looks_healthy(self):
        """Not a proof of correctness — just rules out the two concrete failure signatures that
        burned a full battery's GPU-h last time. A low rate here is necessary, not sufficient."""
        return self.fence_leftover_rate < 0.10 and self.out_of_context_rate < 0.10


def check_smoke_quality(run_dir):
    n = 0
    fence_leftover = 0
    out_of_context = 0
    for f in glob.glob(f"{run_dir}/agent_states/*.json"):
        with open(f) as fh:
            d = json.load(fh)
        for att in d.get("attempts", []):
            n += 1
            proof = (att.get("proof") or "").strip()
            if proof.startswith("```"):
                fence_leftover += 1
            feedback = att.get("feedback") or ""
            if "unknown namespace" in feedback:
                out_of_context += 1
    return SmokeQualityReport(
        n_attempts=n, fence_leftover_count=fence_leftover, out_of_context_count=out_of_context
    )


if __name__ == "__main__":
    import sys

    report = check_smoke_quality(sys.argv[1])
    print(
        f"n_attempts={report.n_attempts} "
        f"fence_leftover={report.fence_leftover_count} ({report.fence_leftover_rate:.1%}) "
        f"out_of_context={report.out_of_context_count} ({report.out_of_context_rate:.1%}) "
        f"looks_healthy={report.looks_healthy}"
    )
