"""Tests for the Phase 6 SFT label-masking core (no model/GPU: a fake chat tokenizer)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "phase6_train_sft.py"
_spec = importlib.util.spec_from_file_location("phase6_train_sft", _SCRIPT)
train = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = train
_spec.loader.exec_module(train)


class _FakeTokenizer:
    """Char-level chat tokenizer: user turn -> 'U:'+content, assistant -> 'A:'+content; the
    generation prompt appends the bare 'A:' header (mirrors add_generation_prompt)."""

    def apply_chat_template(self, messages, tokenize=True, add_generation_prompt=False):
        s = ""
        for m in messages:
            s += ("U:" if m["role"] == "user" else "A:") + m["content"] + "|"
        if add_generation_prompt:
            s += "A:"
        return [ord(c) for c in s] if tokenize else s


def test_build_labels_masks_prompt_and_keeps_completion():
    msgs = [{"role": "user", "content": "ask"}, {"role": "assistant", "content": "ans"}]
    out = train.build_labels(msgs, _FakeTokenizer(), max_len=1000)
    # full = "U:ask|A:ans|" ; prompt(add_generation) = "U:ask|A:"
    full = "U:ask|A:ans|"
    prompt = "U:ask|A:"
    assert out["input_ids"] == [ord(c) for c in full]
    # the first len(prompt) labels are masked; the rest equal the completion tokens
    assert out["labels"][: len(prompt)] == [train.IGNORE] * len(prompt)
    assert out["labels"][len(prompt):] == [ord(c) for c in full[len(prompt):]]
    assert "".join(chr(t) for t in out["labels"][len(prompt):]) == "ans|"


def test_build_labels_truncates_to_max_len():
    msgs = [{"role": "user", "content": "x" * 50}, {"role": "assistant", "content": "y" * 50}]
    out = train.build_labels(msgs, _FakeTokenizer(), max_len=20)
    assert len(out["input_ids"]) == 20 and len(out["labels"]) == 20


def test_build_labels_all_masked_when_completion_truncated_away():
    # if max_len cuts before the assistant turn, every label is IGNORE (no completion supervised)
    msgs = [{"role": "user", "content": "x" * 50}, {"role": "assistant", "content": "ans"}]
    out = train.build_labels(msgs, _FakeTokenizer(), max_len=5)
    assert out["labels"] == [train.IGNORE] * 5


def test_build_labels_supervise_after_masks_completion_head():
    # Stage B: assistant = full proof; supervise ONLY the closing tail, not the copied prefix.
    msgs = [{"role": "user", "content": "CONT"},
            {"role": "assistant", "content": "PREFIXBODY###CLOSE"}]
    out = train.build_labels(msgs, _FakeTokenizer(), max_len=1000, supervise_after="CLOSE")
    sup = "".join(chr(t) for t in out["labels"] if t != train.IGNORE)
    # only the closing region (from 'CLOSE' onward, plus the turn-end '|') is supervised
    assert "CLOSE" in sup and "PREFIXBODY" not in sup
    # everything before the closing is masked
    full = "U:CONT|A:PREFIXBODY###CLOSE|"
    boundary = full.index("CLOSE")
    assert out["labels"][:boundary] == [train.IGNORE] * boundary


def test_build_labels_supervise_after_falls_back_to_prompt_mask_when_absent():
    # marker not in the assistant content -> behave like Stage A (supervise whole completion)
    msgs = [{"role": "user", "content": "ask"}, {"role": "assistant", "content": "ans"}]
    out_b = train.build_labels(msgs, _FakeTokenizer(), max_len=1000, supervise_after="NOPE")
    out_a = train.build_labels(msgs, _FakeTokenizer(), max_len=1000)
    assert out_b["labels"] == out_a["labels"]
