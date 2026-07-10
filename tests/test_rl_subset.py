"""Subset-selection tests (pure)."""

from __future__ import annotations

from atp.rl import subset as S


def test_band_bounds_excludes_zero_and_perfect():
    lo, hi = S.band_bounds(16, 1 / 16, 10 / 16)
    assert (lo, hi) == (1, 10)
    # a wide fractional band still clamps to [1, k-1] (never 0-solve or perfect K/K)
    lo, hi = S.band_bounds(16, 0.0, 1.0)
    assert (lo, hi) == (1, 15)


def test_select_keeps_only_band():
    counts = {f"p{i}": i for i in range(0, 17)}  # solve counts 0..16
    split = S.select_by_solve_rate(counts, k=16, n_train=100, n_heldout=100, seed=0)
    chosen = set(split.train) | set(split.heldout)
    # 0 (no signal) and 16 (no headroom) excluded; 1..10 kept => 10 problems
    assert chosen == {f"p{i}" for i in range(1, 11)}
    assert split.band_size == 10


def test_train_heldout_disjoint():
    counts = {f"p{i}": (i % 10) + 1 for i in range(500)}  # all in band 1..10
    split = S.select_by_solve_rate(counts, k=16, n_train=256, n_heldout=200, seed=1)
    assert len(split.train) == 256
    assert len(split.heldout) == 200
    assert set(split.train).isdisjoint(split.heldout)
    assert split.enough


def test_deterministic_given_seed():
    counts = {f"p{i}": (i % 10) + 1 for i in range(500)}
    a = S.select_by_solve_rate(counts, k=16, seed=7)
    b = S.select_by_solve_rate(counts, k=16, seed=7)
    c = S.select_by_solve_rate(counts, k=16, seed=8)
    assert a.train == b.train
    assert a.train != c.train  # different seed -> different (shuffled) draw


def test_small_band_reports_not_enough_gracefully():
    counts = {"a": 5}  # single in-band problem -> train gets it, heldout empty
    split = S.select_by_solve_rate(counts, k=16, n_train=256, n_heldout=200, seed=0)
    assert split.train == ("a",)
    assert split.heldout == ()
    assert not split.enough
