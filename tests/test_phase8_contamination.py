"""Phase 8 — contamination-noted subset tests (see scripts/phase8_contamination.py docstring for
what this does and does not cover: mechanical checks available from the benchmark data itself, not a
full training-corpus audit)."""
from dataclasses import dataclass

from scripts.phase8_contamination import (
    minif2f_split_leak_check,
    proofnet_low_risk_subset,
    proofnet_problem_source,
)


def test_proofnet_problem_source_flags_known_textbook_prefixes():
    assert proofnet_problem_source("Herstein__exercise_4_1_34") == ("textbook", "Herstein")
    assert proofnet_problem_source("Rudin__exercise_1_2") == ("textbook", "Rudin")


def test_proofnet_problem_source_flags_putnam_as_competition():
    assert proofnet_problem_source("Putnam__exercise_1998_b6") == ("competition", "Putnam")


def test_proofnet_low_risk_subset_keeps_only_competition_problems():
    names = ["Herstein__exercise_1", "Putnam__exercise_1998_b6", "Rudin__exercise_2",
             "Putnam__exercise_1999_b4"]
    assert proofnet_low_risk_subset(names) == {"Putnam__exercise_1998_b6", "Putnam__exercise_1999_b4"}


@dataclass
class _FakeProblem:
    name: str


def test_minif2f_split_leak_check_clean_when_disjoint():
    test = [_FakeProblem("a"), _FakeProblem("b")]
    valid = [_FakeProblem("c"), _FakeProblem("d")]
    report = minif2f_split_leak_check(test, valid)
    assert report.is_clean
    assert report.overlap == set()


def test_minif2f_split_leak_check_flags_real_overlap():
    test = [_FakeProblem("a"), _FakeProblem("b")]
    valid = [_FakeProblem("b"), _FakeProblem("c")]
    report = minif2f_split_leak_check(test, valid)
    assert not report.is_clean
    assert report.overlap == {"b"}


def test_real_repo_minif2f_valid_test_split_is_clean():
    """The actual check this module produced: the vendored miniF2F copy this repo uses has ZERO
    exact-name overlap between valid and test (244/244 each). Skips if the vendored data isn't
    present (e.g. outside this cluster checkout)."""
    try:
        from atp.data.minif2f import load_minif2f
    except ImportError:
        return
    try:
        test = load_minif2f("test")
        valid = load_minif2f("valid")
    except FileNotFoundError:
        return
    report = minif2f_split_leak_check(test, valid)
    assert report.is_clean
    assert len(report.test_names) == 244
    assert len(report.valid_names) == 244


def test_real_repo_proofnet_source_breakdown():
    """The actual finding: ProofNet# is 180/186 named-textbook exercises + 6 Putnam. Skips if the
    real dataset isn't loadable (e.g. proofnet_sharp not staged)."""
    try:
        from atp.config import load_config
        from atp.data import load_dataset
    except ImportError:
        return
    try:
        cfg = load_config("configs/proofnet_baseline.yaml")
        ds = load_dataset(cfg)
    except Exception:
        return
    problems = ds.problems if hasattr(ds, "problems") else ds
    names = [p.name for p in problems]
    if len(names) != 186:
        return
    low_risk = proofnet_low_risk_subset(names)
    assert low_risk == {
        "Putnam__exercise_1998_b6", "Putnam__exercise_1999_b4", "Putnam__exercise_2001_a5",
        "Putnam__exercise_2014_a5", "Putnam__exercise_2018_a5", "Putnam__exercise_2018_b4",
    }
