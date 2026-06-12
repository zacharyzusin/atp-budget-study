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
