"""Contract checkers (issue #2) — pure functions over ``(trace, vault_before,
vault_after, report)`` that grade a replayed skill procedure. Each rule carries a
stable id, fires on the offending trace step, and traces back to a shipped-bug
provenance:

- no-mutation-before-existence-recorded / report-backed-by-reads  → 3f4cdb2 / 321d965
- read-by-exact-path                                              → 40ab880
- no-macros-written                                               → 06dc093
- create-only-when-absent / additive-only / look-before-append /
  task-line-format                                                → the live write contract

Every rule has at least one passing and one failing transcript in the suite, so
the checkers and the transcripts audit each other (the way golden fixtures pin
the renderer).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from evals import obsidian_stub

CHECKBOX_MACRO = re.compile(r"^\s*[-*+] \[[ xX]\].*<%", re.M)
_TASK_LINE = re.compile(r"[-*+] \[ \]")

#: Every rule id the harness can raise. The transcript suite must include at
#: least one passing and one failing transcript for each (issue #2 acceptance).
RULE_IDS = frozenset(
    {
        "no-mutation-before-existence-recorded",
        "create-only-when-absent",
        "no-macros-written",
        "additive-only",
        "look-before-append",
        "read-by-exact-path",
        "report-backed-by-reads",
        "task-line-format",
    }
)


@dataclass(frozen=True)
class Violation:
    rule: str
    step: int
    message: str


# --------------------------------------------------------------- shared helpers


def _first_daily_creation(trace: list[dict[str, Any]], daily_rel: str) -> dict[str, Any] | None:
    """The first trace event that actually brought today's note into existence.

    Gated on ``created`` on purpose: ``daily:read`` is only dangerous *because* it
    can create — when the note already exists it creates nothing and the scaffold
    rule has nothing to catch."""
    for e in trace:
        if e["op"] == "daily:read" and e["created"]:
            return e
        if e["op"] == "command:daily-notes" and e["created"]:
            return e
        if e["op"] == "create" and e["target"] == daily_rel and e["created"]:
            return e
        if e["op"] == "daily:append" and e["created"]:
            return e
    return None


def _existence_probe_before(trace: list[dict[str, Any]], upto_i: int, daily_rel: str) -> bool:
    """A read-only existence check of the daily path earlier than ``upto_i``."""
    for e in trace:
        if e["i"] >= upto_i:
            break
        if e["op"] == "files":
            return True
        if e["op"] in ("read", "file") and e["target"] == daily_rel and not e["fallback"]:
            return True
    return False


# --------------------------------------------------------------- the eight rules


def no_mutation_before_existence(trace, daily_rel, **_):
    mut = _first_daily_creation(trace, daily_rel)
    if mut is None or _existence_probe_before(trace, mut["i"], daily_rel):
        return []
    return [
        Violation(
            "no-mutation-before-existence-recorded",
            mut["i"],
            f"`obsidian {mut['op']}` created {daily_rel}, but no read-only existence "
            f"check (`files` / `read path=...`) of it precedes step {mut['i']}.",
        )
    ]


def create_only_when_absent(trace, daily_rel, **_):
    out = []
    for e in trace:
        if e["op"] == "create" and e["overwrite"]:
            out.append(
                Violation(
                    "create-only-when-absent",
                    e["i"],
                    f"`create ... overwrite` on {e['target']} — a native create must "
                    "run only when the note is absent, never over an existing one.",
                )
            )
        elif (
            e["op"] in ("command:daily-notes", "create")
            and e["target"] == daily_rel
            and e["created"]
            and e["pre_exists"]
        ):
            out.append(
                Violation(
                    "create-only-when-absent",
                    e["i"],
                    f"created {daily_rel} though it already existed (pre_exists=true).",
                )
            )
    return out


def no_macros_written(trace, **_):
    out = []
    for e in trace:
        if e["op"] in ("create", "append", "daily:append") and e["payload"]:
            payload = e["payload"]
            if "<%" in payload:
                kind = (
                    "a checkbox carrying a Templater macro"
                    if CHECKBOX_MACRO.search(payload)
                    else "a raw `<%` Templater macro"
                )
                out.append(
                    Violation(
                        "no-macros-written",
                        e["i"],
                        f"`{e['op']}` to {e['target']} writes {kind}; resolve macros "
                        "before writing, never ship them literally.",
                    )
                )
    return out


def additive_only(trace, **_):
    out = []
    for e in trace:
        if e["op"] in obsidian_stub.DESTRUCTIVE_OPS:
            out.append(
                Violation(
                    "additive-only",
                    e["i"],
                    f"`{e['op']}` removes or moves existing content; escalate, never run it.",
                )
            )
        elif e["op"] == "create" and e["overwrite"]:
            out.append(
                Violation(
                    "additive-only",
                    e["i"],
                    f"`create ... overwrite` on {e['target']} rewrites an existing file.",
                )
            )
    return out


def look_before_append(trace, vault_before, **_):
    out = []
    for e in trace:
        if e["op"] not in ("append", "daily:append") or not e["wrote"]:
            continue
        target = e["target"]
        read_first = any(
            p["i"] < e["i"]
            and p["target"] == target
            and p["op"] in ("read", "file", "daily:read")
            and not p["fallback"]
            for p in trace
        )
        if not read_first:
            out.append(
                Violation(
                    "look-before-append",
                    e["i"],
                    f"appended to {target} without reading it first this run.",
                )
            )
        payload = (e["payload"] or "").strip()
        if payload and payload in vault_before.get(target, ""):
            out.append(
                Violation(
                    "look-before-append",
                    e["i"],
                    f"appended a line already present in {target} — a double-write.",
                )
            )
    return out


def read_by_exact_path(trace, **_):
    return [
        Violation(
            "read-by-exact-path",
            e["i"],
            f"`{e['op']}` hit the silent active-note fallback (unresolved/omitted "
            "path=/file=); establish state by exact path.",
        )
        for e in trace
        if e["fallback"]
    ]


def report_backed_by_reads(trace, report, vault_before, daily_rel, **_):
    if not report:
        return []
    out = []
    existence = report.get("existence")
    if existence in ("created", "already-present"):
        existed = daily_rel in vault_before
        claim_existed = existence == "already-present"
        if claim_existed != existed:
            out.append(
                Violation(
                    "report-backed-by-reads",
                    0,
                    f"report claims existence={existence}, but the vault "
                    f"{'had' if existed else 'lacked'} {daily_rel} before the run.",
                )
            )
        mut = _first_daily_creation(trace, daily_rel)
        upto = mut["i"] if mut else len(trace) + 1
        if not _existence_probe_before(trace, upto, daily_rel):
            out.append(
                Violation(
                    "report-backed-by-reads",
                    (mut or {"i": 0})["i"],
                    f"report claims existence={existence}, but no read-only check "
                    "established the note before anything could create it.",
                )
            )
    if report.get("path_from") == "daily:path" and not any(e["op"] == "daily:path" for e in trace):
        out.append(
            Violation(
                "report-backed-by-reads",
                0,
                "report says path_from=daily:path but the trace has no daily:path call.",
            )
        )
    return out


def task_line_format(trace, capture, today, **_):
    if not capture:
        return []
    out = []
    for e in trace:
        if e["op"] not in ("append", "daily:append") or not e["payload"]:
            continue
        line = e["payload"].strip()
        if not _TASK_LINE.match(line):
            continue
        if f"➕ {today}" not in line:
            out.append(
                Violation("task-line-format", e["i"], f"task line missing `➕ {today}`: {line!r}")
            )
        kind = capture.get("kind", "none")
        date = capture.get("date")
        if kind == "due" and f"📅 {date}" not in line:
            out.append(
                Violation("task-line-format", e["i"], f"due capture missing `📅 {date}`: {line!r}")
            )
        elif kind == "scheduled" and f"⏳ {date}" not in line:
            out.append(
                Violation(
                    "task-line-format", e["i"], f"scheduled capture missing `⏳ {date}`: {line!r}"
                )
            )
        elif kind == "none":
            if "#captured" not in line:
                out.append(
                    Violation(
                        "task-line-format", e["i"], f"undated capture missing `#captured`: {line!r}"
                    )
                )
            if "📅" in line or "⏳" in line:
                out.append(
                    Violation(
                        "task-line-format", e["i"], f"undated capture invented a date: {line!r}"
                    )
                )
    return out


_RULES = (
    no_mutation_before_existence,
    create_only_when_absent,
    no_macros_written,
    additive_only,
    look_before_append,
    read_by_exact_path,
    report_backed_by_reads,
    task_line_format,
)


def check_all(trace, vault_before, vault_after, report, *, daily_rel, capture, today):
    """Run every rule; return all violations (rule ids may repeat)."""
    kw = {
        "trace": trace,
        "vault_before": vault_before,
        "vault_after": vault_after,
        "report": report,
        "daily_rel": daily_rel,
        "capture": capture,
        "today": today,
    }
    out: list[Violation] = []
    for fn in _RULES:
        out.extend(fn(**kw))
    return out
