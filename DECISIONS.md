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

## 2026-06-29 — Stage C = Option 1 (gated RL feasibility probe), user-decided
DECISION: after the two-model SFT null, proceed to a GATED GRPO RL feasibility probe (NOT full
Stage C, NOT close). Probe model = DeepSeek (stronger OOD basis). RATIONALE: SFT null upgrades RL
to the decisive exposure-bias experiment (SFT maxed conditional likelihood, floor didn't move;
on-policy RL optimizes the generation distribution directly). ~even c1(exposure-bound)/c2(capacity)
prior → detect c2 cheaply (~40 GPU-h) before any multi-day sweep; positive-EV both ways.
PRE-REGISTERED TRIPLE SUCCESS GATE (guards reward-hacking false positives) — a PASS needs ALL:
  (1) held-out VERIFIED solve-rate up (PRIMARY; not training reward — train-reward-up-but-held-out-flat
      = hack/overfit, not c1),
  (2) soundness rates (loophole/malformed/false-pos) do NOT degrade base->RL (first-class output),
  (3) no diversity collapse / KL blowup (track diversity + KL-to-base).
ESCAPE CLAUSE: a stall WITH a KL/diversity pathology = retune+re-probe, NOT c2; c2 concluded only
when reward fails to move on TRAIN problems WITHOUT a tuning pathology.
NEXT CHECKPOINT: bring concrete probe specs (problem subset, K, steps, reward shaping, KL coeff,
numeric threshold, GPU-h est) for user pressure-test BEFORE spending GPU, after 3-seed bars finalize.
Full memo: results/phase6/STAGE_C_DECISION.md (gitignored, local).

## 2026-06-29 (correction) — eval concurrency: bounded CPU/mem, NOT --exclusive
SUPERSEDES the earlier "--exclusive single-shard" decision. Topology: 13 big GPU nodes
(ins080-092 = 192 cpu, 8x A6000) + 2 small (ins093/094 = 64 cpu, 4x A6000); `free` QOS caps
cpu=80/job. So --exclusive on a 192-cpu node requests 192 > 80 -> QOSMaxCpuPerJobLimit, PERMANENT
block; it only fits the two 64-cpu nodes -> locked out 13/15 nodes. Real root cause of the
original contention was visible in ReqTRES: jobs reserved only cpu=4, so 5 co-located Mathlib
imports starved on CPU (1978s vs ~100s). FIX: drop --exclusive, reserve --cpus-per-task=32
--mem=96G per single-shard job. Fits QOS (32<=80), gives each job near-exclusive import speed,
lets up to 6 well-resourced jobs share a 192-cpu node without starvation, and unlocks the big
fleet. Validate-first: 2-arm probe wave (10944859-60) ungated; remaining 5 (10944861-65) gated
afterany so a bad resource model is caught before the bulk runs. Goedel arms (5) + d_mf_base_s1
already complete/running under prior submits.

## 2026-07-01 — Stage C probe design locked (user-approved) + rollout engine = HF generate
User approved STAGE_C_PROBE_SPEC.md §6 as recommended: (1) LoRA r=16 for the probe (cheap,
single-variable vs SFT arms; a clean LoRA-GRPO stall carries the pre-registered "retune/consider
full-FT before concluding c2" caveat); (2) held-out gate = Workbook slice for the probe, OOD
benchmarks reserved for the full run; (3) max_new_tokens=4096 rollout cap (F2/F3 short-closing
regime); (4) binary reward + soundness gate + 0.05 format bonus, NO progress shaping (minimize the
hacking surface G2 must police).
ENGINE DECISION: trl 0.17.0 GRPOTrainer's use_vllm=True path connects to a SEPARATE `trl
vllm-serve` process (its own GPU) — there is no in-process colocate in this version. Rather than
double the GPU footprint for a feasibility probe, the probe trains with HF generate
(use_vllm=False) on a single H100. Rollout throughput is lower, but (a) the ~35 GPU-h budget
absorbs it and (b) the DECISIVE G1 measurement is a SEPARATE held-out eval that runs base AND RL
through the identical vLLM eval harness, so the rollout engine cannot bias the go/no-go. A full
Stage C (if G1 passes) would switch to vllm-serve for throughput.
Reward is the eval Verifier verdict verbatim (soundness gate included) -> a training reward of 1.0
== an eval solve; verified inference-faithful in unit tests.

## 2026-07-02 — reduced GRPO subset (band=201) + min-samples decontam of cancelled-shard cells
Subset-gen overran (~130 GPU-h sunk, ~4x throughput miss). Rather than re-run, select from the
24617 cells on disk. Band [1,10]@k=16 = 201 eligible -> draw 130 train / 70 heldout (down from
256/200): a feasibility probe tolerates a smaller, noisier heldout; the §0(c) trainer smoke remains
the real go/no-go and G1 is the reportable gate.
`--min-samples 8` in phase6_select_subset.py: the band is by ABSOLUTE solve-count assuming ~k
samples, so the 750 partial-coverage problems (5-7 seeds) from the 6 cancelled shards must be
dropped or a low-coverage all-solve problem (e.g. 2/2) mis-bands as in-band. Coverage histogram has
a gap (7 -> 16), so min_samples=8 retains exactly the 1250 full-coverage problems. Deterministic +
audited in subset_summary.json (n_dropped_low_coverage=750, disjoint=True).

## 2026-07-02 — GRPO probe num_generations 8 -> 4 (memory-forced)
The 4096-tok completion x per_device(==num_generations) logits tensor blows the 80 GiB H100 at
num_generations=8 (~94 GiB peak, AFTER expandable_segments removed 35 GiB of fragmentation). Rather
than shrink max_completion_length (which must stay == the 4096 eval budget for probe fidelity), drop
the GRPO group size to 4. Group size 4 still yields a group-relative advantage (mean/std over 4
rollouts); it is a common GRPO setting and adequate for a feasibility probe. Applies to both the
smoke and the 150-step probe. If num_gen=4 still OOMs, next rung is max_completion_length, then
gradient-checkpointing/8-bit optimizer.

## 2026-07-02 — GRPO probe: 150->80 steps + short->burst (right-size vs the 40 GPU-h HARD cap)
Reconciled two pre-registered numbers that were in tension. STAGE_C_PROBE_SPEC §3 frames "up to ~150
steps (early-stop on gate signal or reward plateau)" as an UPPER bound; §5 sets GRPO ~20-25 GPU-h with
a HARD STOP at 40 (CLAUDE.md rule 8). Measured per-step cost from smoke 11079344 (train_runtime 903.7s
/3 = 301s/step at 8 rollouts/step = prompts_per_step 2 x num_gen 4). The probe runs 32 rollouts/step
(prompts_per_step 8 x num_gen 4). Generation is sequential grad-accum micro-batches (4x) and reward
verify is 12 parallel Lean workers (32 rollouts ~= 3 waves vs smoke's 1) -> per-step ~= 3-4x the smoke
= ~15-20 min/step -> 150 steps ~= 43-50 GPU-h, which BUSTS the 40 GPU-h hard stop AND short's 11:55
wall (only ~35 steps fit one window). So the queued 150-step/short job (11103370) was wrong on both
axes -> cancelled (never ran a step). Resubmitted as 11103388 on BURST at --max-steps 80 (fits the
20-25 GPU-h GRPO budget: 80 x ~18min ~= 24h ~= ~20-24 GPU-h), --num-generations 4 --prompts-per-step 8
--save-steps 20 --logging-steps 1 --seed 0. burst (14-day wall) completes 80 steps in ONE allocation
vs short's multi-day requeue-chain. Verified burst is NOT blocked by the delmore_priority reservation
(Flags=IGNORE_JOBS, ins067/delmore_lab1 only; burst Nodes include the H100s ins048-050) -> the user's
"if burst blocked, stay on short" condition does not apply; burst reason is plain "Priority". LR is
`constant_with_warmup` (flat 1e-6 after 3% warmup) so max_steps only bounds the stop -> if measured
per-step turns out cheap (~5-6min), 80 steps costs ~8 GPU-h and I can cleanly EXTEND (resume from
checkpoint with higher --max-steps, schedule stays flat). "Measure, don't guess": right-size the final
step count on the first ~4 real steps once it runs.

## 2026-07-03 — Phase 7 Track 1 (Mode 3) design choices
**Mode 1/2 trapped pass@B reconstructed offline, not re-run.** Every committed baseline config has
refinement.enabled=true (no logged pure "no-feedback" curve exists). Rather than burn GPU re-running a
dedicated no-refinement config, Mode 1 is recovered for free by filtering each cell's `agent_states`
attempts to kind=="propose" (a fresh, feedback-free sample, unconditioned on any prior refine attempt
in the cell) and recomputing cumulative cost — the same budget-independence trick Phase 4 used, applied
to attempt KIND instead of a budget cap. Mode 2 is just the existing `ProblemResult`s restricted to
trapped names. Conservative by construction: a refine-only solve counts Mode-1-UNSOLVED (that closing
depended on feedback Mode 1 never gets), so Mode 1 is never overcounted. Both are 0.000% on every
trapped set by definition (trapped = unsolved by all seeds even at 128k) — only Mode 3 needed new GPU.

**Verified-frontier state rides in `state.budget`'s extra keys, not a widened `Attempt` schema.** Mode
3 (`RegroundStepwiseAgent`) needs to carry its re-grounding prefix + depth across a Slurm requeue.
Widening the shared `Attempt`/`AgentState` dataclasses would touch every other phase's mining/analysis
tooling. Instead `state.budget = {**BudgetMeter.snapshot(), "_stepwise_prefix":..., "_stepwise_depth":...}`
— `BudgetMeter.restore` reads only `limit`/`spent`/`ledger` and ignores the rest, so this is a safe,
additive checkpoint format with zero schema risk to existing consumers.

**`tactic_body_prefix` translates `FailingStep.line` out of the model's restated header.** A whole-proof
model echoes its ENTIRE completion each round (header + prior prefix + new tactics — confirmed by the
Format-I guard's 99%+ parseable evidence), but `Verifier.verify` computes `FailingStep.line` over that
full text with no offset. Naively slicing the re-grounding prefix at that raw line number would include
(or double-declare) the header on the next round's continuation prompt. `tactic_body_prefix` locates
the first `:= by`, computes how many lines the header spans, and translates the failing line into a
body-relative offset before calling `verified_prefix`. Caught via a failing test (off-by-one: header
spans `count("\n")+1` lines, not `count("\n")`), not by inspection — TDD paid for itself here.

**Mode 3 requires an `elaborate` boundary-validation gate (found via a real-data smoke, fixed before
scaling).** "Elaborates without error up to line N" is NOT the same as "line N is a well-formed
single-goal stopping point" — a candidate prefix can end mid a `have h := by` block (no sub-proof
written), which is dangling, not verified-and-complete. Smoke 11110019's real Goedel/ProofNet# cell
(Artin__exercise_10_4_7a) hit exactly this: round 2 re-grounded on a dangling `have`-opener and the
model degenerated into prose instead of continuing tactics. Rather than reinvent dangling-detection
(Stage B's `closing_targets._closing_is_dangling` solves a related but offline/whole-proof-only
version of this), `RegroundStepwiseAgent` now requires `elaborate(theorem, prefix) -> bool`, wired in
the real driver to the exact Phase 6 harvest primitive (`ReplBackend.elaborate` on `<statement> := by
\n<prefix>\n  sorry`, requiring `errors==0 and len(sorries)==1`) — the same deep_state validation,
applied online. A rejected candidate leaves the frontier at its last validated value rather than
advancing onto a broken boundary. Caught by INSPECTING the real smoke's `agent_states` (not just its
exit code) — a clean exit code proved the harness didn't crash, not that the re-grounding logic was
sound; per feedback_validate_premise_before_building, this was fixed before scaling to the real
trapped-first eval since ProofNet#'s `have`-heavy proofs make the dangling case likely common.

## 2026-07-04 — Phase 7 Track 1: fresh-resample control needed before trusting a trapped solve
Mode 3's first real 32k-budget run closed 1/150 trapped ProofNet# problems (Rudin__exercise_5_3,
tokens_to_solve=7607) — the project's first-ever nonzero result on a trapped name. Before treating
this as mechanism evidence, inspected the cell's trajectory: it solved on `n_attempts=1`, a cold-start
whole-proof attempt, WITHOUT the re-grounding mechanism ever engaging (no frontier advance needed).
**This means the offline Mode 1/2 baseline (trivially 0/150, since it reuses each cell's ORIGINAL
logged trajectory) is not a fair control for what a FRESH re-sampling session achieves by chance
alone** — Mode 3's run used a different vLLM session/draw than the original baseline, so a solve on
attempt 1 could be ordinary sampling variance, not evidence that verified-state feedback helped.
Rather than report 1/150 as signal without this check, built a genuine control
(`phase7_freshcontrol_run.py`/`.sh`) that runs the EXISTING unmodified WholeProofAgent (whole-proof +
error-feedback refinement, zero re-grounding — the same protocol as the committed baseline) on the
identical trapped names, same fresh session/budget/seed. Only a Mode-3 result that either (a) beats
this control's solve rate, or (b) is attributable to solves with genuine multi-round frontier advance
(n_attempts>1, depth>0 before solving), counts as real signal toward c1. This is the same discipline
as the Stage C triple-gate escape clause: don't let a single favorable number bypass the check that
would tell the two hypotheses apart.

## 2026-07-04 — Mode 3's naive prefix cut discards genuine deep partial credit; added backoff search
Diagnostic on the completed Mode 3 @32k run (150 trapped ProofNet# cells, Goedel): re-grounding only
advanced the verified frontier in 1/150 cells, and that one solve (Rudin__exercise_5_3, n_attempts=1)
happened on a cold-start whole-proof attempt with re-grounding never engaging at all. The fresh-resample
control (job 11112414, plain WholeProofAgent, same trapped names, fresh session) got 0/150 — consistent
with the Mode-3 solve being ordinary sampling variance, NOT mechanism evidence.

Root-caused WHY re-grounding almost never engages, using only already-collected agent_states (no GPU):
- 35% of the 150 cells (52) DO reach deep partial progress on their best attempt (>=50% of the intended
  proof length; median relative depth across all attempts is 15%, but the deep-failure tail is real and
  sizeable) — so there IS real partial credit to work with on a meaningful subset, contra the initial
  read of "re-grounding has nothing to work with."
- But of those 52 deep-failure cells, the frontier only validated in 1. Inspecting concrete cells (e.g.
  Rudin__exercise_5_1, best attempt reached 91% depth = 62/68 lines) showed the SINGLE fixed cut
  `verified_prefix` computes (lines strictly before the reported failing line) lands mid a multi-line
  tactic combinator (`<;>`, `try { ... }`) 26.8% of the time across all 471 candidates checked — a
  genuinely dangling boundary, correctly rejected by the elaborate gate, but discarding real verified
  progress as a side effect, since a slightly SHORTER cut one or two lines back is often a perfectly
  clean ancestor state.
- Fix: added `verified_prefix_candidates`/`tactic_body_prefix_candidates` (atp/agents/stepwise.py) —
  instead of one fixed cut, try progressively shallower cuts (deepest-first, capped at 15 non-blank
  backoffs to bound Lean-call cost) and take the first that both increases depth AND passes the
  elaborate gate. Test-first: 4 new pure-function tests + 1 new agent-integration test (backs off past
  a dangling `<;>` cut to the clean ancestor one line back) — all pass; full fast suite (543 tests)
  still green.
- This is a real design correction, not a tuning tweak: the ORIGINAL Mode 3 numbers (1/150, frontier
  advanced 1/150) undersell the mechanism because the boundary-finder was too naive to use most of the
  deep partial credit that was actually available. Re-running Mode 3 @32k with the fix before drawing
  any conclusion about c1/c2-style "does re-grounding help" — the pre-fix run is not yet a valid read.

## 2026-07-05 — Stage C GRPO RL probe result: c2 (capacity ceiling), the triple gate closes clean
G1/G2/G3 computed via scripts/phase6_stage_c_gate.py on the completed base-vs-RL held-out eval
(70 problems x 8 seeds, budget 8192): pass@1 base=0.586 RL=0.570 (Delta=-1.6pp, need >=+5pp -> G1
FAILS); unsound base=9.58% RL=6.17% (Delta=-3.4pp, need <=+2pp -> G2 PASSES, RL if anything cleaner);
diversity ratio 1.015, mean KL=0.0021 (both well inside ceiling -> G3 PASSES). Training cum.
solve-rate was flat for all 80 steps (0.17-0.27 oscillation, no trend) -> the pre-registered "reward
flat, no pathology" branch -> c2, not a mis-tuned stall (the retune-and-reprobe escape clause does
not apply). Full writeup + GPU-h accounting (~15-18 GPU-h total, under the 35 GPU-h budget / 40 GPU-h
hard stop): results/phase6/STAGE_C_RESULT.md.
Reading: this is the THIRD independent confirmation of the execution-floor thesis (after
scaffolding/search Phase 0-5, and SFT Stage A/B's exposure-bias-but-no-floor-move), via a third
mechanism (RL against the true verifier reward, not just conditional likelihood). Per the
pre-registered LoRA-r16 caveat (STAGE_C_PROBE_SPEC.md §6.1), this is "capacity ceiling under the
probe's constraints," not an airtight permanent close — full-FT RL is the reopening lever if this
arc is revisited. Folds into Phase 7 as Track 4, closed; no further Stage C GPU spend planned unless
Track 1 (Mode 3) findings change the priority calculus.

## 2026-07-05 — Mode 3 alone can't resolve the fork; built Mode 4 as the strong disambiguator
Advisor-quality pushback on the STEPWISE.md check-in: Mode 3 (re-grounds state, then free-runs a
WHOLE continuation) has a confound Mode 4 doesn't — "Mode 3 engages but doesn't close" is consistent
with BOTH (a) exposure bias isn't the bottleneck, and (b) exposure bias IS the bottleneck but
single-shot re-grounding is too weak (the continuation can drift again immediately). Mode 3 alone
falsifies only the weak fix, not the hypothesis. Correct sequencing: run Mode 4 (true stepwise, one
tactic per call, state-conditioned via elaborate every step) on exactly the 19 cells where Mode 3 v2
engaged (advanced the frontier) but didn't close — the ideal, cheapest test set, since we already know
these get deep but can't finish under whole-continuation re-grounding.

Built `atp/agents/tactic_stepwise.py` (TacticStepwiseAgent, `take_tactic_step` pure-core) test-first
(9 tests, full suite 552 green, ruff clean): each step proposes exactly one tactic conditioned on the
TRUE current goal state (from `ReplBackend.elaborate`, never a self-generated/drifted one); the state
only ever advances off an ACCEPTED tactic (validated via elaborate before commit); final closure is
re-checked through the real soundness-gated `Verifier.verify` (elaborate's bare "0 sorries left" isn't
sufficient — must also pass the loophole/sorry/admit gate). Real driver
`scripts/phase7_tactic_run.py` + `slurm/phase7_tactic_run.sh` mirror Mode 3's runner/slurm pattern
(same restartable-sweep machinery, same results/<run>/{problems,agent_states}/ layout), with an added
Format-E pre-flight smoke (TacticTemplate has never been format-validated live before this run) that
FATALs before spending real GPU if the base model doesn't emit a usable bare single tactic.

Extracted the 19 Mode-3-v2-engaged cell names (frontier depth>0, all unsolved) to
scratch/phase7/mode3_engaged_goedel_proofnet.txt. Launched job 11112957 (budget 32000, max_steps=40,
retries_per_step=4) on exactly this 19-cell set. This is THE decisive read for the Track 1 fork:
Mode 4 closing any meaningful fraction flips the fork to GO (exposure bias, single-shot re-grounding
too weak); Mode 4 also nulling makes the capability-floor claim airtight (fails to close even under
full step-by-step ground-truth state feedback), closing the "did you try stepwise?" objection.

## 2026-07-05 (cont.) — Mode 4's first result (0/19) is NOT trustworthy yet — format mismatch suspected
Job 11112957 completed in only 3:50 (suspiciously fast for 19 cells x up to 40 steps x 4 retries)
with 0/19 solved AND every single cell logging `stop_reason=no_progress, n_attempts=0` — meaning
EVERY cell got stuck at step 0, never accepting even ONE tactic across 4 retries. The Format-E
pre-flight guard's own sample completion for a toy theorem was `'theorem probe (n : Nat) : n + 0 =
n'` — the model echoing back a theorem HEADER, not emitting a bare tactic, despite the instruction.
This is the same failure class as [[feedback_inference_mode_match]] (wrong inference mode ≠ model
incapability) — Goedel-Prover-V2-8B is almost certainly trained overwhelmingly on WHOLE-PROOF
completions and defaults to that habitual style even when asked for a single tactic; TacticTemplate
has never been format-validated live before this run, and the guard's own assertions (non-empty, no
code fence, <200 chars) were too weak to catch "plausible-length but semantically wrong" output.
**Do NOT read 0/19 as evidence for the capability-floor claim** until this is resolved — it may be
entirely a prompt/extraction artifact, not a real test of the model under state-grounded stepwise
generation. Built scripts/phase7_format_e_diagnostic.py + slurm/phase7_format_e_diagnostic.sh to
print RAW (unextracted) completions against 3 real trapped goal states (job 11112959, ~15-20 min,
diagnostic only, no sweep) before deciding whether to fix the prompt/extraction and re-run, or
whether the format genuinely doesn't transfer to this model at all (itself a real, reportable
finding, but distinct from "even step-by-step ground truth doesn't help").

## 2026-07-05 (cont.) — Root cause confirmed + fixed: Goedel-Prover-V2 always reasons before answering
Diagnostic job 11112959 confirmed the format mismatch directly: Goedel-Prover-V2-8B, given the
TacticTemplate goal-state prompt, NEVER emits a bare tactic — it always produces a long markdown CoT
explanation first, exactly like its native whole-proof completion style, ignoring the "output only
the tactic" instruction. Crucially, on the one example that didn't get truncated (256-token budget),
the model DID surface the correct answer: `### Next Tactic: \`simp_all [IsSimpleGroup]\`` — but the
naive extractor (first-non-empty-line) grabbed the whole markdown line as "the tactic," which then
correctly failed every elaborate check (garbage syntax), explaining n_attempts=0 on every cell.
Two other examples never reached ANY answer within 256 tokens — still mid-CoT when truncated.

Fix (test-first): `TacticTemplate.extract_proof` (atp/models/templates.py) now matches the
`` `### Next Tactic: \`<tactic>\`` `` marker FIRST, before falling back to the original bare/fenced
parsing — regression test uses the REAL captured completion as fixture
(test_tactic_extract_proof_pulls_the_answer_out_of_a_reasoning_completion). Bumped Mode 4's
sample_max_tokens from 64 -> 768 (CLI-configurable via --sample-max-tokens,
scripts/phase7_tactic_run.py) so the model has room to finish its CoT and reach an answer at all —
the previous default was cutting it off mid-reasoning on 2/3 real cells tested, independent of the
extraction bug. Strengthened the Format-E guard (slurm/phase7_tactic_run.sh) to reject extracted
text containing '#' or the self-referential word "tactic" (not just check length/fences), so a
future format regression fails loudly instead of silently producing another 0/N run.
Full suite (553 tests) green, ruff clean. Re-running the diagnostic (job 11112963, 768 tokens) on
the two examples that previously truncated before answering, to confirm the fix generalizes, before
re-launching the real 19-cell Mode 4 run.

## 2026-07-05 (cont.) — Fix insufficient: this model's answer shape is structurally unpredictable
Re-ran the diagnostic (job 11112963, 768 tokens) on the 2 examples that previously truncated. The
marker-parse fix + bigger budget did NOT converge them to a usable tactic:
- Herstein__exercise_2_10_1: model launched a multi-`have` compound proof SKETCH inside an unclosed
  fenced block (truncated before the closing ```) — extract_lean_block correctly returns None (no
  complete fence), falls back to the raw first line = bare "### Next Tactic" header (no colon+backtick
  this time, so the marker regex doesn't fire either).
- Rudin__exercise_3_21: still 100% prose analysis at 768 tokens, no code emitted at all.

Reframing: this isn't a fixable extraction bug, it's a genuine mismatch between Goedel-Prover-V2-8B's
trained behavior (whole-proof reasoning, sketches multi-step solutions) and Format E's premise (one
atomic tactic per turn). The model's answer shape is unpredictable per-goal: sometimes a clean
one-liner, sometimes a multi-step compound sketch, sometimes unconverged prose — no fixed token
budget or regex reliably normalizes all three. Diminishing returns on further prompt/extraction
engineering without changing approach (e.g. line-by-line elaborate-validating a multi-step sketch,
or trying a much larger budget) — surfacing to the user before sinking more effort in, since this
is a genuine "how much further investment" judgment call, not a routine bug fix.

## 2026-07-05 (cont.) — Time-boxed oracle-extraction fix (ONE pass, per plan), then pivot regardless
Built the one authorized correction: `candidate_tactic_lines` (atp/models/templates.py) extracts
EVERY plausible tactic line from a completion (marker match first, then all lines from a fenced
block — closed OR unclosed via a new `_partial_fence_body` tail-grab — then raw text as last
resort), and `take_tactic_step`/`TacticStepwiseAgent._propose` now oracle-validate (via the SAME
`elaborate` check already used to accept/reject a step) every candidate from ONE completion in
order, instead of committing to a single first-line guess. Test-first using the 3 REAL captured
completions as fixtures (marker case, unclosed-multi-have-sketch case, pure-prose case) — all
recover the right candidates or correctly yield nothing to fabricate from prose. Full suite (557
tests) green, ruff clean. This is a measurement-instrument correction, not a research direction, per
the explicit time-box: one pass, no further regex iteration regardless of outcome.
Relaunched the SAME 19 Mode-3-engaged Goedel/ProofNet# cells with this fix (job 11114507,
results/phase7/goedel_proofnet_mode4_engaged19_v2). Whatever this returns is the final word on
Goedel Mode 4 — either a fair (likely still null) number, or confirmation the extraction still
can't reliably decompose Goedel's output, in which case "Goedel-Prover-V2-8B does not cleanly
decompose into single-tactic turns" is itself recorded as a finding (whole-proof provers structurally
can't exploit stepwise re-grounding the way a tactic-native model could) and Track 2's BFS-Prover-V1-7B
becomes the real disambiguator, pulled forward ahead of the rest of the model-zoo work.

## 2026-07-05 (cont.) — Pulled BFS-Prover-V1-7B forward from Track 2, regardless of Goedel outcome
Verified against ByteDance-Seed/BFS-Prover-V1-7B's actual model card (not assumed): it's a raw
/v1/completions model, NO chat template, trained format is exactly `"{state}:::"` -> tactic
(card example: "h : x = y + 2 ⊢ x - 1 = y + 1:::" -> "simp [h]"). Genuinely tactic-native (unlike
Goedel), so Mode 4 is in-distribution for it. max_position_embeddings=4096 (config.json); pinned
revision 750e39030cf25f4af4fcdc81d358123659656cbe (HF API sha, 2026-07-05).

Also caught: the OLD `TacticTemplate` (verbose instruction-following prompt, assumed to be
"BFS-Prover's format" per its misleading docstring since 2026-06-04) was NEVER actually BFS-Prover's
real trained format — a speculative prompt that was never checked against the model card until now.
Added `BFSProverTemplate` (atp/models/templates.py) matching the real format exactly, test-first (4
new tests using the card's own worked example). Registered as prompt_template="bfs_prover" (widened
the config schema's Literal). Renamed TacticTemplate's docstring to be honest about what it actually
is (a generic instruction-following ablation prompt, not BFS-Prover's real format).

Built configs/proofnet_baseline_bfsprover.yaml — reuses Goedel's Lean pin (v4.9.0-rc1) rather than a
new toolchain, since BFS-Prover-V2's sibling card documents Lean 4.10.0 (close vintage); to be
confirmed empirically via the Format-guard smoke, not assumed. Generalized
scripts/phase7_format_e_diagnostic.py + slurm/phase7_format_e_diagnostic.sh to read model repo/name/
max-tokens from the config (was hardcoded to Goedel) so the same smoke harness works for any model.
Launched job 11114546 (smoke: 3 real trapped goal states, max_tokens=64) to validate format +
Lean-pin compatibility before any real BFS-Prover Mode 4 run.

## 2026-07-05 (cont.) — Goedel Mode 4: the fair, final number (time-box honored, stopping here)
Job 11114507 (Mode 4 v2, oracle-validated multi-candidate extraction) completed: 0/19 solved, same
as before — BUT now with genuine per-step engagement instead of a pure extraction artifact: 6/19
cells got >=1 real accepted tactic (up from 0/19 pre-fix), one (Pugh__exercise_2_92) reaching 10
genuine accepted steps before getting stuck (stop_reason=no_progress on every cell — none reached
max_steps=40 or closed). The remaining 13/19 got ZERO accepted steps even with oracle-validated
multi-candidate extraction across up to 4 retries each with many candidates per completion.

Per the pre-registered stopping rule: the fix recovered usable steps -> this IS the fair, final
Goedel Mode 4 number, no further extraction iteration. Reading: even where re-grounding gets genuine
traction (real per-step engagement, occasionally many steps deep), it still converts to zero closes
on this 19-cell set — consistent with (not proof of, but consistent with) the capability-floor
reading. The 13/19 zero-engagement cells reinforce the "whole-proof reasoning provers don't cleanly
decompose into stepwise turns" finding as a real, separate, reportable result — recorded now,
independent of whatever BFS-Prover's tactic-native run shows.

## 2026-07-05 (cont.) — BFS-Prover format + Lean pin CONFIRMED compatible; real Mode 4 run launched
Elaborate-validated both smoke tactics directly against our existing Lean pin (job 11114560, no GPU
needed): both `intro h` and `have := Fact.mk hp` elaborated cleanly (errors=0, produced a real next
goal state) — the model's raw single-line outputs are genuinely legal Lean tactics under our v4.9.0
mathlib pin, confirming both the format (BFSProverTemplate) and the Lean-pin reuse decision are
sound. No new toolchain needed.

Caught + fixed a real bug before it burned GPU: slurm/phase7_tactic_run.sh hardcoded
"Goedel-LM/Goedel-Prover-V2-8B" in the vLLM serve command AND used a Goedel-specific markdown-based
Format-E guard (TacticTemplate + "###"/fence detection) — irrelevant to BFS-Prover's raw-completion
format. Job 11114561 failed immediately (served the wrong model with the wrong revision). Fixed:
generalized the serve block to read hf_repo/name from config (mirrors the diagnostic script's
earlier fix), and REPLACED the markdown-heuristic guard with a model-agnostic elaborate-validation
guard — proposes a candidate, checks it via the SAME `elaborate` oracle the real agent uses, and
requires genuine acceptance (not just "doesn't look like markdown"). This is a strictly better guard
for ALL future Mode 4 runs, not just BFS-Prover's.

Launched the real disambiguator (job 11114562): BFS-Prover-V1-7B, Mode 4, on the FULL 150-cell
Goedel-trapped ProofNet# set (budget 32000, max_steps=64, retries_per_step=4) — the well-defined
test per the plan: can a genuinely tactic-native model, via verified step-by-step state feedback,
close problems Goedel-Prover-V2 could not solve at any budget up to 128k. This is the number that
decides the fork.

## 2026-07-05 (cont.) — Format guard fixed: retry across fresh samples, not just one
Job 11114562 FAILED the Format guard on its single sample ("rw [IsSimpleGroup]" — an invalid tactic
for that state, plausible sampling variance at temperature=1.0, not a format/pin problem; the SAME
theorem got a valid tactic on both smoke attempts earlier). The guard as written only tried ONE
completion — too fragile against ordinary stochastic variance, and inconsistent with the real
agent's own retries_per_step=4. Fixed: guard now retries up to 4 FRESH samples (mirrors the real
run's tolerance) before failing. Resubmitted as job 11114575.

## 2026-07-05 (cont.) — Final correction pass: stagnation rejection + beam-with-backtracking + template bug
Per explicit instruction: this is the LAST correction before the disambiguator number is final.
Three bounded, well-defined fixes, all necessary (not open-ended hunting):

1. **Stagnation rejection**: a candidate tactic that elaborates cleanly but produces a goal state
   IDENTICAL to the current one (e.g. `rw [mul_comm]` cycling `a*b`/`b*a` forever — the exact bug
   that produced two fake "64-deep" cells in job 11114575) is now REJECTED, not accepted. Real
   verified progress is required to advance, not just syntactic legality.
2. **Beam-with-backtracking**: added `BeamTacticStepwiseAgent` + `expand_node`
   (atp/agents/tactic_stepwise.py) — an explicit DFS-with-backtracking over a beam of up to
   `beam_width` accepted candidates per node (checkpointed as a JSON-safe stack for restart safety),
   replacing the old `TacticStepwiseAgent`'s single irreversible greedy path. This is the fair test
   for a model whose designed capability IS best-first search with backtracking (BFS-Prover) — a
   greedy walk was under-testing it, the same class of confound already fixed once for Mode 3 -> 4.
   Test-first: 6 new tests (expand_node beam-capping/dedup, stagnation rejection, backtrack-recovery,
   budget/checkpoint/resume of the stack) — full suite (563 tests) green, ruff clean.
3. **Template selection bug**: `scripts/phase7_tactic_run.py`'s `build_tactic_solve_fn` hardcoded
   `TacticTemplate()` regardless of `config.model.prompt_template` — meaning the just-completed
   BFS-Prover run (job 11114575) actually used the generic verbose instruction-following prompt, NOT
   `BFSProverTemplate`'s native `"{state}:::"` format the model was actually trained on (the smoke/
   guard scripts already used `template_from_config` correctly; only this real-run script had the
   bug). Fixed to use `template_from_config(config)`. `TacticStepwiseAgent`/`take_tactic_step` (the
   greedy path) are left in place, unused by this script now, since Goedel's already-recorded Mode 4
   number used them and isn't being rerun.

`--beam-width` threaded through scripts/phase7_tactic_run.py and slurm/phase7_tactic_run.sh (new
positional arg, default 3). The old job 11114575 result (0/150, greedy, wrong template, stagnation
bug) is SUPERSEDED — not to be cited. Re-launching the corrected run now: this is the final
disambiguator number per the pre-registered stopping rule (one more run, no further iteration
regardless of outcome).

## 2026-07-05 (cont.) — FINAL disambiguator number: BFS-Prover 0/150, fair test confirmed
Job 11114731 (beam_width=3, stagnation rejection, correct BFSProverTemplate) completed: **0/150
solved**. Engagement jumped to 77/150 cells (51%) reaching real oracle-validated progress (up from
33/150 pre-fix, itself up from 0/150 on the original naive greedy run) — confirms BFS-Prover
genuinely operates as a tactic-native searcher under this harness, the fair test the plan called for.

Residual artifact found and quantified (not fixed further, per the explicit one-more-run stopping
rule): of the 9 cells that hit max_rounds=64, 4 settled into a short state-oscillation (e.g. `apply
le_of_sub_nonneg` <-> `apply sub_nonneg_of_le`, a 2-cycle the single-step stagnation check can't see
since each individual transition DOES change the state) — real Lean-legal steps, but not converging
search. The other 5 show genuinely varied exploration (5-18 distinct tactics). 4/150 (2.7%) cells
affected; the other 141 stopped via legitimate no_progress (backtracking exhausted the beam at every
open node) — the fix worked as intended for the overwhelming majority of the set.

**This is the final disambiguator number per the pre-registered stopping rule.** BFS-Prover-V1-7B —
a genuinely tactic-native model, given full step-by-step VERIFIED state feedback (never a drifted
self-generated state), searching with a small beam and backtracking away from dead ends (its actual
designed capability, not a greedy walk), on a fair budget, with no-op/stagnation rejected — still
closes ZERO of the 150 ProofNet# problems Goedel-Prover-V2 could not solve at any budget up to 128k.

Combined with the fair Goedel Mode 4 result (0/19 engaged-cell subset, real per-step engagement,
still no closes) and the whole-proof-provers-don't-decompose finding, this closes the "did you test
stepwise properly?" objection as completely as this project can: two different generation mechanisms
(single-shot re-grounding, step-by-step search), on a model architecturally built for exactly this
mode, with format/pin/stagnation/backtracking confounds identified and fixed one at a time as found
— all null. Writing up results/phase7/STEPWISE.md with the full arc next.

## 2026-07-05 (cont.) — Phase 8 Cluster A: DeepSeek-Prover-V1.5 does NOT share DeepSeek-Prover-V2's
## pin — it shares GOEDEL's
The Phase 8 plan (atp-phase8-plan memory) assumed the V1.5 triple (Base/SFT/RL) — being from
DeepSeek, and the model DeepSeek-Prover-V2 already sits on `deepseek-lean-env` — would triage into
the "DeepSeek pin" bucket. Checked rather than assumed (this project's repeated lesson): walked
`deepseek-ai/DeepSeek-Prover-V1.5`'s GitHub `.gitmodules` -> mathlib4 submodule commit via the GitHub
Contents API. It resolves to `xinhjBrant/mathlib4@2f65ba7f1a9144b20c8e7358513548e317d26de1` — the
EXACT commit already pinned as GOEDEL's env in base.yaml (`leanprover/lean4:v4.9.0-rc1`), confirmed
by fetching that commit's own `lean-toolchain` file directly. Likely explanation (not verified
further, doesn't change the decision): `xinhjBrant` is presumably the DeepSeek-Prover-V1.5 author's
own mathlib fork from 2024; Goedel-Prover (built ON TOP of DeepSeek-Prover-V1.5-Base per its own
model card/paper) simply inherited the same fork+commit rather than re-pinning. DeepSeek-Prover-V2
(2025, a much later, different-architecture Qwen3-based model) moved to a standard-mathlib pin
instead — the "two DeepSeek pins" observation in atp-phase8-plan's Cluster-A description is real, but
the split is generational (V1.5-era fork vs V2-era standard), not "V1.5 == V2's pin, everything else
differs." PRACTICAL UPSHOT: the V1.5 triple, Goedel-Prover-SFT, and (best-evidence, unconfirmed) STP
all reuse the Goedel Lean env UNCHANGED (base.yaml, already built, `results/_lean_env_ready.txt`) —
no new Lean env to build for Cluster A's causal core. Only DeepSeek-Prover-V2 itself needs
deepseek-lean-env, exactly as already wired.

Added two new prompt templates for this (`atp.models.templates.DeepSeekV15Template`,
`GoedelSFTTemplate`) rather than reusing `WholeProofTemplate`: both V1.5 and Goedel-Prover-SFT are
RAW-completion models (no chat template, no proof-plan preamble) — verified against
`quick_start.py` / `eval/step1_inference.py` in their respective GitHub repos — structurally distinct
from `WholeProofTemplate`'s chat-driven, PLAN_SUFFIX-carrying prompt (Goedel-Prover-V2's own,
later, reasoning-tuned format). Registered both in `ExperimentConfig`'s `prompt_template` Literal.

## 2026-07-05 (cont.) — Phase 8 Cluster A smoke: stopped before downloading ~42GB, shared FS at 99%
Submitted 3 tiny single-shard GPU smoke jobs (slurm/sweep_array.sh) for the V1.5 triple to confirm
"loads via vLLM + verifies" per check-in #1. First mistake caught fast: `sbatch` without an explicit
`--array` override picked up the script's own `#SBATCH --array=0-7%8` default, launching 8 shards per
job (24 total) instead of 1 — killed within ~5s of all reaching state CG, ~0 GPU-h actually spent.
Resubmitted with `--array=0`. The Lean side of all three passed cleanly (env reused, trivial/norm_num/
false probe all correct) — direct runtime confirmation of the pin finding above. vLLM itself failed
immediately for Base/SFT: `sweep_array.sh` defaults `HF_HUB_OFFLINE=1` (CLAUDE.md storage-hygiene
rule: serve from a pre-staged cache, never trigger a live download inside a job) and none of these 5
models have ever been cached to scratch/hf-cache — vLLM couldn't even find a config.json offline.
Cancelled the RL job (still mid Lean-stage) before it hit the identical wall.

This is where autonomous execution stops per feedback_atp_autonomy: `df -h /insomnia001` reads 99%
used, 58G free, and that's the WHOLE shared cluster mount, not a per-user quota — downloading the
triple's weights (~13.8GB x 3 = ~41.5GB, from HF API blob sizes) would consume the large majority of
the remaining shared headroom. That's a different risk class than this project's own >50-GPU-h ask
threshold (this is ~0 GPU-h so far) — it's "affects shared infrastructure other users depend on,"
which this project's own working norms (and plain good sense on a 99%-full shared FS) say goes to the
user first, not a unilateral call. Surfacing in PROGRESS.md/to the user rather than proceeding.

## 2026-07-06 — Leanabell second-pair design choices
1. **Pair choice**: built GD-SFT -> GD-RL (Leanabell's own pre-RL checkpoint -> its RL checkpoint),
   not plain Goedel-Prover-SFT -> Leanabell-GD-RL as the coordinator's message literally phrased it.
   Reason: GD-SFT is GD-RL's ACTUAL base checkpoint (continual-trained on a hybrid dataset before RL,
   per the paper's own README) — comparing GD-RL against Goedel-Prover-SFT (a different lab's
   checkpoint, one stage further upstream, without Leanabell's own continual-training stage) would
   reintroduce a multi-variable confound, exactly what a "second independent lineage pair" is supposed
   to avoid. GD-SFT->GD-RL isolates the RL step alone.
2. **Pin**: reused the Goedel Lean pin as a best-evidence default (same inference class as the
   already-accepted `configs/stp_proofnet.yaml` precedent) since the Leanabell-Prover GitHub repo has
   no code (README + figures only) to independently confirm a mathlib commit from, but the paper
   explicitly continual-trains from Goedel-Prover-SFT and its own eval table is directly comparable to
   3 other papers already pin-confirmed to the same fork+commit in this repo. NOT proven — logged as
   inferred in both the configs and ZOO.md.
3. **Prompt format**: chose `whole_proof` (proof-plan preamble + chat_completions) over the raw-
   completion V1.5/Goedel-SFT style, based on config.json's `max_position_embeddings=8192` (vs the raw-
   completion models' 4096), a real HF tokenizer chat_template (absent on the raw-completion models),
   and the paper's own "reasoning model" framing. Contract-tested via GPU smoke before trusting it
   (coherent Lean-tactic output, correctly verifier-rejected when incomplete) rather than shipping the
   inference purely on the architecture-signal reasoning — this project's `feedback_inference_mode_match`
   lesson (wrong format cost -36pp once) makes an empirical check here non-optional.
4. **Battery budget scope**: coordinator's message literally requested 2k/8k/32k/128k. Estimated the
   128k tier at 300+ incremental GPU-h (using proofnet_baseline.yaml's own ~76 GPU-h/model/benchmark
   documented cost), crossing the 50-incremental-GPU-h ask-first rule. Asked the user rather than
   either silently complying (large, potentially unwanted spend) or silently capping without asking
   (overriding an explicit instruction unilaterally) — user approved capping at 32k to match the V1.5
   triple's own battery ceiling, which also has the methodological benefit of keeping both pairs'
   floor tables comparable at the same budget cap rather than different ceilings.

## 2026-07-06 (cont.) — Fixed extract_proof to strip a re-echoed opening fence (DeepSeekV15Template/GoedelSFTTemplate)
Re-smoked Leanabell-Prover-GD-SFT/GD-RL on the corrected `goedel_sft` raw-completion template
(coordinator-directed fix). Out-of-context "unknown namespace" errors dropped to 0% (confirms that
failure mode was specifically the whole_proof/chat_completions mismatch, now gone). But a NEW,
narrower issue showed up: 15.9% of completions still start with a leftover ` ```lean4 ` fence marker
— not from truncation this time, but because Leanabell's completions sometimes RE-ECHO the prompt's
own opening fence at the start of their own output instead of continuing straight into code (the
prompt already opens the fence; the model isn't supposed to repeat it). `DeepSeekV15Template`/
`GoedelSFTTemplate.extract_proof` only ever stripped a TRAILING fence (documented assumption: "the
completion only ever carries a bare closing fence") — an echoed leading fence fell straight through
to the Lean verifier, guaranteeing a parse error on every such attempt.

Fixed by adding `_strip_echoed_opening_fence` (templates.py) and calling it in both templates'
`extract_proof`, ahead of the existing trailing-fence strip. This is a strict generalization, not a
behavior change for DeepSeek-Prover-V1.5/Goedel-Prover-SFT's own traffic (confirmed no such
leading-fence pattern in their existing baseline data — the regex only fires when a completion
actually starts with a fence marker, a no-op otherwise). Test-first: 4 new tests in
`test_models_templates.py` (2 per template) confirming the strip fires correctly AND that the
existing trailing-fence/no-fence cases are unchanged. Full `pytest -q` green before re-running any
GPU job.

## 2026-07-06 (cont.) — Fixed `PantographBackend._build_source`: reconstruct the theorem header for continuation-style proofs
Root cause of the "0% again after the wiring fix" incident (PROGRESS.md same date, traced byte-exact
from real `p8battery2_*` cells): `_build_source` had exactly two branches — "model emitted a complete
file" (has its own `import` line -> use as-is) or "prepend imports/opens, then the proof verbatim."
Neither branch ever reconstructed the `theorem NAME <binders> : <goal> := by` declaration. This is a
no-op for `WholeProofTemplate` (Goedel-V2/DeepSeek-V2 — the model re-emits the whole fenced block
including its own theorem restatement, hitting branch 1) but silently drops the theorem entirely for
every continuation-style template (`DeepSeekV15Template`/`GoedelSFTTemplate`), where the model
continues directly after `:= by` and is never asked to restate the theorem. Bare tactics landing at
the top level of a Lean file are a guaranteed parse error (`unexpected identifier; expected command`)
— not a real proof failure.

**Fix**: added a third case, gated on whether the (import-less) proof text already contains its own
`theorem`/`lemma`/`example` declaration (reusing the exact `_DECL_RE` pattern verifier.py already uses
for its own "no_goal" check — duplicated as a module-level constant in backends.py rather than
imported, since verifier.py imports FROM backends.py and importing the other way would be circular).
If the proof declares its own goal, behavior is unchanged (existing branch 2). If it's a bare
continuation, reconstruct `<imports>\n<opens>\n\n<theorem.statement> := by\n<proof>` using
`Theorem.statement` (already the right text, no `:= by`/`sorry` — no need to reconstruct it from
scratch).

Test-first: `test_build_source_reconstructs_theorem_header_for_continuation_only_proofs` uses the
EXACT real example traced live (`Artin__exercise_10_1_13`, DeepSeek-Prover-V1.5-SFT) — confirmed it
fails against the pre-fix code (no theorem line anywhere in the assembled source), passes after the
fix. `test_build_source_whole_proof_branch_is_unaffected_by_the_fix` locks in that the existing
complete-file branch stays byte-identical (Goedel-V2/DeepSeek-V2 unaffected). Full `pytest -q` green.

## 2026-07-06 (cont.) — CAUGHT BEFORE WASTING THE RE-VERIFY PASS: the real production backend is `ReplBackend`, not `PantographBackend` — same bug, different class, fixed there too
Before writing the re-verification script, checked which backend `eval/run.py` actually constructs
(`_verify_worker` / `Verifier.from_config` call chain) — its own module docstring says it plainly:
"ReplBackend supersedes PantographBackend for the pin: PyPantograph has no v4.9.0-rc1 release
(DECISIONS.md 2026-06-05)." **`PantographBackend._build_source` (fixed above) is NOT the code path
any real sweep in this project has ever exercised** — fixing it alone would have been a no-op; the
re-verification pass would have "fixed" nothing.

Checked `ReplBackend._build_repl_source` (`src/atp/lean/repl.py`) — confirmed the EXACT SAME bug,
independently implemented: it strips `import` lines (legitimate — Mathlib is preloaded in the REPL's
base env 0) and preserves/prepends `open` clauses, but **never reconstructs the `theorem ... := by`
declaration either**. Same fix, same discipline: test-first
(`test_build_repl_source_reconstructs_theorem_header_for_continuation_only_proofs`, the EXACT real
traced `Artin__exercise_10_1_13` example — confirmed it fails pre-fix), gated on `_DECL_RE` (imported
from `atp.lean.backends` rather than re-duplicated a third time — `repl.py` already imports several
names from `backends.py`, no circularity). Regression test
(`test_build_repl_source_leaves_self_contained_proofs_unaffected`) locks in the untouched case byte-
for-byte. Full `pytest -q` green (50 lean-repl + lean-verifier tests total across both files).

**Both classes now fixed and tested. The re-verification pass (PROGRESS.md, next entry) re-runs
`ReplBackend.verify` — the actually-used class — against the already-collected completions.**

## 2026-07-06 (cont.) — Documented follow-up debt: no `stop` sequence is ever configured (not fixing now)
Per the coordinator's instruction: logging this as real, project-wide, NOT blocking, NOT being fixed
in this pass. `VLLMClient.from_config` (`src/atp/models/client.py`) never sets `self.stop` from any
config field, and `whole_proof.py`'s `_step()` call to `self.client.generate(...)` never passes a
`stop` kwarg either — `self.stop` stays at its `()` default for every template, always. Confirmed via
the 3 traced DeepSeek-Prover-V1.5-Base examples (PROGRESS.md 2026-07-06): the model gives up with a
literal `sorry` as its first tokens, closes the fence, then (with nothing to stop it) rambles into
unrelated hallucinated forum/hint-page text for the rest of its budget. Checked carefully: this does
NOT explain those 3 examples' 0% (the real content is just `sorry` either way — no hidden correct
attempt is buried in the ramble that a stop sequence would recover), so it is NOT the root cause of
the Base/SFT/RL 0% incident (that was `_build_source`/`_build_repl_source`, fixed above). It IS a
real, wasted-budget inefficiency worth fixing eventually — a `stop=("\n```",)` (or template-specific
equivalent) for continuation-style templates would save tokens/GPU-h and produce cleaner failure
feedback, and might occasionally rescue a genuine second attempt in OTHER cells not sampled here. Not
fixing now — out of scope for this pass, flagged for a future session.

## 2026-07-06 (cont.) — BLOCKER #4 CONFIRMED AND FIXED: DeepSeekV15Template/GoedelSFTTemplate were missing `import Aesop` + `set_option maxHeartbeats 0`
Per the coordinator's instruction ("before accepting 0% as real, check the model's own published
numbers and byte-exact prompt format — same check that caught the Leanabell mismatch, never actually
done for V1.5 itself at check-in #1"): re-fetched `quick_start.py`
(github.com/deepseek-ai/DeepSeek-Prover-V1.5, note: NOT at `datasets/quick_start.py` as an earlier
docstring implied — it's at the repo root) and `eval/step1_inference.py`
(github.com/Goedel-LM/Goedel-Prover) byte-for-byte. Both use the IDENTICAL header:

    import Mathlib
    import Aesop

    set_option maxHeartbeats 0

    open BigOperators Real Nat Topology Rat

`DeepSeekV15Template`/`GoedelSFTTemplate` (`src/atp/models/templates.py`) were missing BOTH
`import Aesop` and `set_option maxHeartbeats 0` — check-in #1's own verification only checked
INSTRUCTION WORDING and shape (fence, no sorry, no proof-plan), never the literal header content.
`set_option maxHeartbeats 0` disables Lean's elaboration heartbeat limit; without it, otherwise-valid
proofs using nlinarith/field_simp/simp-heavy tactic chains on nontrivial goals can spuriously fail to
elaborate in time — indistinguishable from a genuinely wrong proof without checking the raw Lean
option state. This is the same class of "genuine-looking failure that's actually a format bug" this
investigation has now hit three times (wiring bug, missing-theorem-header assembly bug, this one).

**Fix**: added `_deepseek_lean4_header()` (templates.py) — `import Mathlib` + `import Aesop` +
`set_option maxHeartbeats 0` + the theorem's own `open` clauses (kept per-problem-accurate rather
than the official scripts' hardcoded default open list) — used by both `DeepSeekV15Template` and
`GoedelSFTTemplate`'s `_code_prefix` (was `_theorem_header`, the shared helper `WholeProofTemplate`
still uses unchanged). Also fixed the VERIFICATION-side assembly for already-collected completions:
`PantographBackend._build_source` (both non-complete-file branches now include the same
`import Aesop`/`set_option maxHeartbeats 0` — safe since these two branches are, in current practice,
exclusively exercised by this exact model family) and `ReplBackend._build_repl_source` (adds
`set_option maxHeartbeats 0` only — deliberately NOT `import Aesop`: env 0 already has Mathlib
imported, whose modules transitively depend on Aesop so its tactics are already available, and
`import` is only legal as a fresh env's first command — injecting one later would itself be a genuine
Lean error). Test-first throughout: 2 new render() tests (byte-exact against the two official
sources), updated 2 existing `_build_repl_source` tests whose exact-match assertions needed the new
prefix, added a dedicated `test_build_repl_source_always_sets_max_heartbeats_zero` (applies
unconditionally, not duplicated if already present). Full `pytest -q` green (100%, all files).

**This requires ANOTHER re-verify pass** (CPU-only, still no new vLLM generation — this is purely a
verification-side Lean-option fix) over all 10 p8battery2_* configs before the floor table can be
trusted. Launching next; see PROGRESS.md.

## 2026-07-06 (cont.) — BLOCKER #5: informal_statement was silently dropped at Problem.to_theorem(), never rendered
Median completion length for DeepSeek-Prover-V1.5-SFT on the (Aesop/maxHeartbeats-fixed, still 0/732
solved) miniF2F re-verify was ~33 tokens across a 100-cell sample — far too short for the multi-step
proofs traced earlier. Checked whether the model was missing something it expected: quick_start.py's
own example places the informal problem statement as a `/-- ... -/` doc-comment directly before the
theorem; `eval/step1_inference.py` does the same via `informal_prefix`. Checked our data:
`Problem.informal_statement` is populated for 242/244 miniF2F problems, but `Problem.to_theorem()`
never passed it to `Theorem` (which had no field for it) — so this doc-comment has NEVER been
rendered for any model, in this project's entire history.

**Fix**: added `Theorem.informal_statement: str | None = None`, threaded through
`Problem.to_theorem()`, added `_informal_doc_comment(theorem)` (templates.py) — renders
`f"/-- {text} -/\n"` when present, empty string otherwise (never a hollow `/-- -/`) — wired into both
`DeepSeekV15Template`/`GoedelSFTTemplate`'s `_code_prefix`, placed between the header/opens and the
theorem statement, matching both official sources' layout. Test-first: regression test on
`Problem.to_theorem()`'s round-trip (`test_data.py`), byte-exact placement tests for both templates,
an omit-when-absent test, and an explicit `WholeProofTemplate` unaffected regression (byte-identical
render with/without informal_statement — Goedel-V2/DeepSeek-V2 never had this in their own official
format, this fix must not touch them). Full `pytest -q` green (100%).

This is a GENERATION-side change (changes what the model sees), not a pure verification/assembly fix
— per house rules, needs at least a smoke-scale regeneration to evaluate, not just a free CPU-only
re-verify pass. Smoke test next (handful of problems, 1 seed, small budget) before any real-scale
re-run — coordinator explicitly gated the real re-run on smoke results showing signal.

## 2026-07-09/10 — Harness-sanity control check: fixed 2 real bugs in the reverify TOOL (not the pipeline) before trusting it
Coordinator would not accept the 0.0%-everywhere corrected floor without a control: re-verify
Goedel-Prover-V2/DeepSeek-Prover-V2-7B (the two models confirmed unaffected by all 3 prior bugs) under
the current patched code and confirm they still post their known nonzero baselines. Found and fixed
2 issues in `slurm/phase8_reverify.sh`/`scripts/phase8_reverify.py` (the re-verify TOOLING itself, not
`atp`'s production code) while setting this up:

1. **Wrong Lean env for DeepSeek-V2**: the sbatch wrapper hardcoded staging `atp-lean-env` (the Goedel
   pin) regardless of model — DeepSeek-Prover-V2 needs `deepseek-lean-env` (a different mathlib
   commit, `ATP_LEAN_ENV_NAME=deepseek-lean-env` per that config's own usage comment). Fixed to
   parameterize by `ATP_LEAN_ENV_NAME` and copy the WHOLE env dir (not enumerate a hardcoded package
   lib name — Goedel's is `AtpLeanEnv/`, DeepSeek's is `DeepseekLeanEnv/`), matching
   `slurm/sweep_array.sh`'s existing approach. Also had to `elan toolchain install
   leanprover/lean4:v4.9.0` (DeepSeek's toolchain, distinct from Goedel's `v4.9.0-rc1`) — it wasn't
   present locally; hit a `$HOME` quota wall on the first attempt (CLAUDE.md rule 6's "tight quota"),
   freed 2.7G by removing an unused, unrelated `v4.30.0` toolchain (not referenced by any config in
   this repo, safe/regenerable) before retrying successfully.
2. **Reverify tool crashes on corrupt/empty checkpoints**: `results/baseline` has 732 pre-existing
   agent_state files from earlier phases; one was empty/corrupt, crashing the WHOLE re-verify batch on
   `json.JSONDecodeError` with zero resume tolerance for that specific failure mode. The production
   eval loop already handles this (`atp.agents.state`'s prior "tolerate empty/corrupt checkpoints"
   fix) — the re-verify tool didn't. Fixed test-first: `_load_attempts` now returns `None` (skip,
   logged) instead of raising; `run_reverify` skips and keeps going. Full `pytest -q` green.

Both fixes are in the STANDALONE re-verify tooling built for this investigation, not in `atp`'s
production package — they do not change or re-open anything about the 3 already-fixed pipeline bugs.
Resubmitted both control jobs with more time + the fixes; awaiting a real read before reporting.

## 2026-07-10 — client.py missing stop-sequence: investigated properly, VERDICT = real but does not explain the 0.0% floor
Per the coordinator's instruction not to dismiss this as "didn't explain anything" without checking —
investigated concretely rather than repeating the earlier debt note.

**Confirmed the gap is real**: `VLLMClient.from_config` never sets `self.stop` from any config field;
`whole_proof.py`'s `_step()` never passes a `stop` kwarg either. `self.stop` is `()` for every
template, always.

**Checked whether it masks hidden solves** (the concrete, falsifiable question): scanned attempts
across the highest-incidence configs for the pattern "content after a genuine (non-leading-echo)
```-fence, that isn't just the trailing-fence-strip case already handled" — i.e., could a real correct
proof be getting corrupted by trailing garbage the current extraction doesn't cut off?
- DeepSeek-V1.5-Base (32% of attempts show trailing content): sampled cases show the trailing content
  is a red herring — these completions ALSO have LEADING garbage (the already-documented `sorry`+
  comment-close pattern), which breaks Lean parsing at the very FIRST token, before ever reaching
  whatever real content follows. Fixing the trailing side wouldn't rescue these.
- Leanabell GD-SFT/GD-RL (11-15% of attempts): sampled cases show the model producing prose ("However,
  let's verify this proof step by step...") that hallucinates and analyzes a DIFFERENT, unrelated
  theorem (e.g. a nonexistent `sqrt_product_simplification` when the actual target problem is
  something else entirely) before ever opening a fence — a genuine model confusion/hallucination
  failure mode on this raw-continuation prompt, not a real solve hidden behind bad extraction. The
  fenced content, even if perfectly extracted, is about the wrong problem.
- DeepSeek-V1.5 SFT-ProofNet# and RL-miniF2F (the configs with the CLEANEST, most carefully-traced
  genuine-tactic-error attempts earlier in this investigation): **zero instances** of this pattern in
  the sampled cells — these attempts' extraction was never in question.

**Verdict**: the missing stop sequence is REAL and should be fixed for data quality/efficiency (wastes
budget on rambling/hallucinated continuations, produces messier failure feedback) — recommended for
any FUTURE regeneration pass. But it does NOT explain the 0.0% floor: sampled evidence shows no hidden
correct proofs are being suppressed by it in the current data. Not fixing now (would need new
generation to matter, and the harness-sanity control already confirms the scoring pipeline itself is
sound) — recorded as real, non-blocking debt, per the instruction to "record the verdict either way."

## 2026-07-10 — Formally dropping Cluster B breadth (STP, other Leanabell siblings) from scope
Per the coordinator's instruction: RL is now closed via two clean matched lineages (DeepSeek-Prover-
V1.5 Base->SFT->RL, Leanabell GD-SFT->GD-RL) through a verified-sound harness (harness-sanity control
passed, taint audit clean, stop-sequence debt investigated and cleared of masking any hidden solve).
Adding more models (STP, Leanabell-Prover-DS-SFT/DS-RL/V2-KM, etc.) would add BREADTH to an already-
established negative, not new information that could change the reading — the two lineages already
agree with each other exactly (0.0±0.0 everywhere). Cluster B is closed, not pursued further this
phase. `configs/stp_proofnet.yaml` remains pin-triaged (inferred pin) but was never swept and stays
that way; revisit only if a future phase specifically needs STP for a different question.

## 2026-07-10 — AUDIT: no_goal false-rejection bug found + fixed; pre-registered magnitude check

New session (post-Phase-8, per user's request for an independent audit before proceeding —
`AUDIT_PLAN.md`). Working tree was entirely UNCOMMITTED at session start (all of Phase 6 Stage C /
Phase 7 / Phase 8, since `aec81a2`) — committed first as `78a7230`, tagged `pre-audit-2026-07-10`
(Task A0), before any further change.

**Confirmed BUG (Task A1, P0)**: `Verifier.verify`'s `no_goal` soundness gate checked
`_DECL_RE.search(proof)` against the RAW extracted completion, not the backend-ASSEMBLED source it
actually compiled. `ReplBackend._build_repl_source`/`PantographBackend._build_source` unconditionally
reconstruct a `theorem ... := by` header when the proof lacks one (added 2026-07-06) — but
continuation-style templates (`DeepSeekV15Template`/`GoedelSFTTemplate`/`BFSProverTemplate`) NEVER
restate the theorem by design, so the gate's check was structurally always-None for that whole
template family, making `ok=True` unreachable regardless of correctness. Reproduced directly against
the real Lean REPL (`scripts/audit_no_goal_gate_check.py`): a genuinely correct bare-tactic proof
(`theorem triv2 : True` / body `  trivial`) compiled successfully (`backend.verify().success=True`)
but `Verifier.verify()` still returned `no_goal`. **Fixed**: `RawVerification.declares_goal: bool`
(computed by the backend from the assembled source) replaces the verifier's own re-derivation;
`_DECL_RE` de-duplicated to one copy in `backends.py`. Test-first (failing→fix→passing, both fast
`ScriptedReplTransport`-based and real-Lean `-m lean` regression tests). Full fast suite green (654
passed). Also fixed a benign parity gap in the unused `PantographBackend`'s complete-file branch
(never had `maxHeartbeats`; `PantographBackend` is confirmed test/plumbing-only, zero production
usage) for consistency (Task A2).

**This directly implicates Phase 8's committed "0.0%-everywhere corrected floor" headline** (both
matched lineages are continuation-style). The 37/37 & 40/40 harness-sanity control did not catch it
(only covers `whole_proof` models, for which the gate is a no-op). The exact completions behind the
`p8battery2_verified2_*` headline table are NOT retained (only `problems/*.json` summaries survive,
no `agent_states/`) — cannot be directly re-verified without a fresh GPU generation.

**PRE-REGISTRATION (magnitude check, offline CPU re-verify, no new GPU generation)**: re-verifying
recorded completions from the older (pre-`verified2`, already-known-invalid per ZOO.md's own table)
`p8battery2_*` run dirs — which DO retain `agent_states/` — under TODAY's fully-patched code (this
fix + the already-committed maxHeartbeats/assembly fixes) via `scripts/phase8_reverify.py`, sampled
`--limit 20` cells each across 4 dirs (deepseek_v15_base_proofnet, deepseek_v15_sft_minif2f,
leanabell_gdrl_proofnet, leanabell_gdsft_minif2f). Note for the record: a partial in-flight peek at
~19/80 cells (0 solved) was visible before this entry was written, while the run continued in the
background under heavy 4-way CPU contention on a 2-core interactive allocation — the decision rule
below is written from first principles (matching the full corpus's own recorded reason distribution,
sampled earlier this session: `no_goal` was only 0.03-0.6% of all attempts across these same dirs,
`compile_error` >99% — genuine incorrectness dominates regardless of this bug), not fitted to that
peek. **Decision rule**: this OLDER dataset is an imperfect proxy for the actual `verified2` headline
(generated before the assembly/maxHeartbeats fixes existed) — ANY flip here is existence-evidence the
bug has real bite on real completions (not just my synthetic Lean repro), but a ZERO-flip result on
this small, stale-data sample does NOT clear Phase 8's headline, because (a) the sample is small
against a rare event, (b) the exact `verified2` data is unavailable to check directly, and (c) the
bug's structural certainty (proven directly against real Lean) does not depend on how many flips
appear in any proxy sample. **Either way, the recommendation is: the Phase 8 continuation-style
battery needs a GPU regeneration + reverify under the now-fully-fixed harness before its
0.0%-everywhere headline can be trusted** — logged as a user decision (GPU jobs are user-submitted
per `PLAN_NEXT.md` §0.3), not something this audit session can resolve by itself.

## 2026-07-16 — WS1.1 power-up: pre-registration for DeepSeek x ProofNet# 3->8 seeds

Per PLAN_NEXT.md WS1.1 (now unblocked — audit Task B closed, see `atp-audit-plan` memory /
SYNTHESIS.md "Independent audit"). The DeepSeek x ProofNet# realizable-allocation result is
noise-dominated (−13% ± 28%, per-seed +5/+9/−51%, ALLOCATION.md §5) — not a confirmed negative, just
undetermined at n=3. This buys statistical power before any mechanism claim is drawn.

**Also found while prepping this**: the "two cells never run" (Goedel x miniF2F, DeepSeek x miniF2F
per-seed allocation) already exist — `phase4_perseed.py` loops over all four baseline runs
unconditionally and `results/phase4/perseed.json` already has both (goedel −40% ± 18%, deepseek
−13% ± 28% [minif2f], both per-seed-consistent negative). Added to `ALLOCATION.md`'s table this
session; the "full 2x2" WS1.1 asked for is complete with ZERO new GPU spend for that half. Only the
DeepSeek ProofNet# power-up needs new data.

**Config**: `configs/deepseek_proofnet_power8.yaml` (seeds `[3,4,5,6,7]`, inherits
`deepseek_proofnet_baseline`'s model/Lean pins unchanged). Run into the SAME run dir
(`results/deepseek_proofnet_baseline`) so cells merge with the existing seeds 0-2 by the usual
file-keyed resume/skip — `atp sweep --aggregate` then covers all 8 seeds. Submit command (handed off,
not run by this session — GPU jobs are user-submitted per PLAN_NEXT.md §0.3):
`sbatch slurm/sweep_array.sh configs/deepseek_proofnet_power8.yaml deepseek_proofnet_baseline`

**Budget estimate**: original 3-seed/186-problem DeepSeek ProofNet# run (`sacct -j 10676442`, plus its
failed-shard rerun in `10676443`/`10687933`) cost ≈55 GPU-h (8-way sharded, ~7h/shard on A6000). Same
problem population, 5 more independent seeds ⇒ linear scaling estimate **≈90-95 GPU-h**. This is
**above the 50 GPU-h CLAUDE.md ask-before line** — flagging explicitly per rule 8, and per
`feedback_gpuh_limit_flexible` not truncating the seed count just to duck under 50, since resolving a
σ=28% noise floor on the plan's stated critical path is exactly the kind of finding that memory says is
worth the spend. User call: run all 5 new seeds as one array, or split/stage if 90+ GPU-h on `short`
partition (11h cap, A6000) is inconvenient right now.

**Pre-registered prediction + decision rule** (per PLAN_NEXT.md WS1.1, both at the pooled-8-seed
level, using the existing c*=16k / OOF predictor — no refitting):
- Predicted sign: net positive but modest, because M2 mechanism analysis
  (`ALLOCATION_MECHANISM.md`, same session) found DeepSeek's raw late-bloomer population is
  comparable to or larger than Goedel's (36 vs 28 post-c* cells) — the fragility looks like a
  small-N per-seed sampling artifact (only ~12 late bloomers/seed) rather than a structural deficit,
  so more seeds should mostly TIGHTEN the estimate rather than flip its sign.
- **Decision rule** (verbatim from PLAN_NEXT.md WS1.1): if the 8-seed DeepSeek mean is within 1σ of
  zero, the claim becomes "one-model-robust, model-dependent" full stop; if positive and >1σ, claim
  generality (two-model STRONG); if negative and >1σ, the Goedel/DeepSeek divergence becomes the
  headline mechanism question for WS2's discussion section.
- This is the input to Gate G1 (end of WS1) — the user makes the two-paper-vs-one-paper call, not
  this session.

**Operational flag on the same handoff**: 90-95 GPU-h over 8 parallel shards (`sweep_array.sh`'s
`--array=0-7%8`) is ≈11-12h/shard — right at or past `slurm/sweep_array.sh`'s current
`--time=11:55:00` `short`-partition cap, the same failure mode (wall-clock timeout losing all progress)
Task B's audit jobs hit twice this cycle (see `AUDIT_FINDINGS.md` notes). Recommend the user either (a)
widen `--array` to more shards (e.g. 0-15%16) so each shard's slice shrinks proportionally, or (b) run
via `burst` (14-day cap) instead of `short` if enough concurrent A6000s aren't free. Not changing
`sweep_array.sh` unilaterally here since it's the shared GPU-sweep script other workstreams also use —
flagging for the user's submit-time judgment call instead.

## 2026-07-21 — WS1.1 power-up RESOLVED: DeepSeek x ProofNet# 8-seed result, decision rule applied

All 8 seeds (0-7) of DeepSeek-Prover-V2-7B x ProofNet# completed on `short` partition (jobs
11616556/11617103/11628973/11641972/11650652, chained across 3 TIMEOUT/resume cycles + one
NVML-herd node-exclude fix; see PROGRESS.md cont.9-25). `phase4_perseed.py` and
`analyze_allocation.py` re-run on the full 8-seed pool:

- deepseek x proofnet_sharp per-seed saved@90% (c*=16000): s0=+4% s1=+3% s2=+16% s3=+54% s4=-17%
  s5=-28% s6=+29% s7=+19% -> **mean +10% ± 24%** (up from the noise-dominated 3-seed −13% ± 28%).
- goedel x proofnet_sharp (unchanged, still 3 seeds): mean +26% ± 7% (strong, per-seed robust).
- Applying the pre-registered decision rule (2026-07-16 entry, verbatim from PLAN_NEXT.md WS1.1):
  0 falls within 1σ of the +10% mean (range -14% to +34%) -> **"one-model-robust, model-dependent"
  full stop.** Not a confirmed negative (prediction of "net positive but modest, mostly tightening"
  was directionally right — sign flipped positive and variance did shrink 28%->24% — but the effect
  did not clear the 1σ bar for generality).
- ALLOCATION_MECHANISM.md numbers also refreshed: deepseek_proofnet_sharp trapped%=72.6%,
  robust%=17.7%, n_post_c*=1256 (up from smaller pre-8-seed pool).

**This is the input to Gate G1** (PLAN_NEXT.md WS1, "end of WS1"): one-paper-vs-two-paper call.
Per PLAN_NEXT.md §0 ground rules and the WS1.1 pre-registration, **this is the user's call, not
this session's** — presenting evidence via AskUserQuestion, not deciding unilaterally.

## 2026-07-21 — Gate G1 resolved: ONE-PAPER world

User call (per Gate G1, PLAN_NEXT.md WS1): **one-paper world**. Phase 4's allocation result folds
into WS2 as the constructive section, honestly scoped as model-dependent — strong/robust for
Goedel (+26% +/- 7%), noise-dominated/inconclusive for DeepSeek even at n=8 (+10% +/- 24%, within
1sigma of zero). WS3 (standalone online-policy paper) is NOT being spun out.

This does not reopen WS2 for writing — the paper (`paper/floor/`) remains paused per the
2026-07-16 PLAN_NEXT.md update until the user explicitly says to resume writing. This entry only
records the structural decision so it's ready when WS2 does reopen.

## 2026-07-21 — External calibration critique: check #2 (Lean/mathlib version) resolved from existing evidence

A detailed external critique (relayed by the user) raised the possibility that our Lean v4.9.0-rc1 /
mathlib `2f65ba7` pin is a year+ older than what Goedel-Prover-V2 and DeepSeek-Prover-V2 were actually
trained/evaluated against, and that this (not a code bug) could explain Goedel's apparent ~10pp gap vs
its published miniF2F number. **This is already resolved, not assumed** — re-checking prior entries:

- The 2026-06-04 pin-lock entry (line ~74-84 above) verified our mathlib commit by reading
  Goedel-Prover-V2's OWN repo `.gitmodules` + root submodule pointer directly (not copied from a
  guess): it resolves to `xinhjBrant/mathlib4@2f65ba7…`, the exact commit we pin. The official
  upstream mathlib API 404s on this SHA, confirming it's fork-specific to Goedel's own training/eval
  environment, not a coincidence.
- A second, independent cross-check (2026-06-17, line ~1362 above) walked DeepSeek-Prover-V1.5's own
  `.gitmodules` via the GitHub Contents API and got the SAME commit — consistent with Goedel-Prover
  being built on top of DeepSeek-Prover-V1.5-Base and inheriting its mathlib fork rather than
  re-pinning.
- So our pin is not "a reasonable choice," it is **the exact commit read out of the model authors'
  own repos** for the model family our Goedel-V2/DeepSeek-V2 checkpoints descend from. This rules out
  "we verified against a newer, incompatible mathlib" as an explanation for any Goedel-specific
  underperformance. (It does NOT rule out that a *published* number like 84.6% was measured by a
  third party on a different/newer pin than the authors' own training env — that's a claim about the
  external paper's methodology, not about ours, and isn't checkable from this repo.)
- Known, already-documented, non-explanatory-of-the-asymmetry limitation: `grind` (Lean's newer
  automation tactic) is Lean>=4.14 and not available on our v4.9.0-rc1 pin (DECISIONS.md
  2026-06-1x, Phase 3 hammer-probe prep). This affects both models identically (same pin), so it
  cannot explain a Goedel-specific gap, only a possible modest downward bias on both.

**Verdict on external-critique check #2: closed, does not implicate our harness.** Proceeding to
checks #1 (pass@N recount) and #3 (finish-reason/heartbeat-in-refinement audit), CPU-only, per the
user's explicit "no GPU yet" scoping — full writeup once those land.

## 2026-07-21 — Pre-registration: Goedel-V2 calibration cell (GPU, NOT YET RUN)

Per the external calibration critique, pre-registering the read BEFORE running the one GPU cell it
requires (per user instruction — thresholds written down first, cell not yet authorized/run):

**Cell:** Goedel-Prover-V2-8B, miniF2F-test, 32 independent samples per problem, temp 0.7,
max_tokens 30000, OFFICIAL header/instruction (no budget meter, no refinement loop — plain
best-of-32 sampling), on our existing verified Lean pin (v4.9.0-rc1 / mathlib `2f65ba7`, see prior
entry — pin itself is not in question).

**Two reference anchors** (not one — per the critique, the paper's own 84.6% is not the only
legitimate comparison point; GAR's independent re-evaluation implies a base pass@32 nearer ~78% for
this model family):

- **≥ ~82%** → serving/harness is fine. The critique collapses to a methods-section fix: state the
  budget-vs-pass@N axis distinction explicitly in the writeup; the agent-loop-vs-plain-sampling delta
  becomes a small side finding, not a defect.
- **~78–82%** → consistent with independent (GAR-anchored) reproduction. Report the calibration
  number in the paper as the reference point used, move on — no harness fix needed.
- **< ~76%** → real defect. The trapped-core definitions (used throughout Phases 2-7's mechanism
  claims) need regenerating on a fixed harness, and the "Goedel carries the one positive Phase-4
  result" concern must be resolved before that result is written up.

**Scope guardrail (explicit, per user instruction):** this cell is validation of already-committed
results, not a new experimental arm. It does not reopen the intervention space (no decomposition
axis, no new scaffolding component), does not lift the WS2 paper-writing pause, and has a defined
stop: this cell plus the CPU-only checks already in flight (pass@N recount, finish-reason/heartbeat
audit, Stage A format diff). Phase 8 regeneration is an explicitly separate, larger decision to be
made AFTER this calibration lands, not bundled into it.

**Status: NOT YET RUN.** Awaiting the CPU-only checks' results and explicit user go-ahead for the
GPU spend (small — 244 problems × 32 samples on one model, single cell, not a sweep).

## 2026-07-24 — Calibration cell design REVISED (per user, based on check #1's finding)

Check #1 (pass@N recount) found more than an axis-mismatch calibration problem: Goedel x miniF2F's
128k-token budget maps to a median of ~1 (mean 1.94, max 14) independent propose samples, meaning
the pass@N curve was NEVER measured anywhere near N=32 — the "saturation" language in SYNTHESIS.md
§3 is a data-exhaustion plateau artifact, not a demonstrated ceiling, and this is a Phase-0-level
correction independent of what any new GPU run finds. It also means the 55-problem Goedel x
miniF2F trapped core (unsolved by all 3 seeds at 128k) was defined at ~6 effective independent
samples total (3 seeds x ~2 attempts), not at anything close to a real ceiling — union-of-seeds
solves 189/244 (77.5%) vs published pass@32's 84.6%, so plain resampling could plausibly recover a
material fraction of the "trapped" set.

**Design change (superseding the 2026-07-21 single-cell pre-registration):** run the 55-problem
trapped core (not the full 244) at pass@32 directly, official protocol, and log tokens per
generation — this does the calibration reconciliation, the trapped-core contamination check, AND
(since per-attempt tokens are already logged) the token-matched plain-sampling-vs-agent-loop
comparison for the project's founding Q1, all from one cell, at ~1/4 the cost of the full 244.

**Modified cell config**: `configs/calibration_trapped32_goedel_minif2f.yaml`. Goedel-Prover-V2-8B,
the 55 names in `scratch/phase2/trapped_minif2f.txt`, 32 independent samples (agent.max_rounds=32,
new config field), refinement disabled, temp=0.7, official header (`import Aesop` +
`set_option maxHeartbeats 0`, new `whole_proof_official_header` template — isolated as its own
registered template, `WholeProofTemplate` itself untouched, so no committed result is affected),
budget effectively uncapped (2,000,000 tokens vs a 655,360 max possible spend at 32*20480).
**One deviation from the reviewer's literal spec, flagged explicitly**: generation cap left at
max_model_len//2=20480, not 30000 — Goedel-Prover-V2-8B's own `config.json` caps
`max_position_embeddings` at 40960 with no rope scaling, so max_model_len cannot be raised past that
without risking breaking vLLM serving; 20480 is not expected to bind materially (only 4.89% of
Goedel miniF2F PROPOSE attempts hit this exact cap in the Phase 0 truncation audit).

**Pre-registered read (recovery count out of 55, UNCHANGED thresholds, same as 2026-07-21 entry's
spirit but against the trapped core directly rather than a full-244 calibration number)**:
- 0-3 recover -> trapped core sound; Phases 2/5/7 stand; fix the saturation + scoring-only language
  in SYNTHESIS.md, report the calibration, write.
- 4-10 recover -> contamination real but bounded; trapped-core claims need a stated recovery-rate
  caveat; interventions' nulls survive with that caveat.
- >10 recover -> trapped core needs regenerating at proper sample counts; every downstream
  "trapped by construction, baseline=0" claim (Phases 2 Step C, 5, 7) goes with it.

**Code changes** (all additive, zero effect on any existing config/result — full fast suite green,
tests added for each): `agent.max_rounds` (AgentCfg, WholeProofAgent.from_config — exact sample-count
cap independent of the token budget), `model.sample_max_tokens` override (ModelCfg — decouples the
generation cap from the max_model_len//2 heuristic without touching max_model_len itself),
`WholeProofOfficialHeaderTemplate` (templates.py — official-header variant, registered under
`whole_proof_official_header`, `WholeProofTemplate` unchanged).

**Smoke test**: job 11682216 (2 trapped problems, max_rounds=4) submitted before the real 55x32 run
per CLAUDE.md rule 5 / this project's "smoke one cell before the full array" convention.

**Two free CPU-only follow-ups requested, not yet done**: (a) reconcile F1's reported 18.9-23.6
attempts-per-unsolved-cell (MECHANISM.md) against this session's pass@N recount's 1.94-mean
propose-attempts — likely a "propose-only" vs "propose+refine" counting-definition difference, not
a contradiction, but needs to resolve cleanly since F1 is the mechanical basis for the
diversity-collapse story. (b) attempts-per-cell-by-budget table for all 4 model x benchmark
combinations, methods-section material regardless of the calibration outcome.

## 2026-07-24 — Calibration smoke test PASSED; full 55x32 cell submitted, sharded

Smoke (job 11682216, 2 trapped problems, max_rounds=4) COMPLETED clean, 1h11m: `stop_reason:
"max_rounds"` (confirms max_rounds — not the token budget — is the real, exact stopping condition;
tokens_spent 60771/66406 vs a 2,000,000 budget, nowhere near binding), `n_attempts: 4` matching
max_rounds exactly, all attempts `kind: "propose"` (refinement correctly disabled), real Lean
compile-error feedback (genuine verification, not mocked). Plumbing validated end to end.

**GPU-hour estimate**: from smoke timing (~20min fixed vLLM+Lean-staging overhead, ~12.8min/round
thereafter), worst case (a problem exhausts all 32 rounds unsolved) is ~6.8h/problem. Sharded 8-way
(mirrors WS1.1's proven pattern) with ~6.9 problems/shard, safely under n_workers=8 so every shard
gets full within-shard parallelism -> worst-case wall-clock per shard ~7h (fits the 12h `short` cap
in one shot, no resume cycles expected) but **worst-case aggregate GPU-hours across 8 shards is
~54h — over CLAUDE.md's 50 GPU-h ask-before line.** Flagging explicitly per convention even though
this exact cell was already authorized ("Run it") — this is a conservative upper bound (assumes
literally zero early solves across all 55 samples-of-32 trapped problems, implausible given the
whole point of the run is testing whether plain resampling recovers some of them); real cost is
expected to be well under this ceiling. Per `feedback_gpuh_limit_flexible`, not truncating scope to
duck under 50 given the finding this buys.

**Submitted**: `sbatch --array=0-7 slurm/sweep_array.sh configs/calibration_trapped32_goedel_minif2f.yaml
calibration_trapped32_goedel_minif2f`, `--exclude=ins082,ins087,ins089,ins091` (known-bad nodes),
`ATP_NSHARDS=8`. Job ID and monitoring to follow in PROGRESS.md.
