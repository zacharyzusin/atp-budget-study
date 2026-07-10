import importlib.util
import json
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "phase6_stage_c_gate", Path(__file__).parents[1] / "scripts" / "phase6_stage_c_gate.py"
)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)  # type: ignore[union-attr]


def _state(name, seed, solved, spent, attempts=None):
    return {
        "theorem_name": name,
        "done": solved,
        "stop_reason": "solved" if solved else "budget_exhausted",
        "budget": {"spent": spent},
        "attempts": attempts or [],
        "_seed": seed,
    }


def test_pass_at_1_is_mean_over_seeds_of_solved_fraction():
    states = [
        _state("p1", 0, True, 100),
        _state("p2", 0, False, 8192),
        _state("p1", 1, False, 8192),
        _state("p2", 1, True, 200),
    ]
    assert gate.pass_at_1(states, budget=8192) == 0.5


def test_pass_at_k_is_any_seed_solves():
    states = [
        _state("p1", 0, True, 100),
        _state("p1", 1, False, 8192),
        _state("p2", 0, False, 8192),
        _state("p2", 1, False, 8192),
    ]
    assert gate.pass_at_k(states, budget=8192) == 0.5


def test_solved_within_respects_budget_even_if_marked_done():
    # tokens_to_solve beyond the target budget doesn't count as solved-within-budget.
    states = [_state("p1", 0, True, 20000)]
    assert gate.pass_at_1(states, budget=8192) == 0.0


def test_unsound_rate_counts_loophole_reason_attempts():
    states = [
        _state("p1", 0, False, 8192, attempts=[
            {"reason": "loophole", "proof": "sorry"},
            {"reason": "compile_error", "proof": "bad"},
        ]),
        _state("p2", 0, False, 8192, attempts=[{"reason": "ok", "proof": "fine"}]),
    ]
    assert gate.unsound_rate(states) == 1 / 3


def test_distinct_trigram_ratio_uses_final_attempt_only():
    states = [_state("p1", 0, True, 100, attempts=[
        {"reason": "compile_error", "proof": "a a a a a a"},
        {"reason": "ok", "proof": "a b c d e f"},
    ])]
    assert gate.distinct_trigram_ratio(states) == 1.0


def test_training_reward_rose_compares_first_vs_second_half():
    p = Path("/tmp/probe_metrics_test.jsonl")
    p.write_text("\n".join(json.dumps(r) for r in [
        {"step": 1, "reward/cum_solve_rate": 0.1, "kl": 0.001},
        {"step": 2, "reward/cum_solve_rate": 0.15, "kl": 0.002},
        {"step": 3, "reward/cum_solve_rate": 0.2, "kl": 0.002},
        {"step": 4, "reward/cum_solve_rate": 0.25, "kl": 0.003},
    ]))
    assert gate.training_reward_rose(p) is True
    assert abs(gate.mean_kl(p) - 0.002) < 1e-9
    p.unlink()
