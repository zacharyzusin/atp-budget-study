# Phase 8 — model zoo: Cluster A pin triage (CHECK-IN #1)

**UPDATE 2026-07-05/06:** check-in #1 below is unchanged/still accurate. Step 2 (common intersection)
is DONE — trivially the full set, 244 miniF2F / 186 ProofNet#. Step 3 (metric battery) recovered from
an early NVML-thundering-herd contention issue (see PROGRESS.md) and is now largely healthy. **Step 4
— CHECK-IN #2 (the matched-pair floor table) is below.** This is the coordinator's/user's decision
gate; the final headline call (discovery vs. definitive-negative) is intentionally NOT made here.

---

## ⚠️ 2026-07-06 CORRECTION — THE CHECK-IN #2 FLOOR TABLE BELOW IS INVALID. DO NOT USE IT.

**Root cause**: `WholeProofAgent.from_config` (`src/atp/agents/whole_proof.py`) hardcoded
`template=WholeProofTemplate()`, ignoring `config.model.prompt_template` entirely.
`template_from_config(config)` — the function that would have correctly resolved
`DeepSeekV15Template`/`GoedelSFTTemplate`/etc. — existed but was **dead code, never called**, since
the very first commit that created this agent (2026-06-04, before Phase 0 started). Every model run
via `agent.mode: whole_proof` whose config asked for a prompt_template OTHER than `whole_proof` itself
was silently served `WholeProofTemplate`'s chat/proof-plan prompt instead of its own intended,
validated format.

**Confirmed by direct evidence, not inference**: pulled the actual "Received request" prompt vLLM
logged for the ORIGINAL V1.5-triple battery job behind the table below (job 11117638,
`p8battery_deepseek_v15_base_proofnet`) — it reads "Complete the following Lean 4 code:\n\n```lean4\n
...:= by sorry\n```\n\nBefore producing the Lean 4 code... provide a detailed proof plan..." — that is
`WholeProofTemplate`'s prompt, NOT `DeepSeekV15Template`'s (which should end the code block at `:= by`
with no `sorry`, no proof-plan preamble, and the model continues the fence itself).

**Everything in the CHECK-IN #2 section immediately below this notice — the floor table, the delta-
floor numbers, the per-seed breakdown, the seed-balance analysis, the contamination-subset work built
on top of it — was measured under the WRONG prompt template for every model in it (Base/SFT/RL of the
DeepSeek-Prover-V1.5 triple). It does not reflect these models' real capability and CANNOT be used for
any claim, discovery or null.** Not affected: Goedel-Prover-V2 and DeepSeek-Prover-V2-7B (Phases 1-7's
models) — both configs' own official prompt format IS textually `WholeProofTemplate`'s by design, so
the bug was a no-op for them; regression-tested and live-spot-checked 2026-07-06 (see PROGRESS.md).

Fixed in `src/atp/agents/whole_proof.py` (test-first — `test_from_config_resolves_the_configured_
prompt_template`, `tests/test_agents.py`), full battery RE-RUN under the now-genuinely-correct
templates — see the "CORRECTED CHECK-IN #2" section further down this file for the real numbers. The
section below is preserved as-is (not deleted) so the record stays honest about what happened and why
it doesn't count, per this project's append-only-history norm.

---

## CHECK-IN #2 (⚠️ INVALID — SEE CORRECTION ABOVE) — DeepSeek-Prover-V1.5 Base/SFT/RL matched-pair floor table

**Coverage at time of this table** (cells completed / target = problems x 3 seeds): ProofNet# (186
problems): Base 532/558 (95%), SFT 521/558 (93%), RL 245/558 (44%, all 3 seeds present: seed0=114,
seed1=70, seed2=61). miniF2F (244 problems): Base 610/732 (83%), SFT 551/732 (75%), **RL 132/732
(18%) — SEED-IMBALANCED: seed0=132, seed1=0, seed2=0.** Goedel-Prover-SFT: proofnet 23/558 (4%),
minif2f 0/732 — not ready, not included, per the coordinator's instruction not to block on it.

**Seed-balance check (done before trusting anything below)**: computed via
`scripts/phase8_floor_table.seed_balance_report` (any expected seed below 10% of its target while
another seed is present = flagged). Result: every triple cell passes EXCEPT RL-miniF2F, which fails
outright (seeds 1 and 2 are fully untouched — RL's miniF2F array started later than the other five and
hasn't caught up). **RL is therefore EXCLUDED from the miniF2F table below** — including it would bias
the comparison entirely toward whatever seed 0 happens to look like. RL-ProofNet# passes (all three
seeds present with a real, if uneven, 61-114 range) and IS included.

### ProofNet# (OOD) — the headline metric per atp-phase8-plan — full triple, common-completed-subset

Computed via `pass_at_b_on_common_subset`: for fairness, each seed's comparison is restricted to the
INTERSECTION of problem names all three stages have already completed for that seed (114/57/44 problems
for seeds 0/1/2 respectively — bounded by RL's slower coverage; this is a preliminary read on an
in-flight sweep, not final numbers, and will tighten as RL's coverage catches up).

| Stage | pass@2000 | pass@8000 | pass@32000 (**floor**) | per-seed @32000 |
|---|---|---|---|---|
| Base | 0.0 ± 0.0 | 0.0 ± 0.0 | **0.0 ± 0.0** | {0: 0.0, 1: 0.0, 2: 0.0} |
| SFT  | 0.9 ± 0.9 | 3.9 ± 1.8 | **5.2 ± 1.7** | {0: 5.3, 1: 3.5, 2: 6.8} |
| RL   | 2.8 ± 0.6 | 6.1 ± 0.8 | **8.9 ± 4.2** | {0: 7.9, 1: 5.3, 2: 13.6} |

**Delta-floor**: Base→SFT = **+5.2pp**; SFT→RL = **+3.7pp** (RL buys a further reduction beyond SFT,
not just re-deriving SFT's gain). Direction is consistent across all 3 seeds at every budget (RL >
SFT > Base in every single per-seed cell above, no exceptions) — this is NOT a single point estimate
carried by one lucky seed.

### miniF2F (in-distribution) — Base/SFT only, common-completed-subset (RL excluded, see above)

| Stage | pass@2000 | pass@8000 | pass@32000 (**floor**) | per-seed @32000 |
|---|---|---|---|---|
| Base | 0.5 ± 0.9 | 1.4 ± 0.3 | **6.0 ± 2.0** | {0: 3.8, 1: 6.6, 2: 7.7} |
| SFT  | 7.4 ± 1.7 | 11.0 ± 2.3 | **14.9 ± 2.4** | {0: 16.4, 1: 12.2, 2: 16.2} |

Base→SFT = **+8.9pp**, consistent across all 3 seeds. RL's miniF2F delta is simply unknown yet (not a
null — genuinely not measured) until its seed 1/2 shards catch up.

**Caveats (read before acting on this)**: (1) ProofNet# N is small per seed (44-114 problems, itself
a further-restricted intersection since RL is the slowest-covered stage) — numbers may shift as more
cells land, especially seed 2's 44-problem slice. (2) This is a preliminary read on an in-flight
sweep, not the final full-coverage numbers the plan calls for — recommend re-running this exact table
once RL reaches parity with Base/SFT's ~90%+ coverage before treating it as final. (3) The apples-to-
apples common-subset restriction assumes each stage's sweep processes cells in a similar order (so the
"first N% completed" isn't a biased sample per stage) — plausible given all three use the same sharding
scheme, but not independently verified. (4) No novel/contamination-audited split (same project-wide
gap noted at step 2) — this is on the RAW benchmark, contamination unaudited. (5) Goedel-Prover-SFT
not included; Cluster B breadth not started. **No headline call (discovery vs. definitive-negative)
is made here** — that's explicitly the coordinator's/user's read on the table above, per
atp-phase8-plan.

**GPU-h**: ~150.7 GPU-h summed across every shard in this whole Phase 8 battery effort since launch
(including the early failed/transient shards from the node-contention episode) — over the nominal
50 GPU-h line, logged per house rule (soft limit; the earlier two-model baseline was already granted
a similar exception when the spend bought a real finding).

Status: **check-in #1 COMPLETE** — the DeepSeek-Prover-V1.5 Base/SFT/RL triple is confirmed: all
three stages download, serve via vLLM, and round-trip through the reused Goedel-pin Lean REPL
(verifier correctly accepts/rejects). Not yet started: step 2 (common intersection eval set), step 3
(metric battery), matched-pair analysis — gated on the coordinator/user reviewing this check-in first.

## Triple GPU-smoke confirmation (2026-07-05, jobs 11117217/218/219/221)

| Stage | vLLM load | Lean round-trip | pass@2000 (n=2 smoke) | Notes |
|---|---|---|---|---|
| DeepSeek-Prover-V1.5-Base | OK | OK | 0.000 ± 0.000 | clean first-try |
| DeepSeek-Prover-V1.5-SFT | OK (2nd attempt) | OK | 0.500 ± 0.000 | 1st attempt (job 11117218) got a spurious 404 `model does not exist` — co-located with the Base job on the same node (ins094), both defaulting to port 8000, the same collision failure mode already documented in slurm/sweep_array.sh's comments; NOT a pin/model problem. Reran alone (job 11117221) with a clean result. |
| DeepSeek-Prover-V1.5-RL | OK | OK | 0.500 ± 0.000 | clean first-try |

All three used `HF_HUB_OFFLINE=1` against weights cached in `scratch/hf-cache` (13GB each, ~39GB
total), the reused `atp-lean-env` (Goedel pin, v4.9.0-rc1), and the raw-completion prompt format
(no chat template) confirmed identical across all three stages. GPU-h spent: ~15.5 GPU-minutes total
across 4 jobs (~0.26 GPU-h) — negligible.

**Disk:** downloading the triple used ~39GB. Note for future sessions: `df -h /insomnia001`
(queried at the mountpoint) reports the true cluster-wide filesystem (1.7P total, 675T free, 60%
used) — NOT tight. The binding constraint is a **per-fileset quota on the COMS-E6998-012 department
allocation** (5.0T quota, visible via `df -h .` from inside the project or any path under
`/insomnia001/depts/edu/COMS-E6998-012/`), currently at **34G free** after this download. This quota
is shared across ALL projects under that department path (Mixture-of-Prompts, continual_alignment,
clmm-project, theorem-proving-research, atp-budget-study), not just this repo, so future headroom
decisions should check `df -h .` from within the project (the fileset view), not the mountpoint.

## Working model list (Cluster A)

| Model | HF repo | Revision (pinned 2026-07-05) | Lean env | Prompt template | Status |
|---|---|---|---|---|---|
| DeepSeek-Prover-V1.5-Base | deepseek-ai/DeepSeek-Prover-V1.5-Base | `0b260a2d` | **Goedel pin** (base.yaml) | `deepseek_v15` | pin+format confirmed via GH; Lean-side smoke passed; vLLM load blocked (weights not cached, see below) |
| DeepSeek-Prover-V1.5-SFT | deepseek-ai/DeepSeek-Prover-V1.5-SFT | `e9a6e6fb` | **Goedel pin** | `deepseek_v15` | same |
| DeepSeek-Prover-V1.5-RL | deepseek-ai/DeepSeek-Prover-V1.5-RL | `40a76013` | **Goedel pin** | `deepseek_v15` | same (Lean-stage job cancelled before vLLM step to avoid the same failure) |
| Goedel-Prover-SFT | Goedel-LM/Goedel-Prover-SFT | `5b03a13d` | **Goedel pin** | `goedel_sft` | pin+format confirmed via GH; not yet GPU-smoked |
| DeepSeek-Prover-V2-7B | deepseek-ai/DeepSeek-Prover-V2-7B | `a8d9e144` (existing) | deepseek-lean-env (existing) | `whole_proof` | already pinned/running since Phase 2 — zoo reuses as-is, no new work |
| BFS-Prover-V1-7B | ByteDance-Seed/BFS-Prover-V1-7B | `750e3903` (existing) | Goedel pin (existing) | `bfs_prover` | already pinned/running since Phase 7 — zoo reuses as-is |
| STP | kfdong/STP_model_Lean | `63a78b9e` | Goedel pin (**inferred**, not GH-confirmed) | `deepseek_v15` (**inferred**) | best-evidence default; needs the contract-test smoke before trusting for a real sweep |
| Leanabell-Prover-GD-RL | stoney0062/Leanabell-Prover-GD-RL | — | **unresolved** | — | **FLAGGED, not pinned**: empty HF model card, no locatable GitHub/paper — see below |
| Leanabell-Prover-V2-DS | stoney0062/Leanabell-Prover-V2-DS | — | **unresolved** | — | same flag |

## The centerpiece: DeepSeek-Prover-V1.5 Base/SFT/RL triple

**Pin + format: CONFIRMED** (paper-level, via GitHub API, not assumed):
- All three stages' GitHub repo (`deepseek-ai/DeepSeek-Prover-V1.5`) pins mathlib4 at
  `xinhjBrant/mathlib4@2f65ba7f1a9144b20c8e7358513548e317d26de1` — the **same commit as Goedel's
  pin** in this repo's base.yaml (`leanprover/lean4:v4.9.0-rc1`), confirmed by fetching that commit's
  own `lean-toolchain` file. This CORRECTS the Phase 8 plan's assumption that the triple shares
  DeepSeek-Prover-V2's (different, later, standard-mathlib) pin — see DECISIONS.md 2026-07-05.
- Prompt format verified against the family's own `quick_start.py`: raw completion (no chat
  template, no proof-plan preamble). All three stages share it (no per-stage documented deviation).
  `max_position_embeddings=4096` for all three (config.json).

**Loads via vLLM: NOT YET CONFIRMED** — a GPU smoke was attempted (job 11116337/338/339, single
shard each) and got as far as: env activation OK, Lean env staged/reused OK, the trivial-true /
norm_num / false-rejection probe all passed cleanly on the (reused, already-built) Goedel pin —
direct runtime evidence the pin finding above is correct. vLLM itself failed to start
(`ValueError: Invalid repository ID or local directory specified`) because none of these 5 new
models have ever been downloaded to `scratch/hf-cache`, and `slurm/sweep_array.sh` defaults
`HF_HUB_OFFLINE=1` (serve only from a pre-staged cache, per CLAUDE.md storage hygiene — never
trigger a live download inside a Slurm job).

**Blocked on a shared-resource decision, not a technical one:** `df -h /insomnia001` reads 99% used,
58G free — for the WHOLE shared cluster mount, not a per-user quota. The triple's weights are
~13.8GB each (~41.5GB total, HF API blob sizes) — downloading them would consume the large majority
of the remaining shared headroom. Stopped here rather than deciding unilaterally; see
PROGRESS.md/DECISIONS.md 2026-07-05 for the options laid out for the user. GPU-h spent so far on
this whole check-in: negligible (~2-3 min x 2 nodes before jobs were cancelled).

## Contract-test methodology (for the record, reusable for Cluster B / STP / Leanabell if pinned)

Reuses the existing Lean-pin smoke embedded in `slurm/sweep_array.sh` (trivial-true accept,
norm_num accept, false-proof reject) — this already ran cleanly against the Goedel pin for all 3
triple-stage smoke attempts. The remaining "contract test" once weights are cached is simply: run
the tiny smoke config (`configs/deepseek_v15_{base,sft,rl}_smoke.yaml`, 2 miniF2F problems, budget
2000, seed 0) end-to-end and confirm at least one real proof attempt round-trips through
`DeepSeekV15Template` -> vLLM -> Lean REPL without an infra error (sorry/admit correctly rejected by
the existing `reject_loopholes` config, already exercised by every prior phase's baseline).

## Leanabell models — why they're flagged, not pinned

`stoney0062/Leanabell-Prover-{GD-RL,V2-DS}` (and their DS-SFT/GD-SFT/V2-KM siblings) have **no HF
model card content at all** (empty README, `cardData: null`) and no `arxiv`/GitHub link findable via
a GitHub repository search or HF search API pass. Their `config.json` shows a bare LLaMA-architecture
checkpoint from an internal path (`/mmu_nlp_hdd/jixingguang/...`) with no public provenance. Pinning
a Lean/mathlib env by NAME GUESS (rather than verified evidence, this project's repeated failure
mode — see the Mode 3/4 confound history in DECISIONS.md) is exactly the mistake this triage step
exists to avoid. Recommendation: drop from Cluster A's near-term critical path (the causal core — the
V1.5 triple + Goedel-Prover-SFT — doesn't need them) and revisit only if a paper/repo surfaces, or
accept the cost of a blind empirical pin-probe as a deliberate, logged choice.

## CHECK-IN #2 FOLLOW-UP (2026-07-06, ⚠️ ALSO INVALID) — coordinator review: "directionally promising, not clean enough"

**⚠️ Everything in this section is ALSO invalid, for the same reason as the check-in #2 table above**:
the "Updated V1.5 triple floor table" below was rebuilt from the SAME wrong-template runs (just with
better seed coverage), so it inherits the exact same defect. The Leanabell 0%-everywhere finding
reported further down turned out to have TWO layered causes, not one: the whole_proof/chat_completions
prompt choice was a real, independent problem (see its own writeup below), but the SUBSEQUENT "fix"
(switching Leanabell to the goedel_sft raw-completion template) also silently failed to take effect
for the exact same reason as the triple — `from_config` was still hardcoding `WholeProofTemplate`
regardless of the config change. Re-verified this directly: the smoke re-run after the config fix
produced byte-identical output to the pre-fix run, which is what led to discovering the wiring bug
itself (see PROGRESS.md 2026-07-06 for the full trace). Everything here is preserved for the record,
not deleted — see the "CORRECTED CHECK-IN #2" section further down for the real numbers from both
pairs, now measured under templates that are actually wired correctly.

Coordinator reviewed the check-in #2 floor table (consistent Base<SFT<RL at every budget/seed) and
withheld the headline verdict pending 4 items. **No headline verdict is written here** — that stays
the coordinator's/user's call. This section reports what changed against each of the 4 items.

### 1. Second matched pair: Leanabell-Prover-GD-SFT -> GD-RL — PIN-TRIAGE PASSED, battery LAUNCHED

**Correction to check-in #1's finding.** ZOO.md previously said Leanabell had "no locatable
GitHub/paper." That was wrong — a GitHub search for the repo name "Leanabell-Prover" (not just
"Leanabell-Prover-GD-RL") surfaces `Leanabell-LM/Leanabell-Prover`, a public paper
([arXiv:2504.06122](https://arxiv.org/abs/2504.06122)), and an HF collection with an eval table. The
earlier search was incomplete, not a real dead end. Logged in PROGRESS.md/DECISIONS.md.

**Lineage (from the paper's own README, quoted directly)**: "Leanabell-Prover-GD-SFT/GD-RL" continual-
trains from **Goedel-Prover-SFT** ("GD" = Goedel lineage; "DS" siblings start from DeepSeek-Prover-V1.5
instead) with a hybrid statement-proof + "cognitive behavior" dataset, THEN applies RL against the Lean
compiler's outcome reward. GD-SFT is GD-RL's own base checkpoint (the continual-trained model prior to
the RL stage) — this is the tighter, single-variable RL delta than comparing GD-RL against plain
Goedel-Prover-SFT (one stage further upstream) would be, so GD-SFT -> GD-RL is the pair built here, not
Goedel-Prover-SFT -> GD-RL.

**Pin**: NOT independently GH-confirmed (the `Leanabell-Prover` GitHub repo has README + figures only,
"Setup Environment: TODO" — no code, no `.gitmodules`). Best-evidence default (same class of inference
as `configs/stp_proofnet.yaml`'s already-accepted precedent): reuses the Goedel pin unchanged, since
the paper explicitly continual-trains from Goedel-Prover-SFT and its eval table lists Goedel-Prover-
SFT/DeepSeek-Prover-V1.5/STP side-by-side with directly comparable pass@B numbers — consistent with
this whole research lineage sharing one mathlib fork+commit (independently confirmed for 3 other
papers already in this repo). **Not proven** — flagged in configs and here.

**Prompt format**: also inferred, not GH-confirmed. Chose `whole_proof` (proof-plan preamble,
chat_completions) over the raw-completion V1.5/Goedel-SFT style based on concrete architecture signals:
`max_position_embeddings=8192` (2x the raw-completion models' 4096), a REAL chat_template in the HF
tokenizer_config (DeepSeek-Coder Instruction/Response style — absent on the raw-completion models), and
the paper's own framing ("cognitive behaviors that emulate human reasoning... align with breakthroughs
in reasoning models"). **Contract-tested, not just guessed**: GPU smoke (jobs 11182484/11182485) on
both GD-SFT and GD-RL — vLLM loads, Lean round-trip clean, and the completions are COHERENT Lean
tactic code (`simp_all`, `norm_num`, `ring_nf`, `intro`, `have` — legitimate mathlib tactics) inside a
proof-plan preamble, correctly rejected by the verifier when incomplete/truncated — not garbage, same
bar Goedel-SFT passed at check-in #1. (Observed: at the tiny smoke budget (2000 tokens total, shared
across ~20-30 refinement/propose attempts), completions truncate well short of a full proof — expected
for a reasoning-style model at a token-starved budget, not a bug: Goedel-Prover-V2, the OTHER
`whole_proof`/chat_completions reasoning model already in this repo, also has a modest pass@2000
(29.6%) for the same reason. The real battery's 8k/32k tiers give proportionally more room.)

**Battery**: launched at 2k/8k/32k (capped to match the V1.5 triple's own cap — coordinator-approved
scope 2026-07-06; the literally-requested 128k tier was estimated at 300+ incremental GPU-h using this
repo's own documented cost baseline, well over the 50-GPU-h ask-first line, so capping keeps the two
pairs apples-to-apples at the same budget ceiling AND keeps cost bounded). Jobs 11187267-11187270 (4
configs = GD-SFT/GD-RL x ProofNet#/miniF2F, 3 seeds each), `--exclude=ins082,ins091` (the two nodes
diagnosed as the check-in #2-era contention source) from the start. **Still in flight at the time of
this writeup — no real numbers for the second pair yet.** Will report once coverage is real.

### 2. RL-ProofNet# seed coverage — RESOLVED, now well-balanced

The sweep kept running in the background and self-healed past the earlier node-contention episode:
RL-ProofNet# is now 140/140/139 per seed (419/558, 75%), RL-miniF2F is now 213/214/213 (640/732, 87%)
— both comfortably pass `scripts/phase8_floor_table.seed_balance_report` (no seed near the ~10%-of-
target floor that flags imbalance). **RL-miniF2F is no longer excluded** — it's included in the
updated table below. Base/SFT/Goedel-SFT all also improved (Goedel-SFT-miniF2F is now fully complete,
732/732).

### Updated V1.5 triple floor table (both benchmarks, all 3 stages, full seed balance)

Common-completed-subset methodology unchanged from check-in #2 (restrict each seed's comparison to
problem names all 3 stages have completed for that seed — coverage is higher now so N per seed is
larger too).

**ProofNet# (OOD)** — common subset 140/140/139 problems/seed:

| Stage | pass@2000 | pass@8000 | pass@32000 (floor) | per-seed @32000 |
|---|---|---|---|---|
| Base | 0.2±0.4 | 0.2±0.4 | **0.7±0.7** | {0: 0.7, 1: 1.4, 2: 0.0} |
| SFT  | 1.6±0.4 | 3.6±1.5 | **4.1±1.1** | {0: 5.0, 1: 2.9, 2: 4.3} |
| RL   | 2.9±0.7 | 5.0±0.7 | **6.2±1.6** | {0: 7.1, 1: 4.3, 2: 7.2} |

Delta-floor: Base→SFT +3.4pp, SFT→RL +2.1pp. Base<SFT<RL holds in all 3 seeds, no exceptions.

**miniF2F (in-distribution)** — common subset 152/151/150 problems/seed, **RL now included**:

| Stage | pass@2000 | pass@8000 | pass@32000 (floor) | per-seed @32000 |
|---|---|---|---|---|
| Base | 0.2±0.4 | 1.3±0.0 | **4.8±2.0** | {0: 2.6, 1: 6.6, 2: 5.3} |
| SFT  | 7.3±1.7 | 10.2±3.1 | **13.7±1.6** | {0: 15.1, 1: 13.9, 2: 12.0} |
| RL   | 10.6±1.7 | 15.2±3.4 | **19.0±3.5** | {0: 23.0, 1: 16.6, 2: 17.3} |

Delta-floor: Base→SFT +8.9pp, SFT→RL +5.3pp. Base<SFT<RL holds in all 3 seeds, no exceptions. This is
a stronger, better-powered version of the same pattern from the original check-in #2 table.

### 3. Contamination-noted subset — partial, honestly limited by what's checkable

**What WAS checked** (mechanical, from data already in this repo — see `scripts/phase8_contamination.py`,
7 tests in `tests/test_phase8_contamination.py`):

- **miniF2F valid/test split-leak check**: exact-name overlap between the vendored miniF2F `valid`
  and `test` splits = **0/244** (clean). This matters because this whole prover lineage's RL/expert-
  iteration stages are documented as training against miniF2F-*valid* — a valid/test name collision
  would be a direct, concrete leak into the reported "test" floor. No such leak found in this repo's
  copy.
- **ProofNet# source breakdown**: 180/186 problems are named textbook exercises (Dummit&Foote 44,
  Munkres 30, Rudin 29, Herstein 24, Artin 14, Axler 14, Ireland&Rosen 10, Shakarchi 8, Pugh 7) + 6
  Putnam competition problems. Textbook exercise banks are this exact field's standard synthetic-
  training-data source pool (DeepSeek-Prover-V1.5/Goedel-Prover/Leanabell-Prover papers all describe
  synthesizing SFT/RL training data from textbook-style statements) — so the textbook-named majority
  of ProofNet# carries a real, plausible train-overlap risk specifically for these labs' models, not
  just generic web contamination. The 6 Putnam problems are the best available lower-risk subset (not
  the field's textbook-synthesis source pool) — **still not zero-risk** (Putnam solutions are public
  online too, and web-pretraining contamination would apply about equally to Base, so isn't obviously
  RL-differential) but the closest thing to a flagged-clean slice available without the labs' actual
  training manifests.

**Recomputed on the low-risk (Putnam-only) subset**: N collapses to 4-6 problems/seed (18/18/14 total
cells across the 3 stages at budget 32k) — **and 0/18, 0/18, 0/14 solved at 32k for Base/SFT/RL
respectively.** This subset is simultaneously too small AND too hard at this budget for any model to
solve anything — it is **uninformative**, not a confirmation of either direction. It cannot be used to
say whether removing textbook-adjacent problems changes the delta-floor's direction or magnitude.

**What was NOT checked, and can't be from this position**: whether Leanabell/DeepSeek/Goedel's actual
private RL training corpora contain problems textually identical or near-identical to specific
ProofNet#/miniF2F test items. That would require the labs' training-data manifests, which aren't
public for the RL stages. **This remains an open, unresolved alternative explanation for the SFT→RL
delta specifically** (does RL training see more benchmark-adjacent statements than SFT training did?
Unknown) — it is not ruled out by anything done here, only bounded: the one mechanical leak check
available (miniF2F split) came back clean, and the field-standard-contamination concern (ProofNet#'s
textbook makeup) applies to the whole benchmark's exercise pool, not something a same-repo analysis
can isolate to RL specifically without the training data.

### 4. Stage C (Phase 6) vs Phase 8 — reconciling the apparent contradiction

**Stage C** (`results/phase6/STAGE_C_RESULT.md`, 2026-07-05): a GRPO LoRA (r=16) RL probe on
DeepSeek-Prover-V2-7B, starting from an already-capable base, training directly against the Lean
verifier's outcome reward for 80 steps on a 130-problem `lean_workbook_clean` subset. **Result: c2,
capacity ceiling.** Held-out pass@1 went base 0.586 → RL-final 0.570 (Δ=**-1.6pp**, G1 failed);
training reward was flat for all 80 steps (no upward trend); G2 (soundness) and G3 (no collapse) both
passed cleanly — this was a clean null, not a mis-tuned stall. RL (as scoped: LoRA, lightweight,
post-hoc, applied AFTER the model already existed) did not move the floor.

**Phase 8** (this check-in): the DeepSeek-Prover-V1.5 Base→SFT→RL triple and (pending) the Leanabell
GD-SFT→GD-RL pair are lab-trained, **full-pipeline** RL — RL integrated into the original training
recipe, starting from a dedicated SFT checkpoint, at whatever scale/duration/reward-shaping the lab
used (typically far more steps, more diverse training data, and full or near-full parameter updates,
not a 16-rank LoRA probe). **Result: RL-trained checkpoints show a consistently lower floor than their
SFT siblings**, direction stable across every seed and budget measured so far.

**These are not the same experiment, and the surface-level "RL moves the floor / RL doesn't move the
floor" framing is not well-posed** — they differ on at least three axes: (a) LoRA r=16 vs full/near-full
fine-tuning, (b) ~80 steps on 130 problems vs a full lab-scale RL training run, (c) a post-hoc nudge
applied to an existing model vs RL integrated into the original training pipeline from a dedicated SFT
base. **Working hypothesis this data supports** (not a proven claim): full-pipeline RL training, at lab
scale, integrated into the original recipe, lowers the execution floor in a way that a lightweight,
post-hoc, LoRA-scale RL nudge cannot reproduce. This sharpens Stage C's null rather than contradicting
it — Stage C rules out "just bolt on a cheap RL nudge," it does not rule out "RL integrated into the
full training pipeline from the start." Whether it's the scale, the integration-from-base, the training
duration, or the reward-shaping that actually matters remains open; distinguishing between these is
future work, not something either experiment alone answers.

**No headline verdict (discovery vs. definitive-negative) is written here.** That is explicitly the
coordinator's/user's call, pending the second pair's real coverage.

---

## ⚠️ 2026-07-06/07 SECOND CORRECTION — the section above is ALSO invalid (assembly bug, not a wiring bug)

The "Updated V1.5 triple floor table" and the Leanabell pair numbers immediately above were rebuilt
under the CORRECT template (the wiring bug was genuinely fixed by this point) — but a SEPARATE,
independent bug made them invalid too: `PantographBackend._build_source` / `ReplBackend.
_build_repl_source` (the ACTUAL backend `eval/run.py` uses) never reconstructed the `theorem ... :=
by` declaration for continuation-style completions (`DeepSeekV15Template`/`GoedelSFTTemplate` ask the
model to continue directly after `:= by`, never restating the theorem) — bare tactics landed as
top-level commands, a guaranteed Lean parse error dressed up as "the model's proof was wrong." Found
by hand-tracing individual examples byte-for-byte (not guessing) after a `WholeProofTemplate`-vs-
these-templates format contradiction was too large to ignore. Fixed, test-first, 2026-07-06 (see
PROGRESS.md/DECISIONS.md that date). **A THIRD bug was found the same day**: both templates were also
missing `import Aesop` + `set_option maxHeartbeats 0` (verified byte-for-byte against
`quick_start.py`/`eval/step1_inference.py`) — the latter disables Lean's elaboration heartbeat limit;
without it, otherwise-valid nlinarith/field_simp/simp-heavy proofs can spuriously fail to elaborate in
time. Also fixed, test-first, same date.

**A fourth candidate was investigated and explicitly NOT adopted at scale**: `informal_statement`
(present for 242/244 miniF2F problems) was silently dropped at `Problem.to_theorem()` and never
rendered as the `/-- ... -/` doc-comment both official sources include. Fixed in code (tested,
correct) and smoke-tested at increasing scale (29 cells, then an expanded 160-cell smoke across
SFT+RL × miniF2F+ProofNet#) — completions became modestly longer (median 33→48 tokens) and
qualitatively more coherent on spot-checks, but **0/160 solved**, no dramatic shift. Per a pre-
committed decision rule, this lead was NOT pursued further or scaled to a real re-run — see
PROGRESS.md 2026-07-07.

## CORRECTED CHECK-IN #2 (2026-07-07) — the real numbers, after 3 independent bugs fixed

**History of every invalid attempt, kept for the record, none deleted:**

| Attempt | What was measured | Root cause once found | Status |
|---|---|---|---|
| 1st check-in #2 table (above, first section) | V1.5 triple under the WRONG template | `WholeProofAgent.from_config` hardcoded `WholeProofTemplate`, ignoring `config.model.prompt_template` entirely | ⚠️ INVALID — wrong prompt |
| 1st Leanabell attempt (whole_proof/chat) | Leanabell GD-SFT/GD-RL under a guessed reasoning-style prompt | Wrong template choice (not the wiring bug — chosen before the bug was found) | ⚠️ INVALID — wrong prompt (separate mistake) |
| 2nd Leanabell attempt (goedel_sft) | Same models, "corrected" template | The SAME wiring bug (template never actually took effect) — this is what led to discovering it | ⚠️ INVALID — wiring bug, unknowingly |
| 2nd check-in #2 table (`p8battery2_*`, wiring bug fixed) | V1.5 triple + Leanabell pair, correct template, wiring fixed | Missing-theorem-header assembly bug in BOTH `PantographBackend`/`ReplBackend` | ⚠️ INVALID — assembly bug |
| Re-verify pass v1 (maxHeartbeats NOT yet fixed) | Same completions, assembly bug fixed | Missing `import Aesop`/`set_option maxHeartbeats 0` | ⚠️ INVALID — header bug |
| **`p8battery2_verified2_*` (this section)** | Same completions, ALL THREE bugs fixed | — | **✅ Current best data** |

**Coverage** (all seed-balance-checked, `scripts/phase8_floor_table.seed_balance_report`, no
imbalance flagged on any of the 10 configs):

| Config | Cells | Coverage |
|---|---|---|
| V1.5 Base — ProofNet# | 558/558 | 100% |
| V1.5 Base — miniF2F | 457/732 | 62% |
| V1.5 SFT — ProofNet# | 558/558 | 100% |
| V1.5 SFT — miniF2F | 732/732 | 100% |
| V1.5 RL — ProofNet# | 488/558 | 87% |
| V1.5 RL — miniF2F | 732/732 | 100% |
| Leanabell GD-SFT — ProofNet# | 349/558 | 63% |
| Leanabell GD-SFT — miniF2F | 366/732 | 50% |
| Leanabell GD-RL — ProofNet# | 348/558 | 62% |
| Leanabell GD-RL — miniF2F | 490/732 | 67% |

**The result, computed identically to every prior floor table (`pass_at_b_on_common_subset`,
common-completed-subset per seed):**

| | ProofNet# floor (pass@32000) | miniF2F floor (pass@32000) |
|---|---|---|
| V1.5 Base | **0.0 ± 0.0** | **0.0 ± 0.0** |
| V1.5 SFT | **0.0 ± 0.0** | **0.0 ± 0.0** |
| V1.5 RL | **0.0 ± 0.0** | **0.0 ± 0.0** |
| Leanabell GD-SFT | **0.0 ± 0.0** | **0.0 ± 0.0** |
| Leanabell GD-RL | **0.0 ± 0.0** | **0.0 ± 0.0** |

**Every single cell across both pairs, both benchmarks, every budget (2000/8000/32000), across
5,586 real re-verified cells: zero solves.** This is not a partial or noisy result — it is exact and
comprehensive (confirmed directly, not inferred: `solved=True` count is 0 in every one of the 10
run dirs). The "clean, consistent Base<SFT<RL" pattern reported at the very first check-in #2 has
**completely evaporated** — it was entirely an artifact of the wiring bug (every model measured under
`WholeProofTemplate`'s prompt regardless of its own config) and does not survive correction.

### Replication verdict — Leanabell pair vs. V1.5 triple

**Clean replication — of a null.** Both independent lineages (DeepSeek-Prover-V1.5's Base→SFT→RL and
Goedel-Prover's GD-SFT→GD-RL) agree exactly: 0.0±0.0 at every stage, every benchmark, every budget.
There is no RL-vs-SFT delta to compare in either lineage — nothing solves anything, so there is
nothing for RL to differentially improve over SFT (or SFT over Base). The two pairs replicate each
other perfectly in the sense that they produce the IDENTICAL (degenerate) result, but this is not a
replication of the original "RL lowers the floor" finding — that finding is gone. **No headline
verdict (discovery vs. definitive-negative) is made here** — per the plan, that call is the
coordinator's/user's, informed by this corrected table.

### Contamination-noted subset (step 3 from check-in #2) — now moot, not just superseded

The original contamination analysis asked whether textbook-exercise overlap could explain the RL-
specific solve-rate BUMP seen in the (invalid) earlier tables. With the corrected floor at 0.0±0.0 for
every stage, **there is no bump left to explain** — the contamination question was conditional on a
finding that no longer exists. The mechanical checks done then (miniF2F valid/test split-leak = clean;
ProofNet# is 180/186 named-textbook exercises + 6 Putnam) are still factually true and remain useful
background for any FUTURE positive finding in this benchmark pair, but they no longer bear on a
result that has since disappeared. Not re-doing that analysis against a 0% floor — there's nothing to
contaminate.

### Stage C (Phase 6) vs. Phase 8 reconciliation — reframed by the correction

The original reconciliation (still above, preserved) framed Stage C's LoRA-GRPO null against what
looked like a genuine full-pipeline-RL floor reduction in Phase 8, proposing "full-pipeline RL lowers
the floor in a way lightweight RL can't" as the working hypothesis. **That asymmetry is gone.** Phase
8's corrected numbers now show NO floor movement from RL either — full-pipeline, lab-scale,
integrated-from-base RL (the V1.5 and Leanabell RL stages) moves the floor by exactly as much as
Stage C's lightweight LoRA nudge did: nothing. Reframed, this is now a **fourth independent
confirmation** of the project's broader execution-floor thesis (Phases 0-5: scaffolding/search/
hammers/reinvestment don't move it; Phase 6 Stage B: SFT-style closing-likelihood maximization doesn't
move it, revealing the exposure-bias signature instead; Phase 6 Stage C: direct outcome-reward RL,
LoRA-scale, doesn't move it; **Phase 8, corrected: full-pipeline, lab-scale RL — across two
independent training lineages — also doesn't move it**), not evidence of a scale-dependent RL effect.
The "full-pipeline vs. lightweight RL" distinction proposed in the earlier (invalid) reconciliation
is no longer needed — both regimes now point the same way.

**No headline verdict is written here.** That is still explicitly the coordinator's/user's call.

---

## HARNESS-SANITY CONTROL + FINAL PRE-SYNTHESIS CHECKS (2026-07-09/10)

Given "three first-commit bugs, then a perfect 0.0% everywhere" is itself a suspicious pattern (real
capability floors are usually noisy-near-zero, not exactly zero — perfect zeros are the classic
signature of a scoring pipeline that isn't scoring anything), the coordinator required a hard blocking
control before accepting the corrected floor. Four checks, all now closed:

**1. Harness-sanity control — PASSED.** Sampled cells Goedel-Prover-V2/DeepSeek-Prover-V2-7B
(confirmed unaffected by all 3 bugs — their native format IS `WholeProofTemplate`) had historically
recorded as `solved=True`, re-verified ONLY the recorded solving proof against the CURRENT fully-
patched backend. **DeepSeek-Prover-V2-7B: 40/40 still verify as `ok`. Goedel-Prover-V2: 37/37 still
verify as `ok`.** The exact backend code that produced Phase 8's 0.0% floor correctly recognizes real,
known-good proofs as solved — the pipeline is sound; the 0.0% is not a scoring artifact. (Caught 2
bugs in the control-check TOOLING itself before trusting it — wrong Lean env staged for DeepSeek-V2,
and a crash on a pre-existing corrupt checkpoint file — both fixed test-first, see DECISIONS.md
2026-07-09/10; neither touches `atp`'s production package.)

**2. Taint audit — zero Phase 0-7 results affected.** Every committed headline result (Phase 1
FINDINGS.md, Phase 2 MECHANISM.md, Phase 3 HAMMER_PROBE.md, Phase 4 ALLOCATION.md — the compute-
optimal positive result, Phase 6 FINETUNE.md/STAGE_C_RESULT.md, Phase 7 STEPWISE.md) used ONLY
Goedel-Prover-V2-8B and/or DeepSeek-Prover-V2-7B, both natively `whole_proof` — unaffected by the
wiring bug regardless of it existing. Phase 7's tactic-stepwise mode uses a wholly separate agent
class (`TacticStepwiseAgent`) that was never routed through the buggy `WholeProofAgent.from_config` in
the first place. `BFS-Prover-V1-7B`/`STP` configs exist (pin-triaged, non-default templates) but were
never actually swept — no committed data to taint. The wiring bug's blast radius is fully contained to
Phase 8, which is the only phase this whole investigation has been re-working.

**3. `client.py` stop-sequence gap — real, but does not explain the 0.0% floor.** Confirmed no
template/config ever sets a `stop` sequence. Investigated concretely (not dismissed): scanned
attempts for "genuine trailing content after a real closing fence" — the one way this gap could mask
a hidden correct solve. DeepSeek-V1.5-Base's cases (32% of attempts) have LEADING garbage that already
breaks parsing before the trailing content is reached. Leanabell's cases (11-15%) show the model
hallucinating analysis of a DIFFERENT, unrelated theorem before ever opening a fence — genuine
confusion, not a real solve hidden behind bad extraction. Zero such cases in the most carefully-traced
configs (V1.5 SFT-ProofNet#, RL-miniF2F). Verdict: real efficiency/quality debt for any future
regeneration, does not retroactively change the current corrected floor.

**4. Cluster B breadth — formally dropped.** RL is closed via two clean, mutually-agreeing matched
lineages through a now-verified-sound harness; more models (STP, other Leanabell siblings) would add
breadth to an established negative, not new information.

**Final coverage** (gdrl_minif2f re-verify continued past its original session limit; current best):
V1.5 triple unchanged from the corrected table above (100/62/100/100/87/100% across the 6 cells).
Leanabell GD-RL-miniF2F now at 541/732 (74%, up from 490/732), seed-balanced (179/179/178/181ish,
`is_badly_imbalanced=False`), still 0/541 solved — consistent with every other cell.

**All four gates clear. The 0.0%-everywhere corrected floor table stands as the real, harness-
validated result for both matched lineages.** Proceeding to `SYNTHESIS.md` (internal, ties Phases 0-8
together) — the discovery-vs-definitive-negative headline call, and any paper-vs-internal framing
decision, remain explicitly the coordinator's/user's, not made here.
