# Harness bug catalogue

Five structural bugs found in this project's own evaluation harness, plus two measurement gaps. Each
is written up for reuse: **none is specific to this codebase** — they are the kind of error that
reproduces silently in any LLM + proof-assistant evaluation harness, and each would have shipped a
wrong headline number in a specific, silent direction.

This is the standalone version of what the paper reports as its first contribution. The per-check
evidence ledger is `AUDIT_FINDINGS.md`; this file is the "what to check in your own harness" digest.

---

## The five bugs

### 1. Lean elaboration heartbeat left at its default
**Symptom:** correct proofs scored as failures, and — worse — spurious timeout feedback injected into
the refinement loop.
**Mechanism:** Lean's `maxHeartbeats` caps elaboration work. A proof that is genuinely correct but
slow to elaborate gets rejected with what looks like a proof error. `set_option maxHeartbeats 0`
disables the cap.
**Blast radius here:** 13/1212 trapped-core cells flipped to solved on re-verification (2.0% of
trapped-problem instances, both models, 3 of 4 cores). But the *final-scoring* number badly
understates it: **17.8% of miniF2F refinement steps** (550/3090 Goedel, 718/4046 DeepSeek) were
immediately preceded by a spurious heartbeat timeout the model then had to react to as if it were a
real error. That is live trajectory distortion, not just mis-scoring, and it is not quantified.
**Direction of error:** understates capability. The fix can only widen what counts as solved.
**Locked by:** `tests/test_lean_repl.py::test_build_repl_source_always_sets_max_heartbeats_zero`,
`tests/test_lean_verifier.py::test_build_source_complete_file_gets_heartbeat_safety_net_only`.
**Check your harness:** grep for `maxHeartbeats`. If it is absent, your slow-but-correct proofs are
being scored as failures, and your refine loop is being fed noise.

### 2. Truncated completions scored as solved (soundness hole)
**Symptom:** false positives on hard problems.
**Mechanism:** a generation truncated at the token limit could emit a bare `def`/preamble that Lean
compiles without error. No goal was ever stated, so nothing failed — and "no error" was being read as
"solved."
**Blast radius here:** miniF2F Phase 0: **0** false positives; miniF2F Phase 1: 6/3124 (0.2%);
**ProofNet# was materially corrupted** (constant full-budget truncation), which is why the ProofNet#
baseline and ablations were fully re-run on the fixed verifier.
**Direction of error:** overstates capability — the dangerous direction.
**Fix:** a solve requires a *declared theorem/lemma/example* **and** a REPL response carrying an
`env`. Absence of errors is not presence of a proof.
**Check your harness:** feed it a completion containing only a comment, and one containing only
`def f := 1`. If either scores as solved, you have this bug.

### 3. A wedged REPL scored as success
**Symptom:** false positives that correlate with load, not with difficulty.
**Mechanism:** a crashed, wedged, or cross-talking REPL process returns an empty response. Empty was
being treated as "no errors" and therefore success.
**Direction of error:** overstates capability, and does so *more* under concurrency — so it looks
like a throughput win.
**Check your harness:** kill the REPL mid-run. If the cells in flight score as solved, you have it.

### 4. A soundness gate that reads the wrong operand (phase-specific, forced 0%)
**Symptom:** one model family scores 0.0% everywhere, regardless of quality.
**Mechanism:** the strongest and subtlest of the five — **an emergent interaction between two
independently correct fixes.** A `no_goal` gate checked `not _DECL_RE.search(proof)` on the *raw
completion*. A later, unrelated fix made the backend assemble a full `theorem ... := by` wrapper
around any proof lacking one. For continuation-style templates — where the model never restates the
theorem, by design — the regex was then **structurally always `None`**, so the gate fired on every
attempt no matter how good the proof.
**Blast radius here:** this is what **withdrew Phase 8's headline**. The harness-sanity control did
not catch it, because that control only covered `whole_proof`-format models, for which the gate was
a no-op.
**Direction of error:** understates capability, catastrophically and invisibly — a 0% that looks like
a finding.
**Fix:** `RawVerification` gained a `declares_goal` field computed from the *assembled* source; the
verifier checks that instead of re-deriving it from the raw completion.
**Locked by:** `tests/test_lean_verifier.py::test_accepts_continuation_style_proof_when_backend_confirms_a_declared_goal`
and a real-Lean (not mocked) regression test,
`tests/test_lean_verifier.py::test_contract_accepts_genuine_continuation_style_solve`.
**Check your harness:** if any result is *exactly* 0.0%, treat it as a harness hypothesis before a
scientific one. And make sure your sanity control covers **every** completion format you run, not
just the common one.

### 5. Lean staging concurrency race
**Symptom:** intermittent, load-dependent failures that look like flaky infrastructure.
**Mechanism:** parallel workers staging the Lean environment to node-local disk raced each other.
**Direction of error:** noise, not bias — but it masquerades as a low pass rate.

---

## The two measurement gaps

### A. pass@*budget* is not pass@*N*
The gap is **budget-dependent, not a fixed offset**, so no constant converts between them. At
B=2k the *median* cell across all four baselines completes **zero** full propose attempts — that
point measures whether a truncated partial attempt happened to contain a proof, not whether the model
got one fair try. At 8k it is still only 0.68–0.87 attempts. Conversion table:
`results/phase0/ATTEMPTS_PER_BUDGET_TABLE.md`; figure: `paper/floor/figs/fig_attempts.pdf`.
**Implication:** a pass@budget result cannot be compared to a published pass@N number without this
conversion, and a pass@N result cannot be read as a compute-efficiency claim.

### B. A within-run bootstrap CI is not a replication
A per-problem bootstrap CI computed on **one** generation run bounds within-run sampling variance
only — **not** the run-to-run campaign variance a reader actually cares about. Caught here the hard
way: miniF2F retrieval's CI on the original run was entirely positive (`[+0.82, +6.15]`pp at 8k), and
an independent replication's own CI (`[-1.78, +3.14]`pp) **does not overlap it at all**. Same
intervention, same harness, same budget.
**Implication:** if a result matters, replicate the run. Do not let a tight bootstrap CI stand in for
that — vLLM sampling is not bitwise reproducible across processes, and the between-run component can
exceed the within-run one.

---

## The generalisable lesson

Four of these five bugs were caught by a check that covered *part* of the surface, and three were
**missed** for a while by exactly that: the Phase 8 sanity control covered only one completion
format; a reproduction gate compared means but not standard deviations; the test entry point
(`make test`) was broken while ad-hoc `python -m pytest` worked. **A verification gate that covers
only part of its output will pass while the uncovered part is silently wrong.** When a gate passes,
ask what it does not look at.

Second lesson, from bug 4 specifically: **two independently correct fixes can compose into a bug.**
Neither change was wrong in isolation, and neither review would have caught it. Only an end-to-end
test against the real verifier — not a mock — surfaced it.
