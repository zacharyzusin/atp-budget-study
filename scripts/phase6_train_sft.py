#!/usr/bin/env python3
"""Phase 6 Task 6.5: LoRA SFT for Stage A (RFT) / Stage B (closing-targeted continuation).

Single-variable A-vs-B (DECISIONS.md 2026-06-22): SAME base, LoRA config, hyperparameters and total
optimization STEPS; the ONLY difference is the dataset (sft_A.jsonl vs sft_B.jsonl). So a win is
attributable to mechanism-targeting, not to a knob.

Inference-faithful loss: each example is tokenized with the model's OWN chat template (exactly what
vLLM applies when the agent posts the user turn), and labels mask everything up to the assistant
turn (completion-only loss). `build_labels` is the pure, fake-tokenizer-tested core; the
Trainer/PEFT/CUDA parts are the thin GPU wrapper.

Restartable (CLAUDE.md rule 3): Trainer checkpoints every --save-steps; rerun resumes from latest.

Usage (one arm, one seed):
  python scripts/phase6_train_sft.py --config configs/phase6_harvest_goedel.yaml \
      --data scratch/phase6/sft/goedel/sft_B.jsonl \
      --out scratch/phase6/ckpt/goedel/B_seed0 --seed 0 --max-steps 200
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

IGNORE = -100  # HF label id that the loss ignores (the masked prompt tokens)


def _common_prefix_len(a: list[int], b: list[int]) -> int:
    n = 0
    for x, y in zip(a, b, strict=False):
        if x != y:
            break
        n += 1
    return n


def build_labels(messages: list[dict], tokenizer, max_len: int,
                 supervise_after: str | None = None) -> dict:
    """Tokenize one conversational example with the chat template; return {input_ids, labels}
    (truncated to max_len), with loss masked (IGNORE) up to a boundary.

    Default (Stage A / RFT): mask the PROMPT only — supervise the whole assistant turn (the proof).

    `supervise_after` (Stage B): mask the prompt AND the assistant-turn HEAD up to the start of this
    text, so loss falls ONLY on the closing (`cont_target`). Without this the loss is dominated by
    the model trivially copying the proof-prefix that the continuation prompt already gave it (smoke
    train_loss 0.06) — the gradient would barely touch the goal-closing we teach. The boundary
    is the longest common TOKEN prefix between the full sequence and the same messages with the
    assistant content truncated before `supervise_after` (robust to chat-template turn wrappers).

    Pure given a tokenizer with `apply_chat_template` (unit-tested with a fake tokenizer)."""
    full = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=False)
    boundary = None
    if supervise_after and len(messages) >= 2:
        asst = messages[1]["content"]
        idx = asst.rfind(supervise_after)
        if idx > 0:
            head_msgs = [messages[0], {"role": "assistant", "content": asst[:idx]}]
            head_ids = tokenizer.apply_chat_template(
                head_msgs, tokenize=True, add_generation_prompt=False)
            boundary = _common_prefix_len(full, head_ids)
    if boundary is None:  # Stage A, or fallback: mask only the prompt
        boundary = len(tokenizer.apply_chat_template(
            messages[:1], tokenize=True, add_generation_prompt=True))
    labels = [IGNORE] * min(boundary, len(full)) + full[boundary:]
    input_ids = full[:max_len]
    labels = labels[:len(input_ids)]
    return {"input_ids": input_ids, "labels": labels}


def load_examples(path: str) -> list[dict]:
    return [json.loads(ln) for ln in Path(path).read_text().splitlines() if ln.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--data", required=True, help="sft_A.jsonl or sft_B.jsonl")
    ap.add_argument("--out", required=True, help="adapter output dir")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-steps", type=int, default=200, help="MATCH across A and B (single var)")
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--batch-size", type=int, default=1)
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--max-len", type=int, default=4096)
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--lora-alpha", type=int, default=32)
    ap.add_argument("--lora-dropout", type=float, default=0.05)
    ap.add_argument("--save-steps", type=int, default=100)
    args = ap.parse_args()

    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        Trainer,
        TrainingArguments,
        set_seed,
    )

    from atp.config import load_config

    set_seed(args.seed)
    config = load_config(args.config)
    hf_repo = config.model.hf_repo
    revision = config.model.revision

    tokenizer = AutoTokenizer.from_pretrained(hf_repo, revision=revision)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    examples = load_examples(args.data)
    tokenized = [build_labels(e["messages"], tokenizer, args.max_len, e.get("supervise_after"))
                 for e in examples]
    n_sup = sum(any(x != IGNORE for x in t["labels"]) for t in tokenized)
    med = sorted(len(t["input_ids"]) for t in tokenized)[len(tokenized) // 2]
    med_sup = sorted(sum(x != IGNORE for x in t["labels"]) for t in tokenized)[len(tokenized) // 2]
    print(f"[train] {len(tokenized)} examples from {args.data}; median len {med}; "
          f"median supervised tokens {med_sup}; {n_sup} with >=1 supervised token")

    def collate(batch: list[dict]) -> dict:
        maxlen = max(len(b["input_ids"]) for b in batch)
        pad_id = tokenizer.pad_token_id
        input_ids, labels, attn = [], [], []
        for b in batch:
            n = maxlen - len(b["input_ids"])
            input_ids.append(b["input_ids"] + [pad_id] * n)
            labels.append(b["labels"] + [IGNORE] * n)
            attn.append([1] * len(b["input_ids"]) + [0] * n)
        return {
            "input_ids": torch.tensor(input_ids),
            "labels": torch.tensor(labels),
            "attention_mask": torch.tensor(attn),
        }

    model = AutoModelForCausalLM.from_pretrained(
        hf_repo, revision=revision, torch_dtype=torch.bfloat16, attn_implementation="eager")
    model.config.use_cache = False
    model.gradient_checkpointing_enable()
    lora = LoraConfig(
        r=args.lora_r, lora_alpha=args.lora_alpha, lora_dropout=args.lora_dropout,
        bias="none", task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
    )
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    targs = TrainingArguments(
        output_dir=args.out,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        max_steps=args.max_steps,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        logging_steps=10,
        save_steps=args.save_steps,
        save_total_limit=1,
        bf16=True,
        seed=args.seed,
        report_to=[],
    )
    trainer = Trainer(model=model, args=targs, train_dataset=tokenized, data_collator=collate)
    ckpts = list(Path(args.out).glob("checkpoint-*")) if Path(args.out).exists() else []
    trainer.train(resume_from_checkpoint=bool(ckpts))
    model.save_pretrained(args.out)
    tokenizer.save_pretrained(args.out)
    manifest = {"base": hf_repo, "revision": revision, "data": args.data, "seed": args.seed,
                "max_steps": args.max_steps, "lr": args.lr, "lora_r": args.lora_r,
                "n_examples": len(tokenized), "corpus": "lean_workbook_clean"}
    (Path(args.out) / "atp_train_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"[train] adapter saved -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
