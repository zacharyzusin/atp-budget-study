#!/usr/bin/env python3
"""Stage C — GRPO RL feasibility probe (DeepSeek-Prover-V2-7B). See STAGE_C_PROBE_SPEC.md.

On-policy RL against the Lean verifier: the trainer samples G proofs per problem, the reward IS the
eval verdict (verified+sound -> 1.0, else format bonus; atp.rl.reward.LeanReward), and GRPO pushes
the GENERATION distribution toward proofs that verify — the lever that directly attacks the exposure
bias the two-model SFT null exposed (SFT maxed conditional likelihood; the floor didn't move).

Single-variable-clean vs the SFT arms: LoRA r=16, same base + pin. Rollout prompt is the BYTE-EXACT
inference prompt (WholeProofTemplate via the chat template), so a training solve is an eval solve.

Rollouts use HF generate (`use_vllm=False`): trl 0.17's vLLM path needs a separate serve GPU; the
probe keeps to one GPU. The held-out gate eval (phase6_launch_eval.sh) runs base AND RL through the
same vLLM harness, so the decisive G1 comparison is unaffected by the rollout engine.

Restartable (rule 3): GRPOTrainer checkpoints every --save-steps; rerun resumes. Per-step
soundness (G2) + diversity (G3) land in the trainer logs and <out>/probe_metrics.jsonl; KL-to-base
(G3) is trl's own `kl` log (beta>0).

Usage (probe):
  python scripts/phase6_grpo.py --config configs/phase6_grpo_deepseek.yaml \
      --train scratch/phase6/grpo/deepseek/train.jsonl \
      --out scratch/phase6/grpo/deepseek/ckpt --max-steps 150 --seed 0
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from atp.lean.backends import Theorem
from atp.models.templates import WholeProofTemplate

ROOT = Path(__file__).resolve().parents[1]


def load_rows(path: str) -> list[dict]:
    return [json.loads(ln) for ln in Path(path).read_text().splitlines() if ln.strip()]


def build_prompt_dataset(rows: list[dict], template: WholeProofTemplate | None = None) -> list:
    """rows ({name, statement, opens, imports}) -> GRPO examples.

    Each example carries a CONVERSATIONAL `prompt` (the exact user turn the eval sends; trl applies
    the model's chat template with add_generation_prompt=True, matching the vLLM chat endpoint) plus
    the columns the reward needs to rebuild the Theorem and verify (trl forwards non-`prompt`
    columns to the reward). Pure — no model/Lean — so it unit-tests on a login node."""
    template = template or WholeProofTemplate()
    out: list[dict] = []
    for r in rows:
        thm = Theorem(
            name=r["name"], statement=r["statement"],
            imports=tuple(r.get("imports") or ("Mathlib",)),
            opens=tuple(r.get("opens") or ()),
        )
        out.append({
            "prompt": [{"role": "user", "content": template.render(thm)}],
            "name": r["name"], "statement": r["statement"],
            "opens": list(thm.opens), "imports": list(thm.imports),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--train", required=True, help="train.jsonl from phase6_select_subset.py")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-steps", type=int, default=150)
    ap.add_argument("--num-generations", type=int, default=8, help="G rollouts / prompt")
    ap.add_argument("--prompts-per-step", type=int, default=16, help="B unique prompts / opt step")
    ap.add_argument("--lr", type=float, default=1e-6)
    ap.add_argument("--beta", type=float, default=0.04, help="KL-to-ref coefficient (G3 guard)")
    ap.add_argument("--max-completion-length", type=int, default=4096)
    ap.add_argument("--max-prompt-length", type=int, default=1024)
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--format-bonus", type=float, default=0.05)
    ap.add_argument("--reward-workers", type=int, default=12, help="parallel Lean verifiers")
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--lora-alpha", type=int, default=32)
    ap.add_argument("--save-steps", type=int, default=25)
    ap.add_argument("--logging-steps", type=int, default=1)
    args = ap.parse_args()

    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer, TrainerCallback, set_seed
    from trl import GRPOConfig, GRPOTrainer

    from atp.config import load_config
    from atp.lean.repl import ReplBackend
    from atp.rl.reward import LeanReward

    set_seed(args.seed)
    cfg = load_config(args.config)
    hf_repo, revision = cfg.model.hf_repo, cfg.model.revision

    tokenizer = AutoTokenizer.from_pretrained(hf_repo, revision=revision)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    rows = load_rows(args.train)
    dataset = Dataset.from_list(build_prompt_dataset(rows))
    print(f"[grpo] {len(dataset)} train problems from {args.train}")

    # per_device micro-batch = one prompt's G completions; grad-accum over B prompts => B*G/step.
    per_device = args.num_generations
    grad_accum = args.prompts_per_step

    reward = LeanReward(cfg, lambda: ReplBackend(cfg),
                        n_workers=args.reward_workers, format_bonus=args.format_bonus)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    metrics_path = out / "probe_metrics.jsonl"

    class RLProbeCallback(TrainerCallback):
        """Fold the reward's per-step soundness (G2) + diversity (G3) into the trainer logs and
        persist them for the readout. Runs on the same cadence as logging_steps."""

        def on_log(self, a, state, control, logs=None, **kw):  # noqa: ANN001
            extra = reward.drain_metrics()
            if not extra:
                return
            if logs is not None:
                logs.update(extra)
            rec = {"step": state.global_step, **extra}
            if logs and "kl" in logs:
                rec["kl"] = logs["kl"]
            if logs and "reward" in logs:
                rec["reward"] = logs["reward"]
            with metrics_path.open("a") as f:
                f.write(json.dumps(rec) + "\n")

    grpo_cfg = GRPOConfig(
        output_dir=str(out),
        per_device_train_batch_size=per_device,
        gradient_accumulation_steps=grad_accum,
        num_generations=args.num_generations,
        max_steps=args.max_steps,
        learning_rate=args.lr,
        beta=args.beta,
        temperature=args.temperature,
        top_p=args.top_p,
        max_completion_length=args.max_completion_length,
        max_prompt_length=args.max_prompt_length,
        lr_scheduler_type="constant_with_warmup",
        warmup_ratio=0.03,
        logging_steps=args.logging_steps,
        save_steps=args.save_steps,
        save_total_limit=2,
        bf16=True,
        gradient_checkpointing=True,
        log_completions=True,
        use_vllm=False,
        seed=args.seed,
        report_to=[],
    )

    model = AutoModelForCausalLM.from_pretrained(
        hf_repo, revision=revision, torch_dtype=torch.bfloat16, attn_implementation="eager")
    lora = LoraConfig(
        r=args.lora_r, lora_alpha=args.lora_alpha, lora_dropout=0.0,
        bias="none", task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
    )

    trainer = GRPOTrainer(
        model=model, reward_funcs=[reward], args=grpo_cfg,
        train_dataset=dataset, peft_config=lora, callbacks=[RLProbeCallback()],
    )
    ckpts = list(out.glob("checkpoint-*")) if out.exists() else []
    try:
        trainer.train(resume_from_checkpoint=bool(ckpts))
        trainer.save_model(str(out))
        manifest = {"base": hf_repo, "revision": revision, "train": args.train, "seed": args.seed,
                    "max_steps": args.max_steps, "num_generations": args.num_generations,
                    "prompts_per_step": args.prompts_per_step, "lr": args.lr, "beta": args.beta,
                    "max_completion_length": args.max_completion_length,
                    "lora_r": args.lora_r, "format_bonus": args.format_bonus,
                    "n_train": len(dataset), "use_vllm": False, "corpus": "lean_workbook_clean"}
        (out / "atp_grpo_manifest.json").write_text(json.dumps(manifest, indent=2))
        print(f"[grpo] adapter saved -> {out}; cum solve-rate {reward.tally.solve_rate:.3f}, "
              f"unsound {reward.tally.unsound_rate:.3f}")
    finally:
        reward.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
