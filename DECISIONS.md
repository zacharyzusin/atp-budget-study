# DECISIONS.md

Append-only log of design decisions. One entry per decision: date, decision, one-line rationale.
Never edit or delete past entries — supersede with a new dated entry if you change your mind.

---

### 2026-06-04 — Budget unit = LLM-generated tokens
Per-problem compute budget `B` is measured in total generation tokens summed across all model calls
(proposals, refinements, tactic steps). Rationale: reproducible across GPU types in a way wall-clock
is not. We also log wall-clock + GPU-hours for cross-checking, but **report** against token budget.
(Revisit if the team prefers GPU-seconds; it's a localized change in `src/atp/budget/`.)

### 2026-06-04 — Headline metric = pass@B curve, not pass@k
Report fraction solved within fixed budget `B`, as a curve over several `B` (e.g. 2k/8k/32k/128k
tokens), ≥3 seeds, mean±std. Rationale: this is the honest, novel axis for compute-constrained groups
and the framing that differentiates us from frontier pass@(thousands) results.

### 2026-06-04 — Base models: Goedel-Prover-V2-8B (primary) + BFS-Prover-V1-7B (tactic comparator)
Both open-weight and runnable/fine-tunable on our cluster. Goedel for whole-proof generation,
BFS-Prover for the tactic-level search axis in Phase 1. Rationale: strongest open small provers; lets
us study generation-mode crossover without training a prover from scratch.

### 2026-06-04 — Inference via persistent vLLM server; agent talks over HTTP
Decouples serving from agent logic, enables clean token accounting and throughput. Serve on l40s,
agent runs as separate (possibly CPU-light) process reading the endpoint from
`results/_vllm_endpoint.txt`.

### 2026-06-04 — Benchmarks: audited miniF2F + ProofNet#, with a novel/held-out split
Use corrected/audited splits and drop known-unprovable miniF2F items. Lead headline claims with the
novel split to mitigate contamination. Rationale: standard benchmarks are buggy and contamination is a
real reviewer concern.

### 2026-06-04 — Network confirmed available on compute nodes
Compute nodes have outbound access, so model/data download can happen in-job. Still set `HF_HOME` to
`scratch/hf-cache` so we don't re-download across jobs.

### TODO (decide in Task 0.2, then log here)
- [ ] **mathlib commit** and **Lean toolchain version** to pin (lock day one; record exact hashes).
- [ ] Training stack for Phase 2: TRL vs minimal GRPO (decide at Phase 2 start).

---

### 2026-06-04 — Config system = pydantic v2 (not OmegaConf) — RESOLVES Task 0.1 TODO
`src/atp/config.py` defines typed pydantic models mirroring `configs/base.yaml`, with
`extra="forbid"` so a typo'd or misplaced key fails loudly at load time (caught by a unit test).
Loader handles `defaults: base` by deep-merging the override onto the base config, then validating.
Rationale: typed validation + clear error messages + lossless round-trip (`load->dump->load`) matter
more here than OmegaConf's interpolation; one fewer dependency. `omegaconf` dropped from deps.

### 2026-06-04 — Dependency install split into LIGHT CORE (now) vs HEAVY GPU/LEAN (deferred)
Shared filesystem `/insomnia001` is at **100% (only ~20 GB free on the 5 TB mount)**. A full
`torch`+`vllm`+`lean-dojo` install (~10–15 GB) risks failing mid-install and starving other users on
this department space. So Task 0.1 installs only the light core needed for the fast suite + tooling
(env footprint **580 MB**); `torch/vllm/transformers/datasets` → `[gpu]`, `lean-dojo` → `[lean]`,
`trl/peft` → `[train]` optional groups, pinned when first installed (Task 0.2/0.3). **Flagged to the
team; awaiting go-ahead on the heavy install / disk cleanup before Task 0.2's Lean build.**

### 2026-06-04 — Light-core pinned versions (frozen on Insomnia, python 3.11.15)
pydantic==2.13.4 · pydantic-core==2.46.4 · PyYAML==6.0.3 · numpy==2.4.6 · pandas==3.0.3 ·
matplotlib==3.10.9 · rank-bm25==0.2.2 · tenacity==9.1.4 · openai==2.41.0 · huggingface-hub==1.17.0 ·
pytest==9.0.3 · pytest-timeout==2.4.0 · ruff==0.15.16 · setuptools==82.0.1. Recorded in
`pyproject.toml` `dependencies`. Rationale: reproducibility rule — exact pins, no floating ranges.

### 2026-06-04 — src/ layout, installed editable with `pip install -e . --no-deps`
Package lives under `src/atp/`; `[tool.setuptools.packages.find] where=["src"]`. Installed
`--no-deps` so the editable install does not pull the deferred heavy stack. Top-level `atp/__init__`
imports must stay light (no torch/vllm/lean at import time) so the fast suite runs on a login node.
Rationale: keeps the marker-gated fast/slow test split honest.

### 2026-06-04 — HF_HOME pointed into scratch via `apply_env(config)`
`config.project.hf_cache = scratch/hf-cache`; `apply_env` resolves it against `project.root` and sets
`HF_HOME` so model/data downloads land in shared scratch, never `$HOME` (storage-hygiene rule).
CLI entrypoints call it before any HF use.

### 2026-06-04 — Lean/mathlib pins LOCKED — RESOLVES Task 0.2 TODO (verified, not guessed)
**Lean toolchain:** `leanprover/lean4:v4.9.0-rc1`.
**mathlib4:** commit `2f65ba7f1a9144b20c8e7358513548e317d26de1` (2024-08-07) from the FORK
`https://github.com/xinhjBrant/mathlib4.git` (NOT upstream leanprover-community/mathlib4).
Rationale: this is the exact submodule (`mathlib4 @ 2f65ba7…`, url `xinhjBrant/mathlib4`) that
Goedel-Prover-V2 pins for compiling/verifying proofs; matching it makes our verifier agree with the
proof format the prover model was trained to emit. Verified by reading the repo's `.gitmodules` + root
tree submodule pointer and fetching `lean-toolchain` at that commit (the official-mathlib API 404'd on
this SHA, confirming it is fork-specific). Recorded into `configs/base.yaml` (`lean.toolchain`,
`lean.mathlib_commit`) + a new `lean.mathlib_repo`. The actual `lake build` of this mathlib into
`scratch/lean-cache` is DEFERRED (disk hold) — pin is locked now; build happens once disk is freed.
Flagged to the team before writing the Lean layer, per the Task 0.2 instruction.

### 2026-06-04 — Disk: filesystem has headroom (672 TB free); "100%/20 GB" was a stale view — SUPERSEDES the disk-hold note
Re-checked `df -h /insomnia001`: **1.7 PB filesystem, 61% used, ~672 TB available.** The earlier
"100% / ~20 GB free on a 5 TB mount" figure does not reflect the live filesystem (likely a transient
or a per-view/quota number captured during Task 0.1). So **raw space is not a blocker** for the heavy
install. The heavy `[gpu]`/`[lean]` install + multi-hour `lake build` are still deferred for a
different reason: they belong on a GPU/compute node (per CLAUDE.md) and shouldn't be kicked off
unattended from a login node. Action: confirm a per-project quota (if any) with the team, then run the
heavy install + `lake build` inside an interactive `srun` session. Token/verify code paths remain
fully mock-tested meanwhile.

### 2026-06-04 — Task 0.3 design: budget meter as the enforcement seam; vLLM via a `Transport` abstraction
**Budget meter (`src/atp/budget/meter.py`).** `BudgetMeter` is the single source of truth for the
per-problem token budget `B`. Accounting uses the server-reported `usage.completion_tokens` — never a
local estimate — so the budget equals what the GPU actually generated. API split: `request(n)` clamps
the next call to `min(n, remaining)` and raises `BudgetExhausted` when nothing remains (clean,
catchable stop — the agent saves partial state, doesn't crash); `spend(actual, label)` charges the
ledger after the call. `snapshot()`/`restore()` round-trip the spend+ledger for requeue (rule 0.3).
Rationale: clamp-then-spend keeps generations inside budget while accounting stays exact even if a
server returns a hair more than requested.

**Model client (`src/atp/models/client.py`).** `VLLMClient` talks to the persistent vLLM server over
a `Transport` Protocol: `OpenAITransport` (real — uses the `openai` SDK against vLLM's OpenAI-compatible
`/v1/completions`, `openai` **imported lazily** so `import atp.models` stays light) vs
`ScriptedTransport` (tests/smoke — exact token control, records payloads). Chose the `openai` SDK over
raw HTTP because it's already a pinned light-core dep and matches the "persistent vLLM + HTTP" decision
above. `generate()` is budget-aware: clamps `max_tokens` via the meter, then charges the returned
`completion_tokens`.

**Prompt templates (`src/atp/models/templates.py`).** `WholeProofTemplate` (Goedel-Prover-V2-8B) and
`TacticTemplate` (BFS-Prover) behind a `PromptTemplate` Protocol, selected by
`config.model.prompt_template`. Whole-proof renders a `lean4` fenced scaffold and extracts the **last**
fenced block from the completion (models draft in earlier blocks); tactic mode returns the first
non-empty line. NOTE: instruction wording follows the published model cards — if a card revision drifts,
update here and log it (the served `revision` is pinned, so prompt changes are deliberate + audited).

### 2026-06-04 — Task 0.4 design: budget is the stopping criterion; state checkpointed every attempt
**Loop shape (`src/atp/agents/whole_proof.py`).** `WholeProofAgent` runs *rounds*: a fresh proposal
then up to `max_refine` error-fed refinements, repeating rounds until solved or budget-out. The
**budget meter is the real stopping criterion** — `client.generate` raises `BudgetExhausted` when the
ledger is empty, which the agent catches as a clean stop (`stop_reason=budget_exhausted`), never a
crash. `max_rounds` is only a safety cap so a generous budget can't spin forever. Rationale: keeps the
loop honest to the project's central knob (fixed token budget) rather than an iteration count.

**State + resume (`src/atp/agents/state.py`).** `AgentState` checkpoints after *every* attempt
(atomic tmp+rename, so a preempt mid-write can't corrupt it) and carries the `BudgetMeter` snapshot.
On resume: a *finished* checkpoint short-circuits (no work redone); an *unfinished* one restores the
meter so spend continues from where the killed job stopped (rule 0.3). The attempt trail is retained
for later analysis / Phase-2 trajectory collection. Per-problem file fits the planned
`results/<run>/problems/<id>.json` layout.

**Dependency injection.** The agent takes an injected `VLLMClient` (carrying the meter) + `Verifier`,
so the whole loop is exercised end-to-end in the fast suite with `ScriptedTransport`+`ScriptedBackend`
— no GPU/Lean. The scripted server honors the meter's clamped `max_tokens`, so mocked budget
accounting equals production. The real end-to-end solve is a single `lean+gpu+slow` test, deferred
with the compute-node install.

### 2026-06-04 — Verification backend = Pantograph (replaces LeanDojo skeleton) — SUPERSEDES the LeanDojo plan
The real Lean backend is **PyPantograph** (`pantograph` 0.3.15), not lean-dojo. Rationale: the sibling
project `…/theorem-proving-research` already has Pantograph working on this exact cluster as a
**persistent Lean 4 REPL** (one Lean process with Mathlib preloaded; ~0.1–0.5 s/tactic vs lean-dojo's
heavyweight per-call cold start and finicky tracing). Lighter, proven here, and supports both whole-proof
file compilation and tactic-mode stepping (needed for the BFS axis). `LeanDojoBackend` in
`src/atp/lean/backends.py` is replaced by `PantographBackend` (same `LeanBackend` protocol, so the
`Verifier` and agent loop are unchanged). `lean-dojo` is dropped from the `[lean]` optional deps in
favor of `pantograph`. The `LeanBackend` protocol indirection from Task 0.2 is exactly what makes this
swap a localized change.

### 2026-06-04 — Verification ENV split: Goedel pin for all reported numbers; v4.29.0 quarantined to plumbing — SUPERSEDES the 2026-06-04 "pins LOCKED … build deferred (disk hold)" entry
Adopting the **hybrid** strategy (parallelize, don't serialize) with a **hard guardrail**:

- **Goedel pin** (`leanprover/lean4:v4.9.0-rc1` + `xinhjBrant/mathlib4@2f65ba7…`, the locked pin) is the
  verification target for **every number that lands in `results/` or the paper** — starting with the
  Phase 0 baseline reproduction and everything downstream.
- **v4.29.0 + upstream mathlib + Pantograph** (reused from the sibling project's prebuilt 7.3 GB
  `lean_env/.lake`) is **QUARANTINED to plumbing validation, smoke tests, and CI only**. No reported
  number is ever measured against it.

**Why the guardrail is non-negotiable (measurement validity, not style):** Goedel-Prover-V2-8B was
trained to emit proofs against a ~v4.9-era mathlib API. Between v4.9.0-rc1 and v4.29.0 there are many
mathlib releases of lemma renames/deprecations/signature changes, so verifying the prover's outputs
against v4.29.0 turns a systematic fraction of failures into pure **API drift** (math correct, lemma
moved) rather than proving ability — directly corrupting pass@B, the headline metric, and undermining
the project's rigorous-evaluation claim. **Switchover gate:** v4.29.0 answers "does the pipeline run";
the Goedel pin answers "is the number right." The Phase 0 baseline reproduction is the harness's
correctness test (it must land in a believable range for a known 8B prover); on a mismatched mathlib an
anomalously low number is indistinguishable from a harness bug, so the baseline repro and everything
after it run on the Goedel pin. Hold this line under time pressure.

**Acquisition — CACHE_MISS confirmed (from-source build required):** `scripts/setup_lean_env.sh`
installed the v4.9.0-rc1 toolchain (commit be6c4894e0a6) and `lake update`d the fork (manifest written,
8 deps incl. mathlib resolved). `lake exe cache get` returned **0% success** — "some files were not
found in the cache … your local checkout of mathlib4 has diverged from upstream." So the `xinhjBrant`
fork is **custom-patched** (its oleans are not hosted in mathlib's cache), and Mathlib must be **built
from source** (~thousands of modules; multi-hour, many-core). This runs as a **Slurm burst job**
(`slurm/build_lean.sh`), NOT on a login node; `lake build` is incrementally resumable so a preempt/
requeue continues from existing oleans (rule 0.3). The setup script now stops at cache-get on a miss
and points to the slurm job (it must never compile on the login node).

### 2026-06-04 — Phase 1 risk noted: BFS-Prover may need a different mathlib pin than Goedel (decide before Phase 1)
If BFS-Prover-V1-7B expects a different mathlib than Goedel's pin, the generation-mode axis (whole-proof
vs tactic search) confounds **search algorithm** with **model identity + environment**. Two clean
resolutions, pick before Phase 1: (a) run each prover in its **native environment** and report it as a
bundled "environment travels with the model" comparison; or (b, cleaner) implement **best-first search
driving the Goedel model in tactic mode**, isolating search-vs-whole-proof with model + mathlib held
constant — viable only if Goedel emits usable single-tactic steps (quick probe needed). Not blocking
Phase 0; logged now so it isn't a surprise.

### 2026-06-05 — Verification backend = leanprover-community/repl (NOT PyPantograph) — SUPERSEDES the 2026-06-04 Pantograph decision
**The Pantograph decision does not survive contact with the Goedel pin.** PyPantograph ships a
`pantograph-repl` binary **compiled against a specific Lean toolchain**, and **no PyPantograph release
matches our pin (Lean v4.9.0-rc1)** — its oldest tagged toolchain is v4.18.0 (verified by walking every
tag's `src` submodule → `leanprover/Pantograph` `lean-toolchain`: v0.3.0→4.18.0, …, v0.3.15→4.29.1).
The sibling project's binary is v4.29.0, and **olean format is version-specific**, so it cannot load our
v4.9.0-rc1 mathlib. Using Pantograph at the pin would require digging up a pre-tag Pantograph commit and
building it from source with a matching old Python wrapper — fragile, and there's a better option already
in hand.

**Decision:** verify with **`leanprover-community/repl`**, the persistent Lean process that the
Goedel/DeepSeek-Prover eval harnesses themselves use. It is **already vendored** as a dependency package
of the pinned mathlib build (`.lake/packages/REPL`), so its `repl` exe is **version-matched to v4.9.0-rc1
by construction** — built with a 40 s `lake build repl` (no Mathlib recompile; depends only on Lean core).
It needs **NO Python package** (just a subprocess speaking newline-delimited JSON over stdio), which
removes the entire version-matching problem Pantograph created. New `src/atp/lean/repl.py`:
`ReplBackend` keeps ONE process with `import Mathlib` loaded as **base env 0** (slow cold start ~4–5 min,
amortized across the whole sweep), runs every candidate proof against env 0 (independent), and reformats
the REPL's JSON messages to `name.lean:line:col: sev: text` so the Task-0.2 `errors.py`/loophole/earliest-
step logic is reused unchanged. `sorries` (reported out-of-band) are surfaced as a sorry-warning line so
the Verifier still rejects them. Transport is injectable (`ScriptedReplTransport` for the fast suite,
`SubprocessReplTransport` for real) — same DI pattern as `VLLMClient`. Per-proof timeout restarts the
(possibly wedged) process. **`PantographBackend` is kept only for the quarantined v4.29.0 plumbing/CI
stack** (it works there); the Goedel-pin guardrail is unaffected — this strictly *improves* measurement
validity by matching the prover's own verification harness. `[lean]` optional dep on `pantograph` is now
plumbing-only; the Goedel-pin path requires no pip install. **Empirically validated 2026-06-05** on the
built env: `import Mathlib`→env 0; `True := by trivial` accepted (no messages); `(1:Nat)=2 := by rfl`
rejected ("The rfl tactic failed … ⊢ 1 = 2").

### 2026-06-05 — LEAN_PATH must probe BOTH `.lake/build/lib/lean` and `.lake/build/lib` (Lean-version layout)
`compute_lean_path` (extracted to a shared free function in `backends.py`, used by both backends)
originally looked only under `.lake/build/lib/lean` (the newer-toolchain layout, e.g. v4.29.0). **The
Goedel pin (v4.9.0-rc1) places package oleans directly under `.lake/build/lib`** (no `/lean`), so the
old code produced a LEAN_PATH **missing all of mathlib** on the pin — every real verify would have failed
with phantom "unknown identifier" errors indistinguishable from proving failures (a silent measurement
bug). Now each package/project lib probes `lib/lean` first, then bare `lib`, selecting whichever actually
contains oleans. Covered by two unit tests (bare-layout finds mathlib; nested-layout still wins when
present). Found while validating the env, 2026-06-05.

### 2026-06-06 — Cold `import Mathlib` fix is node-LOCAL staging, NOT the pickle (premise corrected)
The 2026-06-05 plan was to defeat the ~4.7k-olean GPFS open-storm by pickling the Mathlib env to ONE
file and `unpickleEnvFrom`-ing it (a single sequential read). **That premise was wrong.** Two pickle
jobs (10244652, etc.) still timed out at the 2700 s `import Mathlib` ceiling — you cannot create the
pickle without first completing one cold import, and under contention even a *sequential* read of the
4.2 GB olean tree measured **~3.8 MB/s → 19m14s** (random small-file opens were >45 min). Worse, once
I finally produced a pickle (via the local route below) it was **1112 bytes** — inspection shows it
starts with `olean.<hash>` and lists module names + offsets: the REPL pickle is a lazy **olean index**
that memory-maps the oleans at unpickle time, **not** a self-contained env snapshot. So a pickle on
GPFS re-triggers the exact same open-storm; it only helps when the oleans are on fast local disk.
**Decision: stage the built env to node-local SSD (`/local/$USER`, 294 GB; `/tmp` fallback) at the
top of every sweep job, then point `ReplBackend` at it via the new `ATP_LEAN_PROJECT` env override.**
Measured on ins071: `cp -a` the env to `/local` ≈ 10 min (bounded, sequential), then `import Mathlib`
**from local = 141 s** (vs >2700 s timeout off contended GPFS), and a warm `unpickleEnvFrom` of the
local index = **2 s** with correct verdicts (`Nat.Prime 7 by decide`→ok, `1=2 by rfl`→compile_error).
The pickle is therefore demoted to a *local* warm-start nicety (141 s→2 s for restarts within a job),
written next to the local project automatically. `slurm/sweep.sh` now stages once per node (restart-safe
via a `.staged_ok` marker + olean-count match) before the GPU/probe steps. The Goedel-pin guardrail is
unchanged — verification still runs on the same v4.9.0-rc1 + pinned-mathlib oleans, just read locally.

### 2026-06-06 — GPU stack pinned to cu124 (driver-bound): vllm 0.8.5.post1 / torch 2.6.0 / transformers 4.51.3
Task 0.3 GPU deps were deferred+unpinned; bringing up vLLM exposed a hard cluster constraint. The l40s
nodes run **NVIDIA driver 550.54.14 = CUDA 12.4**. A naive `pip install vllm` pulled **vllm 0.22.1 +
torch 2.11.0+cu130**, which fails at `import torch` time on the GPU with *"NVIDIA driver too old (found
12040)"* → `cuda.is_available() False`. So **torch must be a cu124 build** (driver 550.54.14 is exactly
the cu124 minimum; cu126/cu128/cu130 need newer drivers). The model is **`Qwen3ForCausalLM`**
(Goedel-Prover-V2-8B, confirmed via config.json), so vLLM must also have Qwen3 support — first added in
the **0.8.5** line. **0.8.5.post1 is the unique sweet spot**: ships torch 2.6.0+cu124 *and* has Qwen3;
vllm≥0.9 moves to torch 2.7+cu126 (won't run here). Pinned `transformers==4.51.3` (vllm 0.8.5 expects
4.51.x + Qwen3; transformers 5.x breaks vllm). flashinfer omitted on purpose → vLLM uses the xformers
backend (`xformers==0.0.29.post2`). **Gotcha:** mixing cu13→cu124 wheels corrupted the `nvidia/`
namespace (uninstalling a cu13 lib deleted the cu12 `libnccl.so.2` sharing the same path → torch
ImportError); fixed by purging all bare/cu13 `nvidia-*` orphans then `--force-reinstall --no-deps` the
cu12 set. Installing the GPU stack also downgrades huggingface-hub 1.17→0.36 (transformers caps <1.0)
and numpy 2.4→2.2 — fast suite still 118-green, so the light-core code tolerates both. Verified on an
l40s (job 10258474): torch 2.6.0+cu124 `cuda.is_available True`, matmul OK, `import vllm` OK. Versions
recorded in pyproject `[gpu]`.

### 2026-06-06 — Prover inference: chat-completions + official Goedel-V2 prompt + 40960 context (was 0/5)
First real GPU smoke (job 10258932) ran the full pipeline green but scored **pass@4000 = 0/5**.
Inspecting the agent traces showed the failure was an inference-format mismatch, not hard problems
(the easiest, `mathd_algebra_182`, is a one-line `ring` identity): (1) the client drove the model via
raw **`/v1/completions`** with a hand-built "Complete the following Lean 4 code…" string, applying NO
chat template — but Goedel-Prover-V2-8B is a **Qwen3 reasoning model** (`tokenizer_config.json` has the
`<|im_start|>` chat template); raw completion makes it emit prose ("This completes the proof. The
`ring_nf` tactic…") instead of a ```lean4 block; (2) the 4000-token budget truncated the chain-of-
thought before the model ever reached its final fenced proof. This is exactly the
[[feedback_inference_mode_match]] failure class. **Fixes:** (a) added `model.chat_completions` (default
true) → `VLLMClient` now sends `messages=[{role:user,…}]` to `/v1/chat/completions` so vLLM applies the
model's own template; client parses both `choices[].text` and `choices[].message.content`. (b)
`WholeProofTemplate` now emits the **official Goedel-Prover-V2 prompt** — "Complete the following Lean 4
code:" + the formal block ending in `:= by sorry` + the model-card "provide a detailed proof plan…"
suffix; refinement carries statement+error in a clean chat turn (no dangling open fence). (c) bumped
`max_model_len` 16384→**40960** (model's native context; reasoning needs CoT room) and the smoke budget
4000→32000; slurm scripts now read max_model_len from config. flashinfer absent → vLLM samples with the
PyTorch-native top-p/top-k path (fine). Fast suite 123-green (added chat-mode + prompt tests). Validating
on resubmitted smoke 10260159.

## 2026-06-06 — REMOVE the REPL env pickle entirely (it crashes on norm_num); harden probe + verify
**Decision:** `ReplBackend._load_base_env` now ALWAYS does a fresh `import Mathlib` and NEVER calls
`pickleTo`/`unpickleEnvFrom`. The `mathlib_env.pkl` path is deleted from the code.

**Why:** The Phase-0 smoke (job 10266928) scored every real proof 0 (`pass@32000 = 0/5`) with
"Proof rejected (no parseable error)". Root cause (captured via `scripts/diag_repl.py` + the
2-problem live repro 10269064 with per-attempt `raw_output`): an env restored via `unpickleEnvFrom`
is a lazy olean *index*, not a real snapshot, and it CANNOT evaluate a compiled `@[init]` meta
extension. The first proof that uses `norm_num`/`nlinarith` aborts the whole Lean process:
`libc++abi: terminating ... cannot evaluate '[init]' declaration 'Mathlib.Meta.NormNum.normNumExt'
in the same module`. `_restart()` then reloads from the *same* broken pickle → crashes again →
persistent "no parseable error" for every later proof. The probe (`trivial`/`rfl`) never exercises a
compiled extension, so it passed a broken env. A clean CPU-only replay (fresh `import Mathlib`, ~95s)
verified the SAME proofs correctly, including `norm_num` — so the pickle, not the proofs or the
parser, was the fault. The pickle only ever saved ~140s once per process; correctness wins.

**Also (defense in depth):**
- `slurm/sweep.sh` probe now additionally requires a `norm_num` proof to be accepted — a broken env
  aborts the process *there*, before any GPU spend, instead of masquerading as low pass@B.
- `ReplBackend.verify` retries ONCE on an infra crash (process death), restarting onto a fresh env,
  so a transient REPL death never scores a *valid* proof as failed; a persistent crash returns a
  distinct `REPL_INFRA_ERROR` output (never confused with a real compile error). Tests:
  `test_always_imports_never_pickles`, `test_infra_crash_retries_once_on_fresh_process`,
  `test_persistent_infra_crash_reports_infra_error_not_compile`.
- Per-attempt truncated `raw_output` is persisted in agent state (only for unparseable rejections)
  so future infra glitches are debuggable from results/.

**Status:** fast suite 126 passed; stale `mathlib_env.pkl` removed from the GPFS env; decisive smoke
(job 10270058) running to confirm pass@B > 0.

## 2026-06-07 — Sweep robustness: per-cell containment + loud failure + generous request timeout
- **Decision:** a single (problem,seed) cell failure must NEVER abort the sweep. `run_sweep` contains
  every per-cell exception, skips writing that cell's file (so resume retries it), and always writes
  `metrics.json` for the cells that did finish. Rationale: under concurrency one transient vLLM
  `APITimeoutError` killed baseline 10272937 at 165/732 with zero recorded metrics.
- **Decision:** the slurm wrapper must fail LOUDLY. With `set -uo pipefail` (intentionally no `-e`, so
  per-stage guards control flow), the sweep command's exit code is now checked explicitly, and a
  missing `metrics.json` after a "clean" exit is treated as failure. A crashed sweep must show Slurm
  FAILED, never COMPLETED.
- **Decision:** vLLM request timeout = 3600s (config `model.request_timeout_s`), max_retries=4. One
  request generates up to `max_model_len//2` (20480) tokens; at the concurrent per-stream rate that is
  tens of minutes, so the prior 600s default spuriously timed out. Sized as a ceiling, not a guess.

## 2026-06-07 — Fit completion length to the context window (reactive clamp + retry)
- **Decision:** the client absorbs vLLM context-length 400s by shrinking `max_tokens` to
  `window - prompt_tokens - margin` and retrying once, rather than letting them fail the cell.
  Reactive (catch the 400) not proactive (pre-count tokens) because the server applies the chat
  template, so an exact client-side prompt-token count isn't available; and the 400 is returned
  before any generation, so the retry costs nothing. Budget is still respected (clamp is min'd with
  the original budgeted request). True no-room cases (prompt ≈ whole window) re-raise into sweep
  containment. Trigger: baseline 10304768 cell imo_2019_p1 seed=0.

## 2026-06-10 — Phase 1 component framework: no-op-by-default composable pipeline
- **Decision:** each Phase 1 ablation axis is a `Component` with optional hooks (first hook:
  `decorate_prompt`), assembled by `build_components(config)` into an ordered `ComponentPipeline`.
  **Every hook defaults to a no-op and an empty pipeline is the identity**, so an agent with no
  components enabled is byte-for-byte the Phase 0 baseline. Rationale: the completed Phase 0 pass@B
  curve is the reference each axis is measured against — the baseline path must stay provably
  unchanged. Enforced by `test_agent_baseline_prompts_carry_no_hint`.
- **Decision:** add hooks only when a component needs them (no speculative interfaces). Today only
  `decorate_prompt` exists (prompt-side). Accept-side hooks (reviewer) and others land with their
  component. Pipeline order is fixed in code (not config-driven) so a toggle set maps to one
  pipeline → reproducible config-hash.
- **Decision:** unknown sub-options (e.g. a bad skeleton schedule name) raise in `build_components`,
  i.e. *before* any GPU/Lean work — fail fast on the login node, not 6h into a sweep.

## 2026-06-10 — Tactic-skeletons component (first Phase 1 axis): fixed schedule, fresh-proposal-only
- **Decision:** tactic-skeletons appends a one-line structural hint (e.g. "try `nlinarith`/`norm_num`",
  "simplify then `linarith`", "`omega` for ℕ/ℤ arithmetic") to **fresh proposal prompts only**,
  cycling a fixed schedule by `round_index % len`. Refinement prompts are left untouched — the
  concrete Lean error already steers them and a generic skeleton hint would only dilute that signal.
- **Decision:** schedules are hard-coded (no learning, no data dependency); the name is recorded via
  the config in the run manifest, so a schedule change is an explicit, logged edit. Started with one
  `default` schedule of 8 competition-style skeletons (ordered by how often each closes miniF2F/
  ProofNet goals). This is the cheap "structural priors" axis the plan wants to verify/refute.
- **Scope note:** this is Tasks 1.1 (framework) + first slice of 1.3 (one component). BFS (1.2),
  memory, reviewer, retrieval remain unimplemented placeholders. No GPU run yet — sweep is gated on
  team sign-off per PROJECT_PLAN §12.

## 2026-06-10 — Memory component (Phase 1 axis): within-problem failure recall, prompt-side
- **Decision:** the memory component summarises the most-recent *failed* attempts (compact proof
  snippet + Lean error) into **fresh-proposal prompts only**, as an explicit "do not repeat these"
  block, to stop the budget re-drawing near-duplicate dead ends. Refinement prompts are left clean
  (same rationale as skeletons: the immediate Lean error is the signal). Round 0 (no history) is a
  no-op → baseline-identical.
- **Decision:** scope is deliberately **within-problem only** (read-only over `ctx.history`); no
  cross-problem global solved-lemma memory yet — that's a separate, larger design (shared store,
  contamination/leakage care) deferred unless the ablation motivates it.
- **Decision:** to give components prior-attempt context without new plumbing, `PromptContext`
  gained a `history: tuple[Attempt, ...]` field (default empty → backward-compatible); the agent
  threads `tuple(state.attempts)` in. Bounded by `memory.max_items` (config, default 3) and a
  per-item proof-snippet char cap so prompts can't blow up.

## 2026-06-10 — BFS (Task 1.2) needs a Lean proof-state stepping layer first (FORK, not yet built)
- **Finding:** the `LeanBackend` protocol is **whole-proof only** (`verify(theorem, proof)`); the
  REPL backend checks a complete proof against base env 0 and has **no tactic-stepping /
  proofState interface**. True tactic-level BFS (the BFS-Prover comparator the plan intends) needs
  incremental `{"tactic", "proofState"}` stepping wired onto the REPL — a separable Lean-infra
  subsystem with its own correctness traps (see reference_lean_repl_cluster).
- **Decision (pending team):** do NOT silently build the stepping layer. Surfaced as an explicit
  fork — (A) build REPL proofState stepping then real BFS; (B) keep doing the prompt-side/whole-proof
  components first; (C) cheap pseudo-BFS over whole proofs (rejected as not the real comparator).
  Proceeded with prompt-side components (skeletons, memory) meanwhile.

## 2026-06-10 — Reviewer/critic component (Phase 1 axis): pinned semantics
- **Decision (semantics, user-delegated):** the reviewer is an LLM critic consulted **only on a
  candidate proof Lean has just REJECTED**. Lean stays the free, authoritative gate, so a true solve
  is never blocked/delayed/discarded by the critic, and the critic's token cost is paid only on
  failures (where the agent refines anyway). Rejected the alternatives: a *pre-Lean* gate would risk
  throwing away real solves (and saves no token budget, since Lean isn't token-metered); a
  *post-Lean-on-passes* scorer would spend budget after the loop already ended.
- **Consequence — clean false-accept metric:** because every reviewed proof is known-bad (Lean
  failed it), an ACCEPT is by definition a false accept. `reviewer_false_accept_rate = accepts /
  reviewed`, aggregated over cells (`ProblemResult.n_reviewed`, `n_review_false_accept`), surfaced in
  metrics.json only when the reviewer ran. This is the plan's required soundness number (how
  unreliable the critic would be as a standalone acceptance gate).
- **Behavioural value:** the critique is appended to the next refinement prompt (a second opinion on
  *why* it's wrong, on top of the raw Lean error). So the ablation is honest on both axes — does the
  critique improve pass@B enough to pay for its token cost, and the standalone false-accept rate.
- **Budget safety:** the critic call is metered; if it exhausts mid-step the failed attempt is still
  recorded, then the cell finishes STOP_BUDGET cleanly (new `_step` return value "budget"). Verdict
  parsing is conservative: ACCEPT only on an explicit accept token, first explicit token wins, else
  REJECT. `ReviewerCfg.max_tokens` default 256 (small, so the critic can't starve proving).

## 2026-06-10 — Retrieval component (Phase 1 axis): BM25 baseline over a premise-corpus file
- **Decision:** implement the **BM25** retrieval baseline (lexical, rank-bm25, no GPU); **defer
  ReProver** (`backend: reprover` raises NotImplementedError — it needs a trained neural index).
  Retrieves the top-k library lemmas for the goal and injects them into **fresh proposals only**
  (consistent with skeletons/memory; the ablation question is "do up-front relevant lemmas help at
  fixed budget"). Index over `name + decl`; query = the theorem statement; identifier-run tokenizer.
- **Decision:** retrieve over a **premise corpus JSONL** (`RetrievalCfg.corpus`, `{"name","decl"}`
  per line). The corpus is a *separate data-prep artifact* (a Mathlib declaration dump), NOT built at
  runtime — keeps the component pure/testable and the heavy Lean/Mathlib export out of the agent.
  bm25 without a corpus **raises at build time** (fail fast on the login node), never silently
  retrieves nothing. ⇒ **Prerequisite for the retrieval sweep arm: produce/stage the corpus** (a
  `scripts/build_premise_corpus.py` from the pinned Mathlib, not yet written).
- **Pipeline order (fixed):** retrieval → memory → skeletons → reviewer (outer context first).

## 2026-06-10 — Premise corpus built by lexically parsing pinned-Mathlib source (not the REPL)
- **Decision:** build the BM25 premise corpus by **parsing Mathlib `.lean` source** (the 4361 files
  vendored in the staged Lean env at `.lake/packages/mathlib/Mathlib`), NOT by enumerating the
  compiled environment via the REPL. Rationale: pure CPU/string work, login-node safe, no REPL
  gotchas (see reference_lean_repl_cluster); approximate captures only add mild bag-of-words noise to
  a lexical index — never unsoundness (a retrieved premise is a hint; Lean still checks the proof).
- **Parser** (`src/atp/data/premises.py`): tracks the `namespace` stack to qualify names (sections
  don't affect names), captures each decl's signature from its keyword up to `:=`/`where` (multi-line
  headers joined), strips attributes/comments/docstrings. Kinds: theorem/lemma/def/abbrev/instance
  (named). First occurrence of a name wins (deterministic via sorted files). CLI:
  `scripts/build_premise_corpus.py` (defaults derive source root + commit from base config; writes a
  `<out>.meta.json` provenance sidecar).
- **Result:** 148,727 premises → `scratch/premises/mathlib_2f65ba7f.jsonl` (24 MB), pinned to the
  Goedel mathlib commit. BM25 index builds in 2.1s, ~250ms/query. Wired into phase1_ablation.yaml's
  retrieval arm. **Known limitation (honest ablation finding):** BM25 retrieves excellently when the
  goal names library concepts (gcd, sin/cos → exact lemmas) but weakly for bare symbolic algebra
  (a+b=b+a) where there are no distinctive identifiers — a lexical-retrieval property, not a bug.

## 2026-06-10 — Phase 1 ablation expansion (Task 1.4): OFAT cells, hash-deduped, fail-fast
- **Decision:** a `sweep` config (baseline + axes) expands to concrete validated `ExperimentConfig`
  cells via `atp.eval.ablation.expand_ablation` — baseline = base⊕sweep.baseline; each variant cell =
  baseline⊕variant (OFAT: differs only in its axis). The existing `run_eval` runs each cell unchanged
  into `results/<run>/<cell>/`; a Slurm array maps array-id → cell. CLI: `atp ablation --list/--check/
  --cell-id`. Each variant is re-validated → malformed overrides fail on the login node.
- **Decision (efficiency):** dedup cells by `config_hash`. Each axis's "control" variant is identical
  to the baseline (e.g. memory-off, alloc_split=0.5, whole_proof), so without dedup the 244×3 baseline
  grid would run ~7× over. First cell with a given config wins (the baseline), so an axis contributes
  only its *distinct* variants. phase1 → 14 raw cells collapse to **7 distinct** (baseline + bfs-less
  generation_mode dropped + budget_alloc 0.0/1.0 + memory/reviewer/retrieval/tactic_skeletons on).
- **Decision (correctness guard):** `agent.mode='bfs'` has no agent yet, and `solve_fn` always builds
  the whole-proof agent — so a bfs cell would silently run as whole-proof and corrupt the generation-
  mode arm. `WholeProofAgent.from_config` now raises NotImplementedError on non-whole_proof mode, and
  `validate_cells` flags it pre-flight. The bfs variant is commented out in phase1_ablation.yaml
  (re-enable when BFS lands), mirroring the deferred reprover retrieval cell.

## 2026-06-10 — Ablation Slurm array wrapper (slurm/ablation.sh): per-task isolation + flock staging
- **Decision:** one array task = one ablation cell (`--array=0-6%4` for phase1's 7 cells), each
  serving its own vLLM and running that cell's problems×seeds grid via `atp ablation --cell-id`.
  Adapted from sweep.sh by DUPLICATION (not refactor) — sweep.sh is battle-tested and the baseline
  path; left byte-identical to avoid regressing it (untestable off-cluster). Header note says keep the
  shared hardening in sync.
- **Decision (concurrency correctness):** co-located array tasks (l40s nodes have several GPUs) would
  collide on (a) the shared vLLM endpoint file and (b) the node-local Lean-env staging rm+copy. Fixes:
  per-task **port** (`8000+task`) + per-task **endpoint file** read via new `ATP_VLLM_ENDPOINT_FILE`
  override (`run.resolve_endpoint_file`); and **flock**-guarded staging so the first task stages and
  the rest reuse `.staged_ok`. Range-guard: a task id ≥ cell count exits 0 (over-provisioning safe).
- **Decision:** keep the loud-failure contract (capture rc, require metrics.json) per cell, so a
  crashed cell shows Slurm FAILED not COMPLETED. Launch remains gated on team sign-off (PROJECT_PLAN
  §12); smoke one cell (small data.limit) before the full array.

## 2026-06-11 — Retrieval (BM25) deprioritized: Phase 1 +3.4pp did not replicate
- **Decision:** do NOT promote BM25 premise retrieval as a lever and do NOT anchor a best-combo cell
  on it. A second independent campaign (job 10461442, budget-metered to 32k for the whole curve) gives
  retrieval Δ = +2.2/+0.7/−0.8 pp at 2k/8k/32k — the Phase 1 +3.4pp@8k did not replicate (+0.7pp).
- **Why:** paired flip analysis shows symmetric churn (gains≈losses: +47/−31, +46/−41, +20/−26 at
  2k/8k/32k), i.e. the BM25 context perturbs the stochastic generation rather than injecting usable
  premises; the net sign is noise-driven and trends negative as budget grows. With per-seed std
  ~1.5–3pp and n=3, a ~3pp OFAT delta is not distinguishable from run-to-run variance.
- **Methodology rule adopted:** treat a single OFAT mean-delta under ~1 baseline-σ as noise; require
  more seeds or paired/within-run (flip-count) evidence before calling a component a real effect. By
  this rule none of the Phase 1 components cleared noise.
- **Consequence:** re-prioritize generation-mode BFS (Task 1.2) and a genuinely held-out novel split
  ahead of retrieval. Only revisit retrieval with a relevance filter / smaller k or the deferred
  ReProver neural backend — both speculative, not currently justified.

## 2026-06-11 — Second benchmark (ProofNet#) over BFS; REPL must send native UTF-8
- **Decision:** spend the post-Phase-1 effort on a second audited benchmark (ProofNet#,
  PAug/ProofNetSharp) rather than the BFS generation-mode build. Validate-premise: the Neural-AO*
  prior (search < Pass@1) + our baseline curve being flat after 32k (whole-proof saturating) argue
  against the large BFS build (REPL stepping + 2nd model + search module) before any cheap signal it
  helps. ProofNet# is foundational, low-build-risk (loader exists), and re-tests every Phase 1
  conclusion on a different distribution (undergrad analysis/algebra vs miniF2F competition math).
- **Decision (gate protocol):** before the first GPU run on ANY newly staged benchmark, run the
  CPU-only statement compile-gate (scripts/validate_statements.py). A benchmark whose heads don't
  elaborate against the pinned mathlib is silently all-zeros; the gate is cheap and decisive. It
  immediately earned its keep (caught the astral-char bug below).
- **Decision (correctness):** the REPL transport MUST serialize commands with ensure_ascii=False
  (native UTF-8). The json default (ensure_ascii=True) emits a UTF-16 surrogate pair for astral-plane
  (>U+FFFF) chars, which Lean's JSON reader mangles ("expected token"). This corrupts verification of
  any statement OR model proof using astral math notation (𝓝 nhds, 𝓟 principal, 𝓤 uniformity, ...).
  BMP notation (∫) was unaffected. Latent on miniF2F (0/1466 result files had astral chars), surfaced
  by ProofNet# analysis problems. Locked in with _encode_command + a regression test.

## 2026-06-12 — ProofNet# baseline budget ceiling: 32k, not 128k
**Decision.** Cap the ProofNet# baseline budget grid at [2k, 8k, 32k] (drop the 128k tier that the
miniF2F baseline used).
**Why.** ProofNet# undergrad math is far harder for Goedel-Prover-V2-8B than miniF2F competition math:
the prover rarely solves a problem, so almost every cell exhausts the full budget ceiling rather than
stopping early (stop_on_first_success). At a 128k ceiling that is ~76 GPU-h / ~6 requeues for 558
cells (measured: 78 cells in one 12h wall, job 10511630 TIMEOUT) — over the >50 GPU-h ask-first rule.
miniF2F showed 32k->128k is nearly flat (+5pp), so the 128k tier buys little signal here. Capping at
32k cuts per-unsolved-cell cost ~4x -> ~27 GPU-h, and 2k/8k/32k is enough for the two questions this
benchmark answers (generalization number + 2nd-benchmark recheck of "Phase 1 components are noise").
**Validity of kept cells.** The 78 cells already run under the 128k ceiling are KEPT (not re-run):
solved_within(b) = (tokens_to_solve <= b), and the ceiling never changes generation before it is hit,
so a 128k-ceiling cell's 2k/8k/32k columns equal a 32k-ceiling run's. Resume skips by filename (no
config_hash guard) -> the results dir carries a mixed config_hash; cosmetic, curve data is correct.

## 2026-06-12 (revision) — ProofNet# ceiling restored to 128k (supersedes the 32k cap above)
Supersedes the 32k-cap decision earlier today. User relaxed the >50 GPU-h ask-first rule (good
findings > marginal cluster cost). Restored the full [2k,8k,32k,128k] grid: directly comparable to the
miniF2F baseline, and the 32k->128k tier on harder ProofNet# problems is a genuine question (may not be
flat like miniF2F). Run on partition=burst (4-day wall + --requeue) so preemptions auto-requeue. The 78
cells already done at 128k are kept (resume skips by filename). Job 10534104.

## 2026-06-14 — Verifier must require a declared goal AND a well-formed REPL success
Two soundness holes let non-proofs score as `solved` (found while auditing the ProofNet# ablation,
which reported impossible reviewer/memory pass@8k of 0.5-0.84 vs baseline 0.12):
1. A submission that compiles but declares no `theorem`/`lemma`/`example` (a generation truncated at
   the token cap emitting only a preamble `def`/`#eval`/prose) was accepted because acceptance keyed
   only on "no Lean error message". DECISION: the Verifier now rejects with `reason="no_goal"` unless
   the proof text contains a goal-bearing declaration. Chose the structural "any declaration" check
   (not exact-name match) because 525/528 real solves echo the exact name but 3/528 the model renames
   the theorem — an exact-name gate would have ~0.6% false negatives; the keyword gate has 0 on real
   data while removing 100% of observed truncation false-positives. Residual (accepted): this is a
   NECESSARY not SUFFICIENT check — a proof of a *wrong restated* goal would still pass; no evidence
   of that occurring (model is prompted with the exact statement). Canonical-statement injection is
   the stronger fix if that ever shows up.
2. `repl._format_response` treated ANY response with no error-severity message as success — so an
   empty/malformed `{}` (a wedged or cross-talked REPL under array co-location) scored as verified.
   DECISION: success now also requires `env` present in the response (the REPL returns a new env id
   only on a genuinely accepted command); otherwise it's a REPL_INFRA_ERROR, never a pass. Sound but
   conservative: a malformed response is scored not-solved rather than retried.
Consequence: miniF2F Phase 0/1 numbers are unaffected (audit: 0 / 6-of-3124 false positives — short
proofs rarely truncate). ALL ProofNet# results are invalid and will be re-run with the fixed verifier;
hole #2's old responses aren't persisted so those cells can't be re-scored, only re-run.

## 2026-06-17 — Phase 2: pursue mechanism, not more levers (see PHASE2_PLAN.md)
Decision: the lever-pulling arc is DONE (scaffolding doesn't help — clean null on 2 benchmarks). Do NOT
add another scaffolding component and do NOT "wind down as-is." Instead spend one analysis pass on data
already on disk (results/*/agent_states/, full per-attempt corpus) to turn the negative result into a
MECHANISM that explains the central asymmetry: budget converts to solves on miniF2F (29.6→74.9% over 64×)
but barely on ProofNet# (4.8→14.3%). Explaining why budget stops paying off OOD also explains the
scaffolding null (the tested components can't touch the real bottleneck) — a far stronger claim.
Priority: (A) diversity-collapse analysis + 128k-unsolved failure-mode taxonomy + tokens-to-solve dist +
subfield stratification — CPU-only, gates everything. The A2 taxonomy decides which downstream direction
earns GPU-hours: knowledge-failure→one shot at relevance-filtered BM25; approach-failure→retrieval+BFS
both justified-dead; near-miss→search worth revisiting. Then (B) replicate headline findings on a 2nd
prover (DeepSeek-Prover-V2-7B) for generality. Then (C) diversity-injection ONLY if A1 supports it.
Elevate the verifier-soundness bug to a methodological contribution. NOT doing: 3rd benchmark, ReProver,
more OFAT. Thesis: "compute budget, not agentic scaffolding, is the lever for whole-proof proving at this
scale; here is where/why it saturates, across two models, with a soundness caveat for how to evaluate."
Source of this redirection: external review (pasted by user 2026-06-17).

## 2026-06-17 — Phase 2 Step C built (held for launch) + PRE-REGISTERED prediction
Decision: RUN C (do not skip on F5 alone). F5 is correlational and survivor-/distribution-conditioned —
it observes only solved problems and only the model's NATURAL ~2-approach sampling; it structurally
cannot observe the perturbed regime where we FORCE off-distribution approaches. C closes that genuine
inferential gap (selection gap + off-distribution gap), so it is decisive, not a checkbox. Cost is small
(trapped cells only, 8k/32k), so there is no resource case to skip.
Sequencing: build now at zero GPU (DONE), HOLD launch, then launch scoped as part of the coordinated B
campaign so C runs on BOTH provers (Goedel + DeepSeek-Prover-V2-7B) in one spend. Defer B's diversity
arm until C resolves (generalize the lever if positive, the floor if null).
Design: approach-conditioning (component `diversity_injection`, propose-only) over raw temperature —
temperature raises token entropy but yields noisier versions of the SAME approach and revives the
truncation/false-solve pathology the verifier fix guards against. Scope = trapped core (problems unsolved
by all seeds @128k: ProofNet# 150/186, miniF2F 55/244; lists in scratch/phase2/trapped_*.txt) at budgets
8k+32k. Measure the full 2x2 + texture, not just solve rate:
  (a) MANIPULATION CHECK — did mean_distinct_first_tactics actually rise vs baseline (analyze_mechanism
      A1)? A null is uninterpretable without this.
  (b) solve rate vs baseline @8k/32k on the trapped names (analyze_results compare + paired flips).
  (c) failure texture of the forced-new approaches (analyze_mechanism A2): do they still die at
      reasoning/goal-closing? watch syntax/truncation rate does NOT creep (run on fixed verifier).
PRE-REGISTERED PREDICTION (record before running): **diversity RISES ∧ solves stay FLAT ∧ the
forced-new approaches fail at elaboration/goal-closing at least as often as baseline** — i.e. handing the
model new approaches doesn't help because the bottleneck is within-approach execution (F2/F3 floor), not
approach discovery. That outcome = clean interventional confirmation the collapse is symptomatic; a
positive (solves rise) would instead make diversity-injection the capstone lever. Build artifacts:
src/atp/agents/components/diversity.py, config.DiversityCfg, configs/diversity_{proofnet,minif2f}.yaml.

## 2026-06-17 — Phase 2 Step B: DeepSeek pin CHOSEN (self-decided by the v4.9.0-final window)
Authoritative pin = Lean v4.9.0 (paper) + STANDARD mathlib4 @ f0957a7575317490107578ebaee9efaf8e62a4ab.
Decision method (the one the data makes for us): the v4.9.0-FINAL toolchain window in mathlib4 history
collapses to a SINGLE commit — f0957a7 ("bump toolchain to v4.9.0", 2024-07-01) is the sole mathlib4
commit on v4.9.0-final; the very next commit (f5c3f06, same day) bumped to v4.10.0-rc1. No multi-commit
bisection needed; confirm by max-verification of DeepSeek's published miniF2F proofs (438 files,
minif2f-solutions.zip) against it — fraction to be reported. REPL = leanprover-community/repl @
bump_to_v4.9.0 (its lean-toolchain == leanprover/lean4:v4.9.0, confirmed; canonical not fork). This is
distinct from Goedel (v4.9.0-rc1 + xinhjBrant fork @2f65ba7) — same Lean line, different mathlib, so the
atp Lean layer transfers but it is a genuine separate env. Cost note: STANDARD mathlib oleans are hosted →
`lake exe cache get` should HIT (minutes), unlike the Goedel fork's from-source build. Env scaffolded at
scratch/lean-cache/deepseek-lean-env; build = slurm/build_deepseek_lean.sh (job 10671073). Gates remaining
before any GPU: max-verify DeepSeek proofs (pin confirm + fraction), validate_statements.py on miniF2F +
ProofNet# against this pin → compile-on-both-pins intersection, contract tests incl sorry/admit/
native_decide rejection. Report checkpoint = {chosen commit (done), verification fraction, intersection
size} before the first GPU sweep.

## 2026-06-20 — Phase 3: harden then write (external review of completed Phase 2 arc)
Decision: scientific arc is COMPLETE; do NOT run new GPU sweeps. Before locking the negative thesis, run
4 CPU-only hardening checks (ordered by falsification payoff) + 2 reframings, then write for TMLR.
- H1 (gate): recompute the cross-model dichotomy on the compile-on-both-pins INTERSECTION, not native
  ports (Goedel=mathlib fork, DeepSeek=standard mathlib → different statement sets; the 22.2-vs-14.3 gap
  could be a coverage artifact). Does the gap survive on the intersection?
- H2 (could overturn retrieval-kill): human-validate the regex failure taxonomy on 50–100 unsolved
  attempts/prover (read raw Lean feedback, compare to auto-label). The ~0%-knowledge claim kills retrieval.
- H3: quantify soundness-creep across ALL scaffolding components (not just Step C) from existing logs →
  "scaffolding systematically shifts output toward less-sound regions; naive pipelines inflate pass rates."
- H4: decompose the OOD dichotomy via our F1/F3 lens (less collapse vs deeper execution?) — CPU on existing
  traces; unifies spine: scaffolding can't move the execution floor but TRAINING can (the real OOD lever).
- R1: frame dichotomy as TRAINING-DISTRIBUTION/RECIPE not model size (1B diff can't carry it; controlled
  model-zoo = future work). R2: soften F3 to "attempts elaborate substantially before failing".
- Output: TMLR paper "Budget, Not Scaffolding: A Mechanistic, Two-Model Study..."; workshop short version
  (MATH-AI / AI-for-Math) in parallel; arXiv + full artifact release. Soundness-creep = dedicated section.
Full plan: PHASE3_PLAN.md. Exec order H1→H4→H3→H2→reframe→write. Lock once H1–H4 pass.

## 2026-06-20 — Phase 3 Hammer/SMT leaf-closing probe: PRE-REGISTERED thresholds + compat path
Go/no-go gate for the neuro-symbolic positive direction (neural skeleton + symbolic leaf). Strongly
motivated by H4 (OOD floor = within-approach EXECUTION/leaf-closing, not approach discovery). Three arms
on the trapped cores (unsolved by all seeds @128k): Arm0 = tactic portfolio on ORIGINAL goal (control for
"model didn't invoke available automation"); ArmB = hammer/SMT on ORIGINAL statement (symbolic floor);
ArmA = hammer/SMT on the model's DEEPEST STUCK GOAL (the lever). SYNERGY SET = closed by ArmA but NOT
Arm0/ArmB alone = the positive result. Per-goal wall cap 90s; every closure re-verified by the fixed
verifier (reject sorry/admit/native_decide; assert 0 false-solves).
PRE-REGISTERED decision (anchored on Δ ProofNet# pass@B; ~160 trapped, so 10%≈16 probs≈+8-9pp):
  STRONG GO (build full neuro-symbolic prover): synergy >= +10pp ProofNet# pass@B OR ArmA >> Arm0,ArmB.
  GO (weaker, "add a hammer"): synergy +5-10pp, OR meaningful total closure dominated by ArmB.
  NO-GO: closure < ~2pp across all arms -> STRENGTHENS the negative thesis (floor resists symbolic
         automation), pre-empts the reviewer objection; ship negative result or pivot to systems-level
         fallback (cross-problem budget allocation / learned early-abandonment).
COMPAT path (the main risk — pin is Lean v4.9.0, mid-2024): Arm0 portfolio on-pin first (nlinarith/omega/
aesop/simp/norm_num are in pinned mathlib; grind is Lean>=4.14 so NOT on-pin; duper is external). Lean-SMT
(cvc5) + LeanHammer target newer Lean -> if they don't build on v4.9.0, run OFF-PIN feasibility pre-check
for a closable-fraction estimate, then port before any reported number (nothing off-pin enters results/).
Cheapest-falsification-first (validate-premise memory): smoke Arm0 + an easy hammer on ~20-30 trapped
stuck-goals; if ~0 close, fast NO-GO without building the full LeanHammer stack. Deliverable:
results/phase3/HAMMER_PROBE.md. Check in at smoke (step 3) and go/no-go (step 6).

## 2026-06-20 — Phase 4 feature/model choices
- DEP: added scikit-learn 1.9.0 (+joblib/threadpoolctl) to scratch/conda-envs/atp for the difficulty
  predictor. numpy/scipy already present. Login-node install needs the proxy KEPT (the per-session
  proxy that Slurm jobs must UNSET is what gives the login node internet); compute-node rule unchanged.
- F3 depth: use the verifier's logged "Failed at step N" as the real deepest-step feature (97.8%
  coverage), NOT a proof-length proxy and NOT a separate error-locus parser — the parse is already done
  upstream and stored. Staged plan (cheap-first) therefore needs no escalation: best_depth IS true F3.
- Model: logistic regression (StandardScaler + class_weight=balanced) over GBT as the realizable
  predictor — GBT overfits the small positive class (AUC_LR > AUC_GBT at nearly every checkpoint).
- Decision population = cells NOT solved by checkpoint c; label = eventual_solve; problem-grouped CV
  (GroupKFold) so no problem appears in both train and test (asserted in test_alloc).

## 2026-06-20 — Hammer NO-GO locked (both prover and premise-selection)
Arm B decisive on the FULL trapped set: duper (superposition) 0/119 AND lean-auto premise-selection
0/119. The reviewer's premise-selection caveat is now answered on the full set, not just an 8-sample.
NO-GO on adding a hammer component is final. Pantograph server startup can exceed 90s on loaded nodes →
use ARM_B_TIMEOUT=180 for any Arm-B reruns (the 90s default conflates startup + per-tactic cap).

## 2026-06-20 — Successive-halving: PRE-REGISTERED prediction (before building)
The single-checkpoint realizable policy has two distinct limiters: (a) compute FLOOR c*·N (one decision
point, everyone runs to c* first) — pushes DeepSeek ProofNet#@80% and all miniF2F negative; (b) RECALL
wall at 100% accuracy (hardest winnable ≈ trapped) — fundamental, no scheduler fixes it.
Successive-halving (multi-round: cheap first rung 2k, cut weakest by predicted score, promote survivors)
lowers the floor. PRE-REGISTERED, falsifiable:
  - SH SHOULD lift the FLOOR-limited cells: DeepSeek ProofNet# loose+mid targets, miniF2F negatives
    toward >=0, and tighten Goedel ProofNet# loose targets. Goal = two-model STRONG on ProofNet#.
  - SH should NOT move the 100%-accuracy-retention target on any cell (that's the recall wall).
If SH lifts the 100% target materially, the floor diagnosis was wrong — investigate, don't celebrate.
Rung schedule = [2k,4k,8k,16k,32k,128k]; cuts after each non-final rung use OOF P(solve) at that
checkpoint; sweep keep_frac. SH replaces single-checkpoint as the headline policy iff it dominates.

## 2026-06-20 — Successive-halving: OUTCOME (pre-registered prediction FALSIFIED on the headline)
Built `src/atp/alloc/halving.py` (6 tests) + wired into `phase4_frontier.py`. Result vs the registered
prediction above, scored on the same (compute, solves) frontier:
  - HEADLINE CLAIM FALSIFIED. SH does NOT give two-model STRONG and does not even beat single-checkpoint
    on compute-saved-at-accuracy — it is substantially WORSE. ProofNet# "saved vs uniform" at 80/90/95%:
    goedel c* +15/+30/+24% vs SH -95/-50/-25%; deepseek c* -16/+10/+1% vs SH -145/-99/-43%.
  - MECHANISM PARTLY CONFIRMED (floor lowered, but only at the cheapest operating point). At 5% of
    uniform's max compute the single-checkpoint policy solves 0 (its c*·N floor isn't even cleared),
    while SH solves 51/80 (goedel) and 54/124 (deepseek) by letting cheap cells finish in early rungs.
    SH also edges uniform there (+1.1pp goedel @5%) by reallocating from trapped (cut at 2k) to winnable.
    But the win evaporates by 10% compute and SH trails uniform at every moderate budget.
  - SAFETY CLAUSE HELD. SH does NOT move the 100%-accuracy target (goedel -2%, deepseek -6%, ~unchanged
    from single-checkpoint), confirming the recall wall is fundamental, not a scheduling artifact. (Good:
    the registered "if SH lifts the 100% target, the floor diagnosis was wrong" did not trigger.)
DIAGNOSIS: fixed-fraction multiplicative cutting (η per rung over 5 rungs) is too aggressive in the
rare-winnable regime (ProofNet# ~14% solvable). To retain the rare LATE-solving winnable cells you must
keep a large fraction every round, which drags trapped cells to late rungs → more compute than the
single-checkpoint THRESHOLD policy (keep a quality-defined SET, not a top-η fraction). Threshold beats
fixed-fraction here. The natural follow-up = multi-round THRESHOLDING (abandon below τ at EACH rung), but
that is a NEW policy beyond the registered SH prediction — not built; flagged for check-in, not scope-crept.
DECISION: headline policy STAYS single-checkpoint (goedel ProofNet# STRONG @90% unchanged). SH is reported
as a resolved pre-registered NEGATIVE (a credibility-enhancing falsification + the floor-lowering nuance).

## 2026-06-20 — Multi-round THRESHOLD: PRE-REGISTERED prediction (before building/running)
Cheap mod of the SH infra (same rungs [2k..128k], same cell_outcome accounting); cut rule = keep every
still-unsolved cell with OOF score >= tau at that rung's checkpoint (a quality SET), instead of SH's
top-eta FRACTION. Motivation: it abandons an early-revealing trapped cell at rung 0 (2k) instead of
waiting for the single c* (8k/16k), so unlike fixed-fraction halving it does NOT shed late-solving
winnable cells. The one empirical check that closes the load-bearing claim "scheduling can't move the
recall-limited headline" instead of leaving it as an argument (same discipline as the hammer NO-GO).
PREDICTION (falsifiable):
  - NO material headline movement: compute-saved-at-90%-accuracy stays within ~±5pp of single-checkpoint
    for BOTH models (goedel ~+30%, deepseek ~+10%). Reason: AUC peaks MID-run (8k-16k); the early-rung
    (2k) predictor is weak-to-random (goedel 0.64, deepseek 0.47 < chance), so thresholding at rung 0
    cannot abandon trapped confidently without tripping the same recall wall.
  - POSSIBLE cheap-regime gain: at fixed LOW compute (~5-10% of uniform max) MRT may beat BOTH uniform
    and SH (keeps all winnable + cuts trapped at rung 0), improving the accuracy-at-fixed-compute axis.
TRIP-WIRE: if MRT MATERIALLY beats single-checkpoint on the headline (compute-saved-at-90% up >~5pp on
either model), the ranking-limited diagnosis was INCOMPLETE — the floor was contributing to the headline
after all. Do NOT celebrate; investigate and update the load-bearing claim in ALLOCATION.md §5/§6.
This is the LAST policy variant — one check, then stop tuning: live confirming run -> lock -> paper.

## 2026-06-20 — Multi-round THRESHOLD: OUTCOME (prediction CONFIRMED; trip-wire did NOT fire)
Built `multiround_threshold`/`mrt_curve` in halving.py (5 tests; incl. the defining contrast — on the
exact costs where fixed-fraction SH shed a late winnable cell, the quality-SET threshold keeps EVERY
winnable). Wired into phase4_frontier.py. 314 fast tests pass, ruff clean. Result vs the registered
prediction above:
  - HEADLINE NOT BEATEN -> load-bearing claim now EMPIRICAL, not argued. MRT save-vs-uniform@90%:
    goedel -29%, deepseek -47% — WORSE than single-checkpoint (+30%, +10%). The trip-wire ("MRT
    materially beats single-checkpoint on the headline") did NOT fire. So "no scheduling policy moves
    the recall/ranking-limited headline" is confirmed across THREE policies (single-c*, SH, MRT).
  - WHY MRT is worse (not just equal): one τ applied at every rung thresholds at the EARLY rungs
    (2k/4k) where AUC is weak-to-below-chance (deepseek 2k=0.47), abandoning winnable by mistake unless
    τ is low enough to keep nearly everyone — exactly the mid-run-AUC-peak reasoning. It cannot shave
    the floor off the headline.
  - CHEAP-REGIME gain did NOT materialize for MRT (predicted "possible"): @5% compute MRT ties uniform
    (+0.0pp) and trails SH (45 vs 51 goedel); @10% MRT -1.4pp. Neither scheduling variant gives a robust
    cheap-regime win over uniform; SH's only edge is marginal, at the single cheapest point.
VERDICT: among {single-checkpoint, fixed-fraction SH, multi-round threshold}, single-checkpoint
(threshold at the best-AUC c*) is the best realizable policy on the headline. POLICY-DESIGN PHASE CLOSED
(the one cheap check is done; stop tuning). The writeup can now state "the scheduling policies we tested
do not improve the headline; it is ranking-limited" as a MEASURED fact, pre-empting "did you try
threshold-based multi-round?". NEXT: live confirming run (Task 4.4, GPU) on single-checkpoint -> lock -> paper.

## 2026-06-20 — Per-seed robustness + budget-independence: lock the positive as ONE-model-robust
Two checks closed the positive result (per user check-in), both CPU/analytical (no GPU):
1) PER-SEED CONSISTENCY (scripts/phase4_perseed.py): recomputed saved@90% WITHIN each logged seed
   (same global c*, same OOF predictor) as sample-generalization evidence from data in hand.
   - goedel ProofNet#: +25/+18/+34% -> +26% ± 7%. ROBUST across all 3 independent temp-1.0 draws.
     Strengthens the STRONG headline (problem-generalization already shown by OOF grouped-CV;
     sample-generalization now shown per-seed; no distribution shift = same temp-1.0 process).
   - deepseek ProofNet#: +5/+9/-51% -> high variance, seed-2 COLLAPSE. DOWNGRADED from "POSITIVE" to
     WEAK/fragile: pooled +10% is BELOW the registered 15% POSITIVE bar, and it does not survive per-seed.
     Cause: ~40 solved cells/seed + high c*=16k -> decision pop = high-tts winnable the pooled predictor
     misranks on seed 2 -> retaining 90% forces low τ -> keeps trapped -> -51%. This was the cross-seed-
     variance risk flagged in the Phase 4 plan. CONSEQUENCE: positive contribution is ONE-model-robust
     (goedel), not two-model. (Negatives — scaffolding/hammer/SH/MRT — remain two-model.)
2) BUDGET-INDEPENDENCE (by construction, code-verified): the realizable policy is EARLY-STOPPING of the
   budget-independent 128k runs, not a re-paced re-run. The agent's trajectory depends only on
   seed/model/verifier: max_refine is a FIXED count (4), alloc_split is UNUSED for pacing, and the budget
   meter's request()=min(want,remaining) clamp only truncates the max length of the single boundary
   attempt (same prompt+seed => identical token prefix; a completed/solving attempt finishes before the
   clamp bites, so neither `solved` nor `tokens_to_solve` changes). Kept cell = logged 128k trajectory;
   abandoned cell = a prefix where the verifier already shows no solve. So realized = simulated EXACTLY.
   The "simulation artifact" objection is answered analytically (it can't arise); a temp-1.0 re-run can't
   even confirm it cell-by-cell. No GPU confirming run. (Existing "intermediate-budget" test was
   identity-on-logs only; the by-construction argument + 3-way identity tests + Phase 0 pass@B suffice.)
RESULT: Phase 4 analysis DONE. ALLOCATION.md locked as the deliverable. Next = fold positive(one-model-
robust allocation) + negatives(scaffolding/hammer/SH/MRT, two-model) into the paper spine. STOP tuning.

## 2026-06-21 — Phase 5 START: reclaim-and-reinvest ("more theorems at equal compute")
NEW DIRECTION (user, post Phase-4 lock): upgrade the positive from "save compute at equal accuracy"
(allocation, one-model-robust, fragile on DeepSeek) to the stronger "prove MORE theorems at equal total
compute": early-abandon confidently-trapped unsolved cells, spend the reclaim EXTENDING still-
progressing unsolved cells past the 128k cap (ProofNet# had not saturated at 128k).

WHY THIS IS THE RIGHT SWING (structurally protected): weakly dominant by construction (§1) — Solves_
reinvest = Solves_uniform ∪ {extension solves} at total compute ≤ T, so Δsolves ≥ 0 EVERY seed
regardless of predictor quality. The seed-2 collapse that sank DeepSeek allocation (mis-abandoning
winnable-late cells → −51%) CANNOT happen here: abandon set = unsolved-at-128k (uniform failed them
anyway, so early-cut loses nothing); winnable-late cells live in the EXTEND set, which we never abandon.
A mis-routed winnable-late cell still lands in extend and gets budget. So route GENEROUSLY into extend,
abandon only most-confidently-trapped → margin (not just sign) robust to predictor misrouting.

MECHANISM DECISION — RESUME, not re-run (load-bearing, decided after reading whole_proof.py/client.py):
client.seed is FIXED per cell and passed on EVERY vLLM call, but vLLM is NOT bitwise-deterministic
across runs (batching/kv-cache), so a from-scratch re-run at E=512k would NOT reproduce the logged 128k
prefix → would conflate extension-gain with run-to-run sampling noise and break the dominance semantics.
RESUME preserves the logged 128k prefix VERBATIM (keep state.attempts + budget.spent=128k, raise
meter.limit to E, clear done/stop_reason, re-enter _search) and samples ONLY (128k,E] → realizes
Solves_reinvest ⊇ Solves_uniform exactly. This also makes resume the CORRECT semantics, not just the
cheaper one (plan §2 "prefer resume" upgraded to "resume required"). Re-run-from-scratch is NOT a valid
fallback here for the iso-compute/dominance claim. Budget-independence (Phase 4) is a within-single-run
process property (max_refine fixed, no budget-pacing), NOT a bitwise cross-run reproducibility claim.

AMENDMENT (user, from the Phase-4 lesson): report PER-SEED from the start as a first-class metric (amend
§6), not just pooled. Sign is guaranteed by construction; per-seed MARGIN is the real empirical question
— specifically whether DeepSeek's reinvest margin survives per-seed where its allocation margin didn't.

TASK 5.1 DONE (offline, no GPU): src/atp/alloc/reinvest.py (partition unsolved-at-128k into extend vs
abandon; conservative "confidently_trapped_at" = n_attempts≥5 AND depth_growth≤0 AND stalled≥4, all
≤a-observable; iso-compute reclaim/feasibility arithmetic; stratified pilot sampler). 11 tests in
tests/test_reinvest.py (partition exhaustive/disjoint/all-unsolved, leakage-free, climbing-never-
abandoned sign-safety, feasibility). scripts/phase5_candidates.py → results/phase5/candidates.json.
NUMBERS (ProofNet#, where the tail lives): goedel 478 unsolved→391 extend/87 abandon, reclaim 8.7M tok
(funds 22 extensions@512k); deepseek 434 unsolved→326 extend/108 abandon, reclaim 10.8M (28@512k).
miniF2F (saturated contrast): tiny reclaim, pilot infeasible@iso-compute@512k — expected ~0 gain, the
contrast. Per-seed extend counts balanced (goedel 122/123/146; deepseek 118/109/99). NEXT = Task 5.2
pilot gate: build the resume-to-extend runner (test-first) + extend ~10 ProofNet# cells/model to 512k,
1 seed, then CHECK IN with the pilot solve count + per-seed split before any full spend.

---
## 2026-06-22 — Phase 6 Stage B realization = OPTION 1 (proof-continuation), not subgoal-as-theorem or weighted-RFT

**Decision (user, load-bearing).** The closing-targeted SFT (Stage B, the core novel ingredient) is
realized as PROOF-CONTINUATION in the prover's exact whole-proof format: the ```lean4 code block ends at
`<statement> := by\n<deep-prefix>` (the verified proof up to a deep cut) and the SFT target is the
remaining CLOSING tactics — "here is the theorem and the proof so far, finish it."

**Why not the alternatives:**
- *Subgoal-as-theorem* (reconstruct `theorem sub (<hyps>) : <goal> := by <closing>` and train pure
  whole-proof): REJECTED. It gift-wraps the deep state into a NEW, easier statement with all hypotheses
  handed over explicitly. The model proving it shows it can close a goal someone extracted for it — NOT
  that it can reach and close that state in situ (which is the actual F2/F3 floor). Trains/measures a
  non-transferring, easier skill. "Looks rigorous, measures the wrong thing."
- *Closing-weighted RFT* (full proofs, up-weight closing tokens / oversample): REJECTED. Still trains on
  proofs the model already produces; reinforces existing capability, doesn't teach closing from states it
  currently fails at. Collapses Stage B into "Stage A with a loss reweight" → muddies the A-vs-B novelty
  claim into a hyperparameter.

**Three constraints that make Stage B real (pre-registered):**
1. **CRUX — targets must be closings the BASE MODEL CANNOT produce on its own.** Probe: feed
   (statement + prefix) to the base model at normal budget; KEEP a pair only if the base fails to close it
   AND a verified closing exists (our harvested one, another seed, or a teacher). If every target is
   already-closable, A≈B and the novelty evaporates. This is the single most important design point.
2. **Byte-exact inference format.** Continuation prompt = byte-for-byte the same fence / import block /
   `theorem … := by` scaffolding the model sees at inference, with the partial proof as a genuine prefix.
   Add a test: a base continuation prompt through the REAL inference/parse path yields a parseable
   ```lean4 block (catch the −36pp inference_mode_match mismatch BEFORE training).
3. **Single-variable A-vs-B.** Same base, corpus, hyperparameters, total tokens/steps; the ONLY difference
   is data shape (A: statement→full proof; B: statement+deep-prefix→completion of hard closings).

**Pre-commit verification (before building the full training set):** round-trip a handful of Option-1
examples — feed statement+prefix to the base model (parseable?) AND confirm prefix+closing verifies in
Lean (true by construction; spot-check catches truncation/format bugs cheaply).

**Sequencing guard:** scale the harvest beyond the 1000-problem pilot ONLY after a pilot-SFT falsification
(Stage A vs Stage B on the pilot data) shows lift signal — don't burn ~150–300 GPU-h harvesting before B
is shown to beat A. (Consistent with validate-premise-before-building.)

---
## 2026-06-22 — PRE-REGISTERED prediction for the Stage A/B pilot (before the numbers land)

**Observation (training):** with loss correctly masked to the closing tokens, SFT loss on the HARD
closings is ~0.058 (≈94% per-token prob). The base assigns high CONDITIONAL (teacher-forced) probability
to its own closings, yet the probe showed it FAILS to GENERATE them autoregressively at temperature.
That split = the classic exposure-bias / sampling-vs-knowledge signature.

**Falsifiable PRE-REGISTERED prediction:** if the execution floor is sampling-bound (not conditional-
probability-bound), then closing-targeted SFT (Stage B) should move pass@B LITTLE — because SFT
optimizes exactly the conditional probability that is already near-saturated (loss 0.06). Generic RFT
(A) likewise. A real lift would FALSIFY the saturation read.

**Three-way interpretation, fixed in advance:**
  1. B lifts pass@B meaningfully → saturation read incomplete, SFT helps → SCALE THE HARVEST. Positive.
  2. B null on pass@B BUT A-vs-B separates (B closes problems A doesn't) → partial mechanism signal →
     worth the harvest scale-up. Do NOT discard a weak-but-real separation.
  3. B FLATLY null → NOT "data-starved shrug": the loss=0.06 saturation signature is an INDEPENDENT
     mechanistic explanation → the floor is sampling/exposure-bound → the indicated lever is Stage C
     process-reward RL, NOT harvest scale-up (more SFT data = more of an already-saturated lever).
  The (sign of pass@B) × (matches saturation prediction?) pairing is the deliverable — publishable
  either way, because it diagnoses WHY the floor exists.

**LOAD-BEARING GATE (before reading ANY pass@B delta):** confirm the base-vs-adapter serving path is
BYTE-EXACT in inference format. vLLM serves the LoRA adapter on the SAME server/tokenizer/chat-template
as the base (the adapter is weights only; its saved tokenizer_config is ignored by vLLM serving), so
format is identical BY CONSTRUCTION — but given the −36pp inference_mode_match history, VERIFY
empirically (both model names produce well-formed ```lean4 attempts on the same problems; base-name
request reproduces base behavior). A silent serving discrepancy would masquerade as (or mask) a B
effect. Do not trust A/B deltas until this is green.

**Post-pilot routing (pre-loaded):** null + saturation signature → Stage C RL (evidence-motivated, not
a guess). Positive or weak-separation → harvest scale-up. The loss=0.06 finding is early evidence the
RL branch may be the right one; confirm with pass@B before committing.

## 2026-06-23 — Stage B null => pivot to Stage C RL (not harvest scale-up)
Phase 6 Stage B pilot (goedel seed 0, byte-exact serving gate passed) shows
closing-targeted SFT does not lift pass@B over base (miniF2F B-base -1.2pp@32k;
ProofNet# -0.5pp@32k); generic RFT hurts. Matches the pre-registered exposure-bias
prediction (closing-token loss saturated at ~0.06). DECISION: do NOT scale the
closing-target harvest. The execution floor is sampling-bound; the indicated lever
is Stage C process-reward RL (GRPO). B>A is a "less harmful" within-SFT contrast,
not grounds to scale (B never beats base). See PROGRESS.md 2026-06-23.

## 2026-06-28 — 3-seed eval resume: cap concurrency (root cause = self-inflicted GPFS/RAM storm)
Root cause (systematic-debugging Phase 1): launching ~15 arms × 4 shards at once → dozens of concurrent
cp of 4.2-4.6GB Lean envs (4700 oleans each) off shared GPFS into /dev/shm (RAM tmpfs). Evidence:
staged in 15128-16878s (4+h vs script's 3-20min estimate); failure split 37 reused-env probe-FAIL /
5 fresh-staged probe-FAIL / 18 probe-OK. The reuse guard (.staged_ok + olean-count==GPFS + exe) is
CORRECT and the "refuse to spend GPU on broken probe" guard fired correctly (zero wasted GPU) — the
envs were structurally complete; the probe (cold Mathlib load) failed under node RAM/IO storm, not
corruption. NOT a code bug; orchestration bug.
DECISION: resubmit each remaining arm as a SINGLE shard (ATP_NSHARDS=1, --array=0-0; --resume skips
done cells; 11:55h wall ≫ ~9h worst case for the 183-cell arm at n_workers=3) = 1 staging/arm, and
submit in small batches (≤4 concurrent) chained by Slurm --dependency=afterany so concurrency stays
capped WITHOUT a live watcher (survives session teardown). Hypothesis test: a 4-arm low-concurrency
batch should probe-OK and advance cells; gate the bulk chain on that.

## 2026-06-29 — eval concurrency: --exclusive single-shard waves
DECISION: run the 3-seed eval fill at strictly low concurrency (single-shard, --exclusive,
dependency-chained waves of 4) rather than sharded-parallel. RATIONALE: two consecutive
parallel attempts failed on node contention (bin-packing -> Lean/vLLM resource starvation),
and the scientific conclusion (two-model SFT null) is already locked + visible in the partial
aggregate, so completing the variance bars reliably outranks completing them fast. Long DeepSeek
arms (183/140/139 cells) kept single-shard to cap waves at 4 nodes; can shard-up the tail if
exclusive nodes prove plentiful.
