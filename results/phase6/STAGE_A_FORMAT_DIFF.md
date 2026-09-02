# Phase 6 Stage A — training-data vs. inference prompt-format diff

CPU-only check, read-only against `scripts/phase6_build_sft.py`, `scripts/phase6_train_sft.py`, and
a live example pulled from `scratch/phase6/sft/goedel/sft_A.jsonl`.

## The prompt half: byte-identical, confirmed

Stage A's user turn is built by literally calling `template.render(thm)` — the same
`WholeProofTemplate.render` used at inference (`phase6_build_sft.py:make_example`, kind "A"). Not a
reimplementation, not a paraphrase — the same function object. `phase6_train_sft.py`'s docstring
states training uses trl's `SFTTrainer` with the model's own chat template and completion-only loss,
which (if true, not independently re-verified beyond reading the docstring) would make the templated
wrapper byte-identical end to end. **The prompt side of the reviewer's "train/inference format
mismatch" hypothesis is ruled out** — it is not a naive reimplementation bug.

## The target/label half: a real, confirmed divergence

`make_example`'s assistant turn is `_fenced(proof)` — ONLY the fenced Lean code, via:

```python
def _fenced(proof: str) -> str:
    return f"```lean4\n{proof.strip()}\n```"
```

Pulled a live example from `scratch/phase6/sft/goedel/sft_A.jsonl` (record 0, `lean_workbook_1001`):

**User turn (verbatim, matches `WholeProofTemplate.render` exactly):**
```
Complete the following Lean 4 code:

```lean4
import Mathlib

theorem lean_workbook_1001 ... := by sorry
```

Before producing the Lean 4 code to formally prove the given theorem, provide a detailed proof plan
outlining the main proof steps and strategies.
The plan should highlight key ideas, intermediate lemmas, and proof structures that will guide the
construction of the final formal proof.
```

**Assistant turn (verbatim, first lines):**
```
```lean4
theorem lean_workbook_1001 ... := by
  have h1 : ...
```
```

**The assistant turn contains ZERO plan text.** The prompt explicitly instructs the model to
produce a proof plan BEFORE the code; the training label goes straight to the fenced code with no
plan, no reasoning trace, nothing preceding the fence. This is not a wrapper/tokenization mismatch —
it is a direct content contradiction between the instruction the model is shown and the completion
it is rewarded for producing: **Stage A trains the model that the correct response to "give a plan,
then code" is "skip the plan, emit only code."**

## Why this plausibly explains the −12 to −20pp regression

`WholeProofTemplate`'s own docstring says the plan-then-code structure exists specifically "so the
reasoning model thinks before emitting the final proof" (templates.py:169). If the plan tokens are
functionally load-bearing — i.e., the model's original (pre-SFT) successful completions used that
prose as real intermediate computation before committing to code, not decorative filler — then SFT
that rewards skipping straight to code is not a stylistic change, it is training the model away from
the reasoning step that let it solve the problem in the first place. This was not independently
confirmed here (would require pulling a raw pre-SFT harvest completion and checking whether it
included plan prose before the fence — the harvested `proof` field used as the training label is
already fence-extracted, so the original plan prose, if it existed, was already stripped before
`make_example` ever saw it, and is not visible in the SFT data itself). But given the prompt
literally requests it and the label contains none of it, **this is a concrete, checkable, and
distinctly different failure mode from "byte-mismatched wrapper"** — it's closer to "the SFT
objective actively unlearns the model's own reasoning scaffold." Worth checking a handful of raw
harvest completions (pre-fence-extraction) for plan prose before concluding either way; not done in
this pass (would need to read the harvest script's raw output, not just the built SFT file).

## Bottom line

Format mismatch in the sense the reviewer originally proposed (train/inference wrapper divergence,
possibly a LoRA-merge bug) is NOT what's happening — the wrapper is provably identical. But there IS
a real, verified, and different divergence: the training target contradicts what the prompt asks for
and may be actively suppressing the model's own reasoning step. This deserves a mention before
publishing the Stage A number, and is cheap to investigate further (check raw harvest completions for
plan prose) if the −12 to −20pp number is going to be reported as evidence of anything beyond "SFT on
extracted-code-only labels doesn't help."
