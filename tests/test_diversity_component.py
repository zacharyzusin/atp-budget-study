"""Fast tests for the Phase 2 Step C diversity-injection component (no GPU/Lean)."""
from atp.agents.components import DiversityInjection, build_components
from atp.agents.components.base import PromptContext
from atp.agents.components.diversity import _distinct_openings, _opening_tactic
from atp.agents.state import Attempt


def _attempt(proof):
    return Attempt(index=0, kind="propose", proof=proof, ok=False, reason="compile_error",
                   feedback="x", completion_tokens=10)


def _ctx(kind, history):
    class _Thm:
        name = "t"
    return PromptContext(theorem=_Thm(), kind=kind, round_index=len(history), history=tuple(history))


def test_opening_tactic_and_distinct():
    assert _opening_tactic("theorem t := by\n  nlinarith [sq_nonneg x]") == "nlinarith"
    assert _opening_tactic("theorem t := by\n  · simp\n  ring") == "simp"
    assert _opening_tactic("") is None
    hist = [_attempt("theorem t := by simp"), _attempt("theorem t := by simp [foo]"),
            _attempt("theorem t := by nlinarith")]
    assert _distinct_openings(tuple(hist)) == ["simp", "nlinarith"]  # de-duped, first-seen order


def test_first_proposal_is_noop():
    comp = DiversityInjection()
    # empty history => nothing to diverge from => prompt unchanged
    assert comp.decorate_prompt("PROMPT", _ctx("propose", [])) == "PROMPT"


def test_refine_is_untouched():
    comp = DiversityInjection()
    hist = [_attempt("theorem t := by simp")]
    assert comp.decorate_prompt("PROMPT", _ctx("refine", hist)) == "PROMPT"


def test_propose_lists_tried_openings_and_asks_for_different():
    comp = DiversityInjection()
    hist = [_attempt("theorem t := by simp"), _attempt("theorem t := by nlinarith")]
    out = comp.decorate_prompt("PROMPT", _ctx("propose", hist))
    assert out.startswith("PROMPT")
    assert "`simp`" in out and "`nlinarith`" in out
    assert "fundamentally different" in out.lower()


def test_max_listed_caps_the_list():
    comp = DiversityInjection(max_listed=2)
    hist = [_attempt(f"theorem t := by tac{i}") for i in range(5)]
    out = comp.decorate_prompt("P", _ctx("propose", hist))
    assert "`tac0`" in out and "`tac1`" in out and "`tac2`" not in out


def test_wiring_off_by_default_on_when_enabled():
    from atp.config import AgentCfg, ComponentsCfg, DiversityCfg

    class _Cfg:
        agent = AgentCfg(components=ComponentsCfg())
    assert build_components(_Cfg()).names == ()  # default off → empty pipeline (Phase 0 identity)

    class _Cfg2:
        agent = AgentCfg(components=ComponentsCfg(diversity=DiversityCfg(enabled=True)))
    assert "diversity_injection" in build_components(_Cfg2()).names
