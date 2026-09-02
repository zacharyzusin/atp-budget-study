"""Phase 8 step 2 — compile-on-ALL-pins intersection generalized to N pins/models.

Generalizes scripts/h1_intersection.py (hardcoded to Goedel+DeepSeek) to an arbitrary set of
statement_validation.json paths, so adding Cluster-A models that reuse an EXISTING pin costs nothing
(their failures are already captured by that pin's validation file) and a genuinely new pin only
needs its own statement_validation.json to be included.
"""
import json
import os

from scripts.phase8_intersection import compute_intersection


def _write_validation(path, n_problems, failures):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"n_problems": n_problems, "failures": failures}, f)


def test_intersection_no_failures_any_pin(tmp_path):
    v1 = tmp_path / "pinA.json"
    v2 = tmp_path / "pinB.json"
    _write_validation(v1, 3, [])
    _write_validation(v2, 3, [])
    result = compute_intersection([str(v1), str(v2)])
    assert result.n_total == 3
    assert result.excluded_names == set()
    assert result.intersection_size == 3


def test_intersection_excludes_union_of_failures(tmp_path):
    v1 = tmp_path / "pinA.json"
    v2 = tmp_path / "pinB.json"
    _write_validation(v1, 3, ["a"])
    _write_validation(v2, 3, ["b"])
    result = compute_intersection([str(v1), str(v2)])
    assert result.excluded_names == {"a", "b"}
    assert result.intersection_size == 1


def test_intersection_dict_style_failures(tmp_path):
    # statement_validation.json failures can be plain strings OR {"name":..., "reason":...} dicts —
    # support both like the original h1_intersection.py script did.
    v1 = tmp_path / "pinA.json"
    _write_validation(v1, 2, [{"name": "a", "reason": "unknown identifier"}])
    result = compute_intersection([str(v1)])
    assert result.excluded_names == {"a"}
    assert result.intersection_size == 1


def test_intersection_missing_validation_file_raises(tmp_path):
    missing = tmp_path / "does_not_exist.json"
    try:
        compute_intersection([str(missing)])
        raise AssertionError("expected FileNotFoundError")
    except FileNotFoundError:
        pass


def test_intersection_inconsistent_n_problems_raises(tmp_path):
    v1 = tmp_path / "pinA.json"
    v2 = tmp_path / "pinB.json"
    _write_validation(v1, 3, [])
    _write_validation(v2, 4, [])
    try:
        compute_intersection([str(v1), str(v2)])
        raise AssertionError("expected a mismatch error")
    except ValueError:
        pass


def test_intersection_reuses_shared_pin_validation_across_models():
    # The actual Phase 8 situation: multiple models (V1.5 triple, Goedel-SFT, BFS-Prover) share the
    # SAME already-built Goedel pin, so they contribute the SAME validation file — passing it
    # multiple times (once per model that reuses it) must not change the result.
    real_goedel = "results/minif2f/statement_validation.json"
    real_deepseek = "results/phase2/deepseek/statement_validation/minif2f_deepseekpin.json"
    if not (os.path.exists(real_goedel) and os.path.exists(real_deepseek)):
        return  # only meaningful inside the real repo checkout
    result_once = compute_intersection([real_goedel, real_deepseek])
    result_dup = compute_intersection([real_goedel, real_goedel, real_deepseek])
    assert result_once.excluded_names == result_dup.excluded_names
    assert result_once.intersection_size == result_dup.intersection_size


def test_full_repo_intersection_is_all_problems():
    """The real finding this step produced: BOTH existing pins have zero elaboration failures on
    BOTH benchmarks, so the compile-on-all-pins intersection is simply the full problem set — no
    exclusions. Cluster-A models all reuse one of these two pins, so this result carries over
    unchanged; skip if the repo's real validation files aren't present (e.g. a fresh checkout)."""
    pairs = [
        (244, [
            "results/minif2f/statement_validation.json",
            "results/phase2/deepseek/statement_validation/minif2f_deepseekpin.json",
        ]),
        (186, [
            "results/proofnet_sharp/statement_validation.json",
            "results/phase2/deepseek/statement_validation/proofnet_deepseekpin.json",
        ]),
    ]
    for n_expected, paths in pairs:
        if not all(os.path.exists(p) for p in paths):
            return
        result = compute_intersection(paths)
        assert result.excluded_names == set()
        assert result.n_total == n_expected
        assert result.intersection_size == n_expected
