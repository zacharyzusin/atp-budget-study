"""Closing-targeted SFT data construction (Phase 6 Stage B — the novel ingredient).

The mechanism story (Phase 2/3): the bottleneck is within-approach goal *closing* (the F2/F3
execution floor), not approach discovery. So we build training data that targets closing explicitly:
from each VERIFIED whole proof, truncate at a deep tactic boundary and form a
`(deep_proof_state -> remaining closing tactics)` pair. The model is trained to finish a proof from
a non-trivial intermediate state.

This module is the pure, Lean-free core: parse a tactic-mode proof into top-level tactic groups and
emit truncation candidates. Each candidate's `prefix_with_sorry` is elaborated by the REPL
(`scripts/phase6_harvest.py`) to (a) confirm the prefix cleanly elaborates to EXACTLY ONE sorry goal
and (b) read that goal's text = the `deep_state`. The pair re-verifies by construction: the full
proof (prefix + closing) already verified, so applying `closing` to that state closes it.

NESTED TRUNCATION (pilot finding 2026-06-22): these provers write monolithic
`have h_main : <goal> := by <real work>` then `exact h_main`, so TOP-LEVEL truncation yields a
useless `exact h_main` closing (~55-68% of pairs) while the goal-closing work is INSIDE the `have`.
We therefore also descend into `… := by` blocks and truncate within them (keeping outer context, so
exactly one sorry results), and DROP trivial closings (a lone `exact`/`simpa`/`assumption`/`rfl`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_BY_MARKER = re.compile(r":=\s*by\b")
_BLOCK_OPENER = re.compile(r":=\s*by\s*$")  # a group whose tactic body follows on indented lines
_TRIVIAL = re.compile(r"^(exact\??|simpa?|assumption|trivial|rfl)\b")
# a line that CONTINUES the preceding tactic rather than starting a new one — must never begin a
# group (truncating before it would leave a dangling combinator / orphan alternative).
_CONTINUATION = re.compile(r"^(<;>|<\|>|\||\)|\}|=>)")


@dataclass(frozen=True)
class ClosingCandidate:
    k: int                  # cut index within the chosen block (1 <= k < #groups in that block)
    n_groups: int           # #tactic groups in the block that was cut
    prefix_with_sorry: str  # full source: prefix + a `sorry` at the cut (elaborated for deep_state)
    closing: str            # remaining tactic text WITHIN the cut block — for trivial-filtering
    depth: int = 0          # 0 = top-level cut, 1 = cut inside a `… := by` block
    # --- proof-continuation (Stage B Option 1) fields: BODY text (tactics after the theorem's
    # `:= by`), split at the cut. INVARIANT: `<head>\n<cont_prefix>\n<cont_target>` == original
    # proof, so cont_target verifies by construction appended to cont_prefix. cont_target includes
    # any OUTER context after a nested block (e.g. the `exact h_main` after a `have … := by` cut).
    cont_prefix: str = ""   # body tactics up to the cut (the "proof so far" shown in the prompt)
    cont_target: str = ""   # body tactics from the cut to proof end (the continuation SFT target)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def split_head_body(proof: str) -> tuple[str, list[str]] | None:
    """Split a tactic-mode proof into (head_through_`:= by`, body_lines).

    Returns None if the proof is not tactic-mode (no top-level `:= by`) — those yield no closing
    targets. The body is the tactic block after the FIRST `:= by` (the theorem's); any tactics on
    the same line as `by` are pulled onto their own first body line.
    """
    m = _BY_MARKER.search(proof)
    if m is None:
        return None
    head = proof[: m.end()]
    rest = proof[m.end():]
    first, _, after = rest.partition("\n")
    body_lines: list[str] = []
    if first.strip():
        body_lines.append(first.strip())
    body_lines.extend(after.splitlines())
    while body_lines and not body_lines[-1].strip():
        body_lines.pop()
    if not body_lines:
        return None
    return head, body_lines


def top_level_groups(body_lines: list[str]) -> list[list[str]]:
    """Group body lines into top-level tactics: a line at the base indent starts a new group;
    more-indented (or blank) lines attach to the current group (so a multi-line `have … := by …`
    stays one group and we never truncate inside it)."""
    nonblank = [ln for ln in body_lines if ln.strip()]
    if not nonblank:
        return []
    base = min(_indent(ln) for ln in nonblank)
    groups: list[list[str]] = []
    for ln in body_lines:
        s = ln.strip()
        # A line starts a new top-level tactic only if it is at base indent AND is neither a
        # continuation (`<;>` etc.) nor a comment-only line. Comments must NOT start a group: a
        # comment sitting between a tactic and its `<;>` combinator would otherwise capture the
        # combinator into a comment-group, letting us cut mid-tactic (see lean_workbook_101).
        starts_group = bool(s) and _indent(ln) <= base \
            and not _CONTINUATION.match(s) and not s.startswith("--")
        if starts_group:
            groups.append([ln])
        elif groups:
            groups[-1].append(ln)
        else:
            groups.append([ln])
    return groups


def _candidate_ks(n: int) -> list[int]:
    """Truncation points: prioritize the END (closing = last 1/2/3 tactics) + one mid-depth."""
    ks = {n - 1, n - 2, n - 3, n // 2}
    return sorted(k for k in ks if 1 <= k < n)


def _real_lines(text: str) -> list[str]:
    """Stripped non-blank, non-comment-only lines."""
    return [ln.strip() for ln in text.splitlines()
            if ln.strip() and not ln.strip().startswith("--")]


def _is_trivial_closing(closing: str) -> bool:
    """A closing that is a lone goal-discharge (`exact h`/`simpa`/`assumption`/`rfl`) carries no
    execution-floor signal — the work is elsewhere. Drop it (comments ignored)."""
    real = _real_lines(closing)
    return len(real) <= 1 and bool(real) and bool(_TRIVIAL.match(real[0]))


def _closing_is_dangling(closing: str) -> bool:
    """A closing whose first real (non-comment) line begins with a tactic-combinator continuation
    (`<;>`, `|`, …) is an UNRUNNABLE training target: it only makes sense appended to the preceding
    tactic, so the cut split a tactic mid-combinator. The prefix may still elaborate to one sorry,
    so this is NOT caught downstream — drop it here."""
    real = _real_lines(closing)
    return bool(real) and bool(_CONTINUATION.match(real[0]))


def _flatten(groups: list[list[str]]) -> list[str]:
    return [ln for g in groups for ln in g]


def closing_truncations(proof: str) -> list[ClosingCandidate]:
    """Emit closing-target candidates for one verified tactic-mode proof (empty if not applicable).

    Top-level cuts + one level of descent into each `… := by` block (where the real goal-closing
    work lives). Trivial closings are dropped; each `prefix_with_sorry` is REPL-validated later.
    """
    sb = split_head_body(proof)
    if sb is None:
        return []
    head, body_lines = sb
    groups = top_level_groups(body_lines)
    n = len(groups)
    if n < 1:
        return []
    nonblank = [ln for ln in body_lines if ln.strip()]
    base_indent = min(_indent(ln) for ln in nonblank) if nonblank else 2
    base_pad = " " * base_indent

    out: list[ClosingCandidate] = []

    # --- top-level cuts (closing = last few top-level tactics) ---
    for k in _candidate_ks(n):
        prefix = _flatten(groups[:k])
        target = _flatten(groups[k:])
        closing = "\n".join(target).strip("\n")
        src = f"{head}\n" + "\n".join(prefix) + f"\n{base_pad}sorry"
        out.append(ClosingCandidate(k=k, n_groups=n, prefix_with_sorry=src,
                                    closing=closing, depth=0,
                                    cont_prefix="\n".join(prefix),
                                    cont_target="\n".join(target)))

    # --- nested cuts: descend into each `… := by` block, keeping outer context (one sorry) ---
    for i, g in enumerate(groups):
        if len(g) < 2 or not _BLOCK_OPENER.search(g[0]):
            continue
        header, inner_lines = g[0], g[1:]
        inner_nonblank = [ln for ln in inner_lines if ln.strip()]
        if not inner_nonblank:
            continue
        inner_pad = " " * min(_indent(ln) for ln in inner_nonblank)
        inner_groups = top_level_groups(inner_lines)
        m = len(inner_groups)
        if m < 2:
            continue
        before, after = _flatten(groups[:i]), _flatten(groups[i + 1:])
        for j in _candidate_ks(m):
            inner_prefix = _flatten(inner_groups[:j])
            inner_closing = _flatten(inner_groups[j:])
            closing = "\n".join(inner_closing).strip("\n")
            src_lines = before + [header] + inner_prefix + [f"{inner_pad}sorry"] + after
            src = f"{head}\n" + "\n".join(src_lines)
            # continuation target carries the inner closing AND the outer after-context (the proof
            # tail the model must still produce to finish), so cont_prefix+cont_target == original.
            cont_prefix = "\n".join(before + [header] + inner_prefix)
            cont_target = "\n".join(inner_closing + after)
            out.append(ClosingCandidate(k=j, n_groups=m, prefix_with_sorry=src,
                                        closing=closing, depth=1,
                                        cont_prefix=cont_prefix, cont_target=cont_target))

    return [c for c in out
            if not _is_trivial_closing(c.closing) and not _closing_is_dangling(c.closing)]
