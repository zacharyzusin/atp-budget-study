#!/usr/bin/env bash
# Phase 2 Step B — empirical pin confirmation: verify DeepSeek-Prover-V2's OWN published miniF2F proofs
# (minif2f-solutions.zip) against our candidate DeepSeek env (Lean v4.9.0 + standard mathlib @ f0957a7).
# The verification fraction is the faithful-pin metric: ~100% => the env we built reproduces DeepSeek's
# verification environment; substantially less => some published results depend on env details we can't
# reconstruct at this commit (a disclosable limitation, or a signal to widen the v4.9.0 window).
#
# Each solution is a complete `import Mathlib` proof (no sorry) → a clean `lake env lean` (rc 0, no
# "error:") = verified. Runs `lake env lean` from the env dir so LEAN_PATH resolves. CPU/Lean, no GPU.
#
# Usage: scripts/verify_deepseek_proofs.sh [N_SAMPLE|all] [PARALLEL]
#   N_SAMPLE: how many solution files to check (default 60; "all" = every file). PARALLEL default 8.
set -uo pipefail
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy

PROJ="/insomnia001/depts/edu/COMS-E6998-012/zwz2000/atp-budget-study"
ENV_DIR="$PROJ/scratch/lean-cache/deepseek-lean-env"
SOLS="$PROJ/scratch/phase2/deepseek_recon/sols"
N_SAMPLE="${1:-60}"
PAR="${2:-8}"
export PATH="$HOME/.elan/bin:$PATH"
export ELAN_HOME="$PROJ/scratch/elan-deepseek"   # same relocated toolchain home as the build (HOME quota)

[ -d "$ENV_DIR/.lake" ] || { echo "FATAL: env not built at $ENV_DIR (run slurm/build_deepseek_lean.sh)"; exit 1; }
[ -d "$SOLS" ] || { echo "FATAL: solutions not extracted at $SOLS"; exit 1; }
cd "$ENV_DIR" || exit 1

mapfile -t ALL < <(find "$SOLS" -name '*.lean' | sort)
echo "[verify] $(date) host=$(hostname) — ${#ALL[@]} published proofs available; toolchain=$(cat lean-toolchain)"
if [ "$N_SAMPLE" = "all" ]; then
    FILES=("${ALL[@]}")
else
    # deterministic stride sample across test+valid for a representative fraction
    mapfile -t FILES < <(printf '%s\n' "${ALL[@]}" | awk -v n="$N_SAMPLE" -v t="${#ALL[@]}" 'NR%int((t/n)+1)==1')
fi
echo "[verify] checking ${#FILES[@]} files at -P$PAR (rc0 = verified)..."

RES=$(mktemp)
printf '%s\n' "${FILES[@]}" | xargs -P "$PAR" -I{} bash -c '
  f="{}"
  if timeout 300 lake env lean "$f" >/dev/null 2>&1; then echo "PASS $f"; else echo "FAIL $f"; fi
' > "$RES"

NP=$(grep -c '^PASS' "$RES"); NF=$(grep -c '^FAIL' "$RES"); NT=$((NP+NF))
echo "[verify] DONE $(date)"
echo "[verify] VERIFIED $NP / $NT  = $(awk -v a="$NP" -v b="$NT" 'BEGIN{printf "%.1f%%", (b? 100*a/b:0)}')"
if [ "$NF" -gt 0 ]; then echo "[verify] failures (first 15):"; grep '^FAIL' "$RES" | head -15 | sed 's#.*/sols/#  #'; fi
mkdir -p "$PROJ/results/phase2"
printf 'deepseek_pin_verification %s\nenv: lean v4.9.0 + standard mathlib@f0957a7\nverified %s/%s\nlist:\n' \
    "$(date -Is)" "$NP" "$NT" > "$PROJ/results/phase2/deepseek_proof_verification.txt"
cat "$RES" >> "$PROJ/results/phase2/deepseek_proof_verification.txt"
rm -f "$RES"
