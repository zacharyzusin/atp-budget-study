"""Fast tests for the Lean error parser (Task 0.2). No Lean/LeanDojo required."""

from __future__ import annotations

from pathlib import Path

import pytest

from atp.lean.errors import (
    attribute_failure,
    find_loopholes,
    parse_lean_output,
)

FIXTURES = Path(__file__).parent / "fixtures" / "lean"


def _fx(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_parse_unsolved_goals_folds_continuation():
    parsed = parse_lean_output(_fx("unsolved_goals.txt"))
    assert len(parsed.errors) == 1
    err = parsed.earliest_error
    assert err is not None
    assert (err.line, err.col) == (3, 0)
    assert err.severity == "error"
    assert "unsolved goals" in err.text
    # the goal continuation line is folded into the message text
    assert "⊢ n + 0 = n" in err.text


def test_parse_unknown_identifier_keeps_path_and_message():
    parsed = parse_lean_output(_fx("unknown_identifier.txt"))
    (err,) = parsed.errors
    assert err.path == "Mathlib/Test.lean"
    assert err.position == (12, 14)
    assert "Nat.foo_bar" in err.text


def test_earliest_error_is_by_source_position_not_text_order():
    """multiple_errors.txt lists the line-7 error first, but the line-4 error is earliest."""
    parsed = parse_lean_output(_fx("multiple_errors.txt"))
    assert len(parsed.errors) == 2
    earliest = parsed.earliest_error
    assert earliest is not None
    assert earliest.line == 4
    assert "type mismatch" in earliest.text


def test_sorry_warning_is_not_an_error_but_is_flagged():
    parsed = parse_lean_output(_fx("sorry_warning.txt"))
    assert parsed.has_error is False
    assert parsed.earliest_error is None
    assert len(parsed.warnings) == 1
    assert parsed.uses_sorry_warning is True


def test_empty_output_is_clean():
    parsed = parse_lean_output(_fx("success_empty.txt"))
    assert parsed.messages == ()
    assert parsed.has_error is False
    assert parsed.earliest_error is None


@pytest.mark.parametrize(
    "proof, expected",
    [
        ("theorem t : True := by\n  trivial", []),
        ("theorem t : True := by\n  sorry", ["sorry"]),
        ("by\n  native_decide", ["native_decide"]),
        ("by\n  admit", ["admit"]),
        # word-boundary: identifiers containing a token must NOT trip it
        ("by\n  exact admitCard_le", []),
        ("by\n  exact sorryAx_free", []),
    ],
)
def test_find_loopholes_word_boundary(proof, expected):
    assert find_loopholes(proof) == expected


def test_attribute_failure_blames_the_right_tactic():
    body = "intro n\ninduction n with\n| zero => rfl\n| succ k ih => simp [ih]"
    # error reported at line 4 of the body (the succ case)
    parsed = parse_lean_output("p.lean:4:20: error: simp made no progress")
    fs = attribute_failure(body, parsed)
    assert fs is not None
    assert fs.line == 4
    assert fs.step_index == 3
    assert fs.tactic == "| succ k ih => simp [ih]"
    assert "simp made no progress" in fs.message


def test_attribute_failure_none_when_no_error():
    parsed = parse_lean_output("")
    assert attribute_failure("intro n\nrfl", parsed) is None
