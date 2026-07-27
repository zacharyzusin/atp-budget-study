"""Learned difficulty predictor: will a still-running cell ever solve within 128k? (Task 4.3)

At checkpoint `c` the realizable policy must decide, for each **not-yet-solved** cell, whether to
keep funding it. We train a small classifier on the leakage-free checkpoint-`c` features to predict
eventual solve, scored by **problem-grouped** cross-validated ROC-AUC (no problem in both train and
test). The AUC-vs-`c` curve is the headline diagnostic: how early is trapped-ness detectable, hence
how much of the oracle headroom a realizable policy can capture.

Decision population = cells *not already solved by* `c` (a solved cell needs no further budget).
Among those, the label is simply `eventual_solve` (such a cell, if solved, must solve after `c`).
"""

from __future__ import annotations

import numpy as np

from atp.alloc.features import CheckpointRow


def rows_to_xy(rows: list[CheckpointRow], checkpoint: int, feature_names: tuple[str, ...] | None = None):
    """Build (X, y, groups, feature_names) for one checkpoint from its not-yet-solved cells.

    Filters to `row.checkpoint == checkpoint` and `not row.solved_by_c` (the decision population).
    `y = eventual_solve`. Returns float arrays; `groups` = problem_name (for grouped CV).
    `feature_names` defaults to the original v1 set; pass `CheckpointRow.FEATURE_NAMES_V2` for the
    WS6 item 4 richer feature set (results/phase4/PREDICTOR_V2_DESIGN.md).
    """
    sel = [r for r in rows if r.checkpoint == checkpoint and not r.solved_by_c]
    names = list(feature_names or CheckpointRow.FEATURE_NAMES)
    X = np.array([[r.features(tuple(names))[k] for k in names] for r in sel], dtype=float)
    y = np.array([int(r.eventual_solve) for r in sel], dtype=int)
    groups = np.array([r.problem_name for r in sel])
    return X, y, groups, names


def rows_to_xy_by_seed(rows: list[CheckpointRow], checkpoint: int, seeds: set[int],
                        feature_names: tuple[str, ...] | None = None):
    """Same as `rows_to_xy` but restricted to rows whose `.seed` is in `seeds` -- the seed-holdout
    guard (WS6 item 4 pre-registration): feature engineering / model selection must never see the
    held-out seed's rows, and the held-out seed is evaluated exactly once at the end."""
    sel = [r for r in rows if r.checkpoint == checkpoint and not r.solved_by_c and r.seed in seeds]
    names = list(feature_names or CheckpointRow.FEATURE_NAMES)
    X = np.array([[r.features(tuple(names))[k] for k in names] for r in sel], dtype=float)
    y = np.array([int(r.eventual_solve) for r in sel], dtype=int)
    groups = np.array([r.problem_name for r in sel])
    return X, y, groups, names


def holdout_seed_eval(rows: list[CheckpointRow], checkpoint: int, holdout_seed: int,
                       train_seeds: set[int], model_factory,
                       feature_names: tuple[str, ...] | None = None) -> float:
    """Fit ONE model on `train_seeds`' rows only (already selected via CV on those seeds), evaluate
    ONCE on `holdout_seed`'s rows. Returns AUC (nan if degenerate -- single class or no held-out
    positives). This is the final check, not an average into the CV number (WS6 item 4 CV guard)."""
    from sklearn.metrics import roc_auc_score

    Xtr, ytr, _, names = rows_to_xy_by_seed(rows, checkpoint, train_seeds, feature_names)
    Xho, yho, _, _ = rows_to_xy_by_seed(rows, checkpoint, {holdout_seed}, feature_names)
    if len(Xtr) == 0 or len(Xho) == 0 or len(np.unique(ytr)) < 2 or len(np.unique(yho)) < 2:
        return float("nan")
    model = model_factory()
    model.fit(Xtr, ytr)
    scores = model.predict_proba(Xho)[:, 1]
    return float(roc_auc_score(yho, scores))


def cv_auc(X: np.ndarray, y: np.ndarray, groups: np.ndarray, model_factory,
           n_splits: int = 5, seed: int = 0) -> tuple[float, np.ndarray]:
    """Out-of-fold ROC-AUC under GroupKFold (no group spans train/test). Returns (auc, oof_scores).

    `model_factory` is a 0-arg callable returning a fresh unfitted estimator with `predict_proba`.
    Degenerate cases (one class present, or fewer groups than folds) return AUC = nan.
    """
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import GroupKFold

    n_groups = len(set(groups.tolist()))
    if len(np.unique(y)) < 2 or n_groups < n_splits:
        return float("nan"), np.full(len(y), np.nan)

    oof = np.full(len(y), np.nan, dtype=float)
    gkf = GroupKFold(n_splits=n_splits)
    for tr, te in gkf.split(X, y, groups):
        if len(np.unique(y[tr])) < 2:
            continue
        model = model_factory()
        model.fit(X[tr], y[tr])
        oof[te] = model.predict_proba(X[te])[:, 1]
    mask = ~np.isnan(oof)
    if len(np.unique(y[mask])) < 2:
        return float("nan"), oof
    return float(roc_auc_score(y[mask], oof[mask])), oof


def logistic_factory():
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=1000, class_weight="balanced"),
    )


def gbt_factory():
    from sklearn.ensemble import GradientBoostingClassifier
    return GradientBoostingClassifier(random_state=0)
