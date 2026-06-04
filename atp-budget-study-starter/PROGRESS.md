# PROGRESS.md

Append-only lab notebook. Add a dated entry after every work session and every experiment.
Newest entries at the bottom. Never delete history.

**Entry template:**
```
### YYYY-MM-DD — <short title>
- Did: <what changed / what ran>
- Tests: <pytest result, which markers>
- Numbers: <key metrics, budget, seeds, GPU-hours> (link to results/<...> if applicable)
- Issues: <anything broken / surprising>
- Next: <the single next step>
```

---

### 2026-06-04 — Project bootstrapped from plan
- Did: Received `PROJECT_PLAN.md` + `CLAUDE.md` + seeded `DECISIONS.md`. Repo not yet created.
- Tests: n/a (no code yet).
- Numbers: n/a.
- Issues: none.
- Next: Task 0.1 — create repo layout, `pyproject.toml` (pytest markers slow/gpu/lean), `Makefile`,
  pre-commit/ruff; commit; then Task 0.2 (Lean layer) and pin mathlib/Lean versions in `DECISIONS.md`.
