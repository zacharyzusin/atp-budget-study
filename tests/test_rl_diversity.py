"""Diversity-metric tests (pure)."""

from __future__ import annotations

import math

import pytest

from atp.rl import diversity as D


def test_distinct_ngram_all_unique_is_one():
    # every trigram distinct
    assert D.distinct_ngram_ratio(["a b c d e"], n=3) == 1.0


def test_distinct_ngram_repetition_drops():
    # "a b c a b c" -> trigrams: (a,b,c),(b,c,a),(c,a,b),(a,b,c) => 3 unique / 4 total
    assert D.distinct_ngram_ratio(["a b c a b c"], n=3) == pytest.approx(3 / 4)


def test_distinct_ngram_identical_rollouts_collapse():
    # two identical rollouts -> unique grams unchanged, total doubles => ratio halves
    one = D.distinct_ngram_ratio(["a b c d"], n=3)
    two = D.distinct_ngram_ratio(["a b c d", "a b c d"], n=3)
    assert two < one


def test_distinct_ngram_too_short_is_zero():
    assert D.distinct_ngram_ratio(["a b"], n=3) == 0.0
    assert D.distinct_ngram_ratio([], n=3) == 0.0


def test_token_entropy_uniform_vs_peaked():
    uniform = D.token_entropy(["a b c d"])
    peaked = D.token_entropy(["a a a b"])
    assert uniform == pytest.approx(math.log(4))
    assert peaked < uniform


def test_token_entropy_empty():
    assert D.token_entropy([]) == 0.0
    assert D.token_entropy([""]) == 0.0


def test_retention_and_snapshot():
    assert D.retention(8.0, 10.0) == pytest.approx(0.8)
    assert D.retention(5.0, 0.0) == 1.0  # base 0 -> no collapse possible
    snap = D.diversity_snapshot(["a b c d", "e f g h"])
    assert set(snap) == {
        "diversity/distinct_3gram",
        "diversity/token_entropy",
        "diversity/mean_tokens",
    }
    assert snap["diversity/mean_tokens"] == pytest.approx(4.0)
