"""Fast, CPU-only tests for scripts/analyze_mechanism.py (no GPU/Lean/cluster)."""
import json, os, sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import analyze_mechanism as am


def test_first_tactic_and_skeleton():
    p = "theorem foo : True := by\n  intro h\n  simp [bar]\n  exact h"
    assert am.first_tactic(p) == "intro"
    assert am.skeleton(p, depth=3) == "intro>simp>exact"
    # focusing dots and comments are stripped / ignored
    p2 = "theorem g : True := by\n  · constructor\n  -- a comment\n  rfl"
    assert am.first_tactic(p2) == "constructor"
    assert am.skeleton(p2, depth=2) == "constructor>rfl"
    assert am.first_tactic("") is None


@pytest.mark.parametrize("reason,fb,expected", [
    ("ok", "Proof verified.", "ok"),
    ("loophole", "uses disallowed tactic(s) sorry.", "loophole_sorry"),
    ("no_goal", "no theorem/lemma/example declaration found", "truncation"),
    ("compile_error", "unknown identifier 'Foo.bar'", "knowledge_hallucinated_lemma"),
    ("compile_error", "unexpected token ':='; expected term", "formalization_syntax"),
    ("compile_error", "Failed at step 7 (`ring`): unsolved goals", "reasoning_deep"),
    ("compile_error", "Failed at step 1 (`simp`): unsolved goals", "reasoning_shallow"),
])
def test_classify(reason, fb, expected):
    assert am._classify(reason, fb) == expected


def _cell(name, attempts):
    return {"theorem_name": name, "attempts": attempts, "stop_reason": "x"}


def test_analyze_end_to_end(tmp_path):
    run = tmp_path / "run"
    asd = run / "agent_states"
    asd.mkdir(parents=True)

    # solved cell: 2 distinct approaches, the 2nd verifies
    solved = _cell("Algebra__ex1", [
        {"proof": "theorem t := by simp", "reason": "compile_error",
         "feedback": "Failed at step 1 (`simp`): unsolved goals", "kind": "propose"},
        {"proof": "theorem t := by ring", "reason": "ok", "feedback": "Proof verified.", "kind": "propose"},
    ])
    # unsolved cell with COLLAPSED diversity: same wrong first tactic 4x (resampling)
    collapsed = _cell("Algebra__ex2", [
        {"proof": "theorem t := by nlinarith", "reason": "compile_error",
         "feedback": "Failed at step 1 (`nlinarith`): unsolved goals", "kind": "propose"}
    ] * 4)
    # unsolved knowledge-failure cell (hallucinated lemma)
    knowledge = _cell("Topology__ex1", [
        {"proof": "theorem t := by exact Foo.nonexistent", "reason": "compile_error",
         "feedback": "unknown identifier 'Foo.nonexistent'", "kind": "propose"}
    ])
    for c in (solved, collapsed, knowledge):
        (asd / f"{c['theorem_name']}__seed0.json").write_text(json.dumps(c))

    res = am.analyze(str(run))
    assert res["n_cells"] == 3
    assert res["solve_rate"] == round(1 / 3, 3)

    # A1: collapsed unsolved cell has low diversity (1 distinct / 4 attempts = 0.25)
    div = res["A1_diversity"]
    assert div["unsolved"]["n_cells"] == 2
    assert div["solved"]["first_tactic_diversity"] == 1.0  # 2 distinct / 2

    # A2: taxonomy buckets both unsolved cells
    tax = res["A2_taxonomy"]["cell_pct"]
    assert "reasoning_shallow" in tax and "knowledge_hallucinated_lemma" in tax

    # A4: two subfields present
    strat = res["A4_stratify"]
    assert set(strat) == {"Algebra", "Topology"}
    assert strat["Algebra"]["n"] == 2
