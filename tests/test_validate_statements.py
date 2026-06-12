"""Tests for the statement compile-gate tally logic (scripts/validate_statements.py).

Lean-free: the Lean backend is injected as a ScriptedBackend, so we exercise `_run`'s
success/failure bookkeeping and the first-error extraction without any Lean install. The script's
`main()` (config load + real ReplBackend + report write) is the thin wrapper, exercised on-cluster.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from atp.data.problems import Problem
from atp.lean.backends import RawVerification, ScriptedBackend

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "validate_statements.py"
_spec = importlib.util.spec_from_file_location("validate_statements", _SCRIPT)
validate_statements = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validate_statements)


def _prob(name: str) -> Problem:
    return Problem(name=name, statement=f"theorem {name} : True", benchmark="proofnet_sharp",
                   split="test")


def test_run_tallies_elaboration_and_extracts_first_error():
    problems = [_prob("good"), _prob("bad"), _prob("ok2")]

    def responder(theorem, proof):
        # the gate always appends ":= by sorry" to the statement
        assert proof == f"{theorem.statement} := by sorry"
        if theorem.name == "bad":
            return RawVerification(
                success=False,
                output="bad.lean:2:1: warning: unused\n"
                       "bad.lean:2:5: error: unknown identifier 'Foo'",
            )
        return RawVerification(success=True, output="good.lean:1:1: warning: uses 'sorry'")

    records = validate_statements._run(problems, ScriptedBackend(responder))
    assert [r["name"] for r in records] == ["good", "bad", "ok2"]
    assert [r["ok"] for r in records] == [True, False, True]
    # only the failing record carries an error = the first *error*-severity line (not the warning)
    assert records[0]["error"] == ""
    assert records[1]["error"] == "bad.lean:2:5: error: unknown identifier 'Foo'"
    assert records[2]["error"] == ""


def test_first_error_falls_back_to_first_line_when_no_error_marker():
    # defensive: a malformed/empty output still yields a short, non-crashing summary string
    assert validate_statements._first_error("") == ""
    assert validate_statements._first_error("some opaque failure\nsecond") == "some opaque failure"
