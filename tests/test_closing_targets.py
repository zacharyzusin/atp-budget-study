"""Tests for the Phase 6 closing-target truncation core (top-level + nested + trivial filtering)."""

from __future__ import annotations

from atp.data.closing_targets import (
    closing_truncations,
    split_head_body,
    top_level_groups,
)

PROOF = """theorem lw (a b : ℝ) (h : a = b) : b = a := by
  have h1 : a - b = 0 := by
    rw [h]
    ring
  linarith [h1]"""

# the dominant prover structure: a monolithic `have h_main := by <work>` then `exact h_main`
MONOLITHIC = """theorem t (x : ℕ) : x = 5 := by
  have h_main : x = 5 := by
    norm_num
    omega
  exact h_main"""

# real Goedel pilot shape: `<;>` combinator lines continue the preceding tactic (lean_workbook_101)
COMBINATOR = """theorem t (x : ℕ) (hx : x = 2^9 + 1) : x = 513 := by
  have h_main : x = 513 := by
    rw [hx]
    <;> norm_num
    <;> rfl
  exact h_main"""

# real DeepSeek lean_workbook_101 shape: a COMMENT sits between the tactic and its `<;>` combinator.
# The comment must not start a group (else the cut splits `rw [hx] <;> norm_num` mid-combinator,
# yielding a closing that begins with a dangling `<;>` — unrunnable).
COMBINATOR_COMMENT = """theorem t (x : ℕ) (hx : x = 2^9 + 1) : x = 513 := by
  have h_main : x = 513 := by
    rw [hx]
    -- Calculate 2^9 and simplify
    <;> norm_num
    <;> rfl
  exact h_main"""


def test_split_head_body_tactic_mode():
    sb = split_head_body(PROOF)
    assert sb is not None
    head, body = sb
    assert head.endswith(":= by")
    assert body[0].startswith("  have h1")
    assert body[-1].strip() == "linarith [h1]"


def test_split_head_body_term_mode_returns_none():
    assert split_head_body("theorem t : True := trivial") is None


def test_top_level_groups_keeps_have_block_intact():
    _, body = split_head_body(PROOF)
    groups = top_level_groups(body)
    assert len(groups) == 2
    assert groups[0][0].strip().startswith("have h1")
    assert len(groups[0]) == 3  # have + rw + ring
    assert groups[1][0].strip() == "linarith [h1]"


def test_closing_truncations_top_level_and_nested():
    cands = closing_truncations(PROOF)
    closings = {c.closing.strip() for c in cands}
    # top-level cut keeps the non-trivial `linarith [h1]`; nested cut into the have yields `ring`
    assert "linarith [h1]" in closings
    nested = [c for c in cands if c.depth == 1]
    assert any(c.closing.strip() == "ring" for c in nested)
    # every prefix is a self-contained source with exactly one sorry (nested keeps outer context
    # AFTER the sorry, so it need not be the final token)
    assert all(c.prefix_with_sorry.count("sorry") == 1 for c in cands)


def test_monolithic_have_filters_trivial_and_descends():
    cands = closing_truncations(MONOLITHIC)
    # the top-level closing would be the useless `exact h_main` — it must be FILTERED OUT
    assert all(c.closing.strip() != "exact h_main" for c in cands)
    # the real work is captured by descending into the `have h_main := by` block
    nested = [c for c in cands if c.depth == 1]
    assert nested, "expected a nested closing-target from inside the have-block"
    c = next(c for c in nested if c.closing.strip() == "omega")
    # the sorry sits INSIDE the have, with the outer `exact h_main` preserved (=> exactly one sorry)
    assert "have h_main" in c.prefix_with_sorry
    assert "exact h_main" in c.prefix_with_sorry  # outer context kept
    assert c.prefix_with_sorry.count("sorry") == 1


def test_combinator_lines_attach_to_preceding_tactic():
    # `<;>` lines must NOT start their own group, else a cut yields a closing that begins with a
    # dangling `<;>` (invalid Lean) and a prefix whose tactic is left mid-combinator.
    _, body = split_head_body(COMBINATOR)
    inner = body[1:4]  # the have-block's body: rw / <;> norm_num / <;> rfl  (still indented)
    groups = top_level_groups(inner)
    assert len(groups) == 1, "the rw + its two <;> combinators are a single tactic"
    # and no emitted closing may start with a combinator
    for c in closing_truncations(COMBINATOR):
        assert not c.closing.lstrip().startswith("<;>"), c.closing


def test_comment_between_tactic_and_combinator_is_not_split():
    # the have-body is a SINGLE combinator tactic (rw [hx] <;> norm_num <;> rfl) with a comment in
    # the middle — there is no valid interior boundary, so no nested candidate may be emitted, and
    # certainly none whose closing starts with `<;>`.
    cands = closing_truncations(COMBINATOR_COMMENT)
    for c in cands:
        real = [ln.strip() for ln in c.closing.splitlines()
                if ln.strip() and not ln.strip().startswith("--")]
        assert not (real and real[0].startswith("<;>")), c.closing
    # the have-block collapses to one tactic group => no nested cut
    assert not [c for c in cands if c.depth == 1]


def test_continuation_prefix_plus_target_reconstructs_proof():
    # INVARIANT (Stage B): for every candidate, the body splits cleanly — cont_prefix + cont_target
    # rebuild the original proof body, so the continuation target verifies by construction.
    for proof in (PROOF, MONOLITHIC, COMBINATOR):
        head, body_lines = split_head_body(proof)
        body = "\n".join(body_lines)
        for c in closing_truncations(proof):
            assert c.cont_prefix and c.cont_target
            assert c.cont_prefix + "\n" + c.cont_target == body, (proof, c)


def test_continuation_target_carries_outer_context_for_nested():
    # a nested cut's continuation must include the OUTER tail (`exact h_main`), not just inner work
    nested = [c for c in closing_truncations(MONOLITHIC) if c.depth == 1]
    c = next(c for c in nested if "omega" in c.cont_target)
    assert "exact h_main" in c.cont_target       # outer tail is part of what the model must produce
    assert "exact h_main" not in c.cont_prefix   # but not in the proof-so-far


def test_no_candidates_for_single_trivial_proof():
    assert closing_truncations("theorem t : True := by\n  trivial") == []


def test_trivial_closings_are_dropped():
    # last tactic is a lone `exact`/`simpa` → trivial → dropped; the substantive nested one survives
    cands = closing_truncations(MONOLITHIC)
    assert all(c.closing.strip() not in ("exact h_main", "simpa", "assumption") for c in cands)
