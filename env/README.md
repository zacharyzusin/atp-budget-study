# Frozen environment

Captured 2026-09-02 at project close, from the conda env that produced every result in this repo:
`<project>/scratch/conda-envs/atp` (Python 3.11.15).

| File | What it is |
|---|---|
| `pip-freeze.txt` | `pip freeze` — exact versions of all 203 Python packages |
| `conda-explicit.txt` | `conda list --explicit` — conda-level packages with URLs, usable with `conda create --file` |

Key pins, which match the ones documented in `README.md` and `DECISIONS.md`:

```
vllm==0.8.5.post1
torch==2.6.0
transformers==4.51.3
numpy==2.2.6
scikit-learn==1.9.0
pytest==9.0.3
ruff==0.15.16
```

**These pins are not incidental.** The prover models are matched to specific Lean/Mathlib API
versions, and Mathlib API drift between releases silently invalidates a prover trained against an
older API — a wrong pin does not error, it just lowers the pass rate. The Lean and Mathlib pins are
in the top-level `README.md`; the rationale is in `DECISIONS.md`.

Note that the Lean toolchain and the custom Mathlib fork are **not** captured here — they live in
`scratch/` and must be built from source. See `scripts/setup_lean_env.sh`.
