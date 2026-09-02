# Budget-Bounded Agentic Theorem Proving

A controlled study of **what actually moves the solve rate of a frozen whole-proof Lean prover under a
fixed per-problem token budget** — and, when the answer turned out to be "almost nothing," a careful
account of *why*, backed by an audited evaluation harness.

Two open ~7–8B provers, two benchmarks, ≥3 seeds everywhere, on an academic Slurm cluster (Columbia
Insomnia). Every number here is reproducible without a datacenter.

> **Status: complete. No further experiments are planned.**
> Phases 0–8 plus an independent audit and a post-draft strengthening sprint are all closed. A paper
> draft lives in [`paper/floor/main.tex`](paper/floor/main.tex) (14pp, compiles clean); what remains
> there is writing, not experiments. **New to this repo? Read [`HANDOFF.md`](HANDOFF.md) first** — it
> is the guided tour: which docs are live vs. historical, what every phase asked and answered, and
> which claims carry caveats.

---

## The question

For a fixed whole-proof theorem prover — an LLM that emits a complete Lean proof, gets it checked, and
retries within a token budget — three questions, in the order they were actually asked:

1. **Does agentic scaffolding help?** Premise retrieval, memory of failed attempts, an LLM reviewer
   step, tactic-skeleton hints, forced approach diversity, smarter *within-problem* budget allocation —
   does any of it buy solves over just sampling more whole-proof attempts at the same budget?
2. **If not, why not?** What is actually limiting the model, and does *any* lever move it — more
   search, more compute, fine-tuning, RL?
3. **(Emerged mid-project, became the main positive result)** Does *how a fixed total budget is split
   across a batch of different problems* matter, independent of any change to the model or its
   scaffolding?

### Report `pass@B`, not `pass@k`

Everything is measured against a hardware-independent compute budget `B` = total LLM-generated tokens
per problem, summed across every model call. `pass@B` is reported as a **curve** over 2k/8k/32k/128k
tokens, ≥3 seeds, mean ± seed-std. Wall-clock and GPU-hours are logged but never the reported axis.

---

## What we found

### 1. The headline curves (`pass@B`, 3 seeds, mean ± std)

| budget | miniF2F · Goedel | miniF2F · DeepSeek | ProofNet# · Goedel | ProofNet# · DeepSeek |
|--------|------------------|--------------------|--------------------|----------------------|
| 2k   | 29.6% ± 3.3% | 27.9% ± 2.1% | 4.8% ± 1.4% | 5.4% ± 0.5% |
| 8k   | 60.1% ± 1.9% | 57.9% ± 1.7% | 9.3% ± 1.1% | 13.1% ± 0.8% |
| 32k  | 69.5% ± 0.6% | 67.1% ± 0.9% | 12.0% ± 0.6% | 18.3% ± 1.6% |
| 128k | 74.9% ± 0.9% | 72.0% ± 0.5% | 14.3% ± 0.8% | 22.2% ± 1.7% |

miniF2F flattens by 128k; ProofNet# is still climbing at much lower absolute rates. The asymmetry
replicates on both models independently — it is a task property, not a model artifact. (The 2k column
is attempt-starved: the median cell completes **zero** full propose attempts inside a 2k cap. Footnote
it; don't read it as a comparable point on the same curve.)

### 2. An execution floor: nothing we tried at test time moves it

| Intervention | Phase | Result |
|---|---|---|
| Agentic scaffolding (retrieval, memory, reviewer, skeletons, diversity, alloc) | 1 | **Null** OFAT; two components actively *hurt* out-of-distribution (BM25 retrieval: −36 net flips on ProofNet#) |
| Forced approach diversity, on the fully-trapped core | 2 (F6) | **Null, causally.** Diversity rises 42–70% under a budget-matched manipulation check; solves stay flat, quality mildly degrades |
| Hammer / SMT closing tactics | 3 | **NO-GO** — portfolio closes 0/40 trapped problems |
| More of the same budget on already-trapped problems | 5 | **~0 new solves** (Goedel 1, DeepSeek 0) |
| Closing-likelihood SFT | 6 A/B | **Null** — surfaces an exposure-bias signature instead of a fix |
| Lightweight post-hoc GRPO RL | 6 C | **Null**, with a saturated-policy signature (near-zero KL, flat reward) |
| Verified-state re-grounding | 7 | **Null** in its strongest form, incl. a matched fresh-resample control |
| Full lab-scale Base→SFT→RL, two lineages | 8 | **Withdrawn** — our own audit found a phase-specific verifier bug that mechanically forces 0% regardless of model quality. We report the bug, not the number. |
| Prompted `sorry`-deferred subgoal decomposition | WS6 | **NO-GO on both models.** One model stated correct intermediate facts but still could not *defer* them — the gap is treating sub-facts as separable obligations, not identifying them |

**The mechanism (Phase 2, tested causally, not just correlationally): approach *discovery* is not the
bottleneck; within-approach *execution depth* is.** That single result explains the whole column above
— any lever that only changes *which* approach gets tried should not be expected to help, and none did.

**Scope, stated honestly:** this floor is scoped to **frozen whole-proof provers** and to the
interventions we could actually run and trust. Systems that *train* for decomposition are a different
class, and none of this is evidence against them. All findings are established at 7–8B; whether the
floor persists at 32B+ is untested and is the most important open question the project leaves behind.

### 3. The one lever that did move something: cross-problem budget allocation

Not a model change and not a scaffold change, but a *policy* question — given a fixed total budget, how
should it be split across a batch of *different* problems. A realizable, mechanism-informed allocation
policy saves **~30% of compute at 90% of full-budget accuracy** on Goedel×ProofNet#.

Reported as the strongest lever found, **not** as a settled positive: a paired per-problem bootstrap CI
on that estimate crosses zero, and the second model's estimate is weaker and also inconclusive at 95%
even at 8 seeds. See [`results/phase4/ALLOCATION.md`](results/phase4/ALLOCATION.md).

### 4. The measurement contribution: five harness bugs and two reporting gaps

Auditing our own harness turned out to be a first-class result. Each bug, left unfixed, would have
shipped a wrong headline in a specific silent direction:

1. A Lean elaboration-**heartbeat** misconfiguration that silently corrupted **17.8%** of miniF2F
   refinement-loop feedback (and flipped 13/1212 final verdicts).
2. A **soundness hole** scoring truncated non-proofs as solved.
3. A **wedged-REPL** bug scoring a hung process as success.
4. A phase-specific **`no_goal` verifier bug** mechanically forcing 0% for continuation-style
   completions — this is what withdrew Phase 8.
5. A **Lean-staging concurrency race**.

Plus two gaps that change how any comparable result should be read:

- **pass@budget ≠ pass@N**, and they diverge in a budget-dependent way that is not a fixed offset.
- **A per-problem bootstrap CI on one generation run bounds only within-run sampling variance**, not
  the run-to-run campaign variance an independent replication reveals to be larger. We caught this the
  hard way: a retrieval effect whose CI was entirely positive on one run ([+0.82,+6.15]pp) failed to
  reproduce on an independent replication whose own CI ([−1.78,+3.14]pp) does not even overlap it.

---

## Where things stand

- **Experiments: done.** Phases 0–8, the post-Phase-8 audit, and the WS6 strengthening sprint are all
  closed. No GPU work is planned or queued.
- **Paper: drafted, not finished.** `paper/floor/main.tex` compiles clean at 14pp with all findings
  folded in. Open `\todo`s are a citation pass, three figures (generation scripts exist), and the
  author list (deliberately blank for anonymization).
- **Open threads**, all documented, none blocking: scale (7–8B only — feasibility of a 32B calibration
  cell is scoped in [`results/phase_scale32b/FEASIBILITY.md`](results/phase_scale32b/FEASIBILITY.md)
  but was deliberately not run); Phase 4's allocation result confirmed on one model only; artifact
  release packaging.

See [`HANDOFF.md`](HANDOFF.md) §"Open threads" for the full list with context.

---

## Repository tour

```
src/atp/
├── lean/         # Lean 4 REPL backend, whole-proof verifier, compiler-error parser
├── models/       # vLLM client, budget meter, prompt templates
├── agents/       # propose→verify→refine loop, components/ (the Phase 1 ablation axes),
│                 #   stepwise/tactic_stepwise (Phase 7), decomposition (WS6)
├── alloc/        # Phase 4: features, difficulty predictor, policies, frontier, halving
├── budget/       # token accounting and stopping
├── data/         # miniF2F / ProofNet# loaders, exclusions, contamination + disjointness checks
├── eval/         # pass@B metrics, run manifests, sweep harness, aggregation, plots
└── rl/           # Phase 6 Stage C: GRPO reward, diversity, subset selection
configs/          # 81 versioned experiment YAMLs (+ base + smoke)
slurm/            # 31 restartable sbatch scripts
scripts/          # per-phase analysis + one-off probes (named by phase)
results/          # per-phase result docs ("the receipts") + metrics + run manifests
env/              # frozen pip/conda listings for the environment that produced every result
tests/            # pytest mirroring src/ (markers: slow, gpu, lean)
paper/floor/      # the paper draft
```

`configs/`, `slurm/`, `scripts/`, `results/`, `env/` and `paper/floor/` each have their own `README.md`
indexing what's inside — start there rather than reading the directory listing.

## Documentation map

Read in this order:

| Doc | Role |
|---|---|
| [`HANDOFF.md`](HANDOFF.md) | **Start here.** Guided tour: doc roles, phase index, caveats, open threads |
| [`SYNTHESIS.md`](SYNTHESIS.md) | The consolidated narrative + the corrections log |
| [`PROJECT_SUMMARY.md`](PROJECT_SUMMARY.md) | Exactly what was run, on what data, with what config, and the exact number — per phase |
| `results/*/` | The receipts each summary cites (`results/phase1/FINDINGS.md`, `results/phase4/ALLOCATION.md`, …) |
| [`PROGRESS.md`](PROGRESS.md) / [`DECISIONS.md`](DECISIONS.md) | Append-only lab notebook and design-decision log. Primary sources; large. |
| [`CLAUDE.md`](CLAUDE.md) | Operating rules + cluster cheatsheet |

`PROJECT_PLAN.md`, `PLAN_NEXT.md`, `PHASE2_PLAN.md`, `PHASE3_PLAN.md`, `AUDIT_PLAN.md` are **historical
plans**, kept for the audit trail. Each carries a banner saying when it was written and what superseded
it — do not read them as current state.

## Reproducibility

Every experiment is a versioned YAML in `configs/` and writes a `run_manifest.json` (git SHA, config
hash, seed, model revision, mathlib commit, Lean version, host, GPU type, timestamps). Those manifests
are tracked in this repo. The toolchain is pinned exactly, because Mathlib API drift between releases
silently invalidates a prover trained against an older API:

| Component | Pin |
|-----------|-----|
| Prover A | `Goedel-LM/Goedel-Prover-V2-8B` @ `dfd02e6` — Lean `v4.9.0-rc1`, mathlib4 `2f65ba7` |
| Prover B | `deepseek-ai/DeepSeek-Prover-V2-7B` @ `a8d9e144` — Lean `v4.9.0`, mathlib4 `f0957a7` |
| Mathlib (A) | `xinhjBrant/mathlib4` @ `2f65ba7f1a9144b20c8e7358513548e317d26de1` (custom fork, built from source) |
| Serving stack | vLLM `0.8.5.post1`, PyTorch `2.6.0+cu124`, transformers `4.51.3` |

Prover A's Mathlib pin is a **custom fork** matched to the prover's training-time API; its oleans are
not in Mathlib's public cache and must be built from source. Full pin rationale and the
measurement-validity argument are in `DECISIONS.md`. A frozen dependency listing is in
[`env/`](env/).

## Running it

```bash
module load anaconda/2023.09
conda activate /insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study/scratch/conda-envs/atp

make test     # fast suite — login-node safe, no GPU/Lean (~2 min, 730 tests)
make lint     # ruff
make verify   # both of the above — the pre-commit gate
make smoke    # tiny end-to-end sanity on an interactive GPU session (2–5 problems)

# Reproduce a baseline pass@B curve (audited miniF2F test, 3 seeds):
mkdir -p logs results
sbatch slurm/sweep.sh configs/phase0_baseline.yaml baseline   # restartable; resume skips done cells
```

The sweep stages Mathlib oleans to node-local SSD, brings up a vLLM server, runs the agent over the
problem set, and writes per-problem JSON, a `pass@B` curve, and a manifest to `results/baseline/`. Jobs
are restartable by design (the cluster preempts and requeues): completed `(config, seed, problem)` cells
are skipped on resume.

### Cluster gotchas baked into the harness

Documented in `DECISIONS.md` / `CLAUDE.md`, and worth knowing before you touch a Slurm script: Slurm
jobs inherit a per-session SSH proxy that must be unset before any download; Mathlib's ~4.7k-olean cold
load must be staged to node-local SSD or it causes a shared-GPFS storm; the Lean REPL must be driven
over a PTY with a recursive `LEAN_PATH`; the REPL env pickle is deliberately **not** used (it silently
corrupts verdicts on `@[init]` tactic extensions). Every GPU sweep is gated on a verification probe that
must accept a `norm_num` proof and reject a false one, so a broken environment fails fast instead of
masquerading as a low pass rate.

## Conventions

- **Test-first.** Every module ships `tests/test_<module>.py`; the fast suite must be green before
  anything is "done". Hardware tests are marked `@pytest.mark.{slow,gpu,lean}`.
- **Append-only lab notebook.** `PROGRESS.md` and `DECISIONS.md` are never rewritten. Corrections are
  appended with pointers, and the superseded text is left in place — the audit trail is a deliberate
  asset, not clutter.
- **Configs, not magic numbers.** Every experiment is a versioned YAML emitting a run manifest.
- **Restartable everything.** Any job > 20 min checkpoints and resumes cleanly.
- **Pre-registration.** Decision rules and risk analyses are written *before* expensive runs (see
  `results/phase4/PREDICTOR_V2_DESIGN.md`, `results/phase_decomp/DESIGN.md` for worked examples). Two
  probes were closed early by their own pre-registered stopping rules, saving substantial GPU time.

## License

[MIT](LICENSE). If you use this work, please cite the repository; a paper reference will be added on
release.
