"""A fake ``obsidian`` CLI (issue #2).

Implements the command subset the daily-notes / task-capture / vault-operations
skills drive, over a vault root, and — crucially — reproduces the *sharp edges*
those skills defend against, so a procedure change is executed against them
rather than against a forgiving fake. Every invocation appends one JSON line to
a trace; the contract checkers grade that trace.

The stub is intentionally not a real Obsidian: its Templater emulation resolves
exactly the shipped daily template and nothing else, and its plugin/task
behaviour is the documented minimum. Provenance for each sharp edge — verified
against the live CLI vs. assumed from skill prose — lives in ``CLI_SEMANTICS.md``.

Two entry points, one code path:

- ``run(argv, *, vault, state_path, trace_path, today)`` — in-process, for the
  scripted lane (no subprocess, fully portable).
- ``main()`` — reads ``OBSIDIAN_STUB_VAULT`` / ``OBSIDIAN_STUB_STATE`` /
  ``OBSIDIAN_STUB_TRACE`` / ``ONYXIAN_NOW`` from the environment, for the PATH
  shim used by the live lane.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import yaml

# --------------------------------------------------------------- Templater

_INLINE_DATE = '<% tp.date.now("YYYY-MM-DD") %>'


def _unescape(s: str) -> str:
    return re.sub(
        r"\\(.)",
        lambda m: {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}.get(
            m.group(1), m.group(1)
        ),
        s,
    )


def _split_plus(expr: str) -> list[str]:
    """Split a ``tR +=`` right-hand side on top-level ``+`` (not inside strings)."""
    parts: list[str] = []
    buf = ""
    in_str = esc = False
    for ch in expr:
        if in_str:
            buf += ch
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
            buf += ch
        elif ch == "+":
            parts.append(buf)
            buf = ""
        else:
            buf += ch
    parts.append(buf)
    return parts


def _eval_tr(block: str, today: str) -> str:
    """Evaluate the shipped daily template's ``<%* ... %>`` string-building block.

    Deliberately tiny: it understands ``const today = ...`` (skipped) and
    ``tR += "literal" + today + "literal";`` concatenation, nothing more.
    """
    out: list[str] = []
    for line in block.splitlines():
        m = re.match(r"\s*tR\s*\+=\s*(.+?);\s*$", line)
        if not m:
            continue
        val = ""
        for term in _split_plus(m.group(1)):
            term = term.strip()
            if term == "today":
                val += today
            elif len(term) >= 2 and term.startswith('"') and term.endswith('"'):
                val += _unescape(term[1:-1])
        out.append(val)
    return "".join(out)


def resolve_templater(text: str, today: str) -> str:
    """Resolve the shipped daily template's macros. Leaves no ``<%`` behind.

    Whitespace-control tokens (``-%>``) are *not* emulated — the block token is
    replaced by its ``tR`` value and surrounding newlines are left intact. The
    result is deterministic and pinned by a test; it is not byte-for-byte real
    Templater output (fidelity there is out of scope, per the issue).
    """
    text = text.replace(_INLINE_DATE, today)
    return re.sub(r"<%\*(.*?)%>", lambda m: _eval_tr(m.group(1), today), text, flags=re.DOTALL)


# --------------------------------------------------------------- vault helpers

# Destructive / mutating-in-place ops the additive contract forbids outright.
DESTRUCTIVE_OPS = {"delete", "move", "rename", "property:remove"}


class StubError(Exception):
    """A stub call the live CLI would reject (e.g. create over an existing file)."""


def _read_config_name(vault: Path) -> str:
    cfg = vault / ".vault" / "config.yaml"
    if not cfg.is_file():
        return ""
    data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    return str(data.get("vault", {}).get("name", ""))


def _daily_rel(vault: Path, today: str) -> str:
    """Today's daily-note path, from the seeded ``.obsidian/daily-notes.json``."""
    seed = vault / ".obsidian" / "daily-notes.json"
    cfg = json.loads(seed.read_text(encoding="utf-8"))
    y, m, d = today.split("-")
    stamp = cfg["format"].replace("YYYY", y).replace("MM", m).replace("DD", d)
    folder = cfg["folder"].rstrip("/")
    return f"{folder}/{stamp}.md"


def _template_rel(vault: Path) -> str:
    seed = vault / ".obsidian" / "daily-notes.json"
    cfg = json.loads(seed.read_text(encoding="utf-8"))
    return f"{cfg['template']}.md"


def _abs(vault: Path, rel: str) -> Path:
    return vault / rel


def _kv(tokens: list[str]) -> tuple[dict[str, str], list[str]]:
    kv: dict[str, str] = {}
    pos: list[str] = []
    for t in tokens:
        if "=" in t:
            k, v = t.split("=", 1)
            kv[k] = v
        else:
            pos.append(t)
    return kv, pos


def _resolve_by_name(vault: Path, name: str) -> str | None:
    """Wikilink-style resolve: match a bare name (with or without .md) to a file.

    Dot-folders (`.claude/`, `.obsidian/`, `.vault/`) are not vault-indexed notes,
    so Obsidian's link resolver ignores them — and so do we."""
    name = name[:-3] if name.endswith(".md") else name
    matches = []
    for p in vault.rglob(f"{name}.md"):
        rel = p.relative_to(vault)
        if p.is_file() and not any(seg.startswith(".") for seg in rel.parts):
            matches.append(rel.as_posix())
    return matches[0] if len(matches) == 1 else None


# --------------------------------------------------------------- state / trace


def _load_active(state_path: Path) -> str | None:
    if state_path.is_file():
        return json.loads(state_path.read_text(encoding="utf-8")).get("active")
    return None


def _save_active(state_path: Path, active: str | None) -> None:
    state_path.write_text(json.dumps({"active": active}), encoding="utf-8")


def _emit(trace_path: Path, record: dict) -> None:
    with trace_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


# --------------------------------------------------------------- the CLI


def run(
    argv: list[str],
    *,
    vault: Path,
    state_path: Path,
    trace_path: Path,
    today: str,
) -> tuple[int, str]:
    """Execute one ``obsidian`` invocation; append a trace line; return (code, out)."""
    vault = Path(vault)
    op = argv[0] if argv else ""
    kv, pos = _kv(argv[1:])
    active = _load_active(state_path)
    daily_rel = _daily_rel(vault, today)

    rec: dict = {
        "argv": list(argv),
        "op": op,
        "target": None,
        "fallback": False,
        "wrote": False,
        "created": False,
        "pre_exists": None,
        "overwrite": False,
        "payload": None,
        "returned_id": None,
    }
    out = ""
    code = 0

    def _read_target(kv: dict, pos: list) -> tuple[str | None, bool]:
        """Resolve a read/file target. Returns (rel, fallback) — an omitted or
        unresolved path=/file= silently returns the *active* note (40ab880)."""
        if "path" in kv:
            rel = kv["path"]
            if _abs(vault, rel).is_file():
                return rel, False
            return active, True  # unresolved path -> active-note fallback
        if "file" in kv:
            rel = _resolve_by_name(vault, kv["file"])
            if rel is not None:
                return rel, False
            return active, True  # unresolved name -> active-note fallback
        return active, True  # omitted target -> active-note fallback

    try:
        if op == "vault":
            out = _read_config_name(vault)

        elif op == "daily:path":
            rec["target"] = daily_rel
            out = daily_rel

        elif op == "daily:read":
            # SHARP EDGE: opening the daily note can create it. Used as an
            # existence probe, this reports "already existed" for a note it made.
            rec["target"] = daily_rel
            path = _abs(vault, daily_rel)
            if not path.is_file():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    _abs(vault, _template_rel(vault)).read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
                rec["wrote"] = rec["created"] = True
            active = daily_rel
            rec["returned_id"] = daily_rel
            out = path.read_text(encoding="utf-8")

        elif op == "daily:append":
            rec["target"] = daily_rel
            path = _abs(vault, daily_rel)
            rec["pre_exists"] = path.is_file()
            if not path.is_file():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    _abs(vault, _template_rel(vault)).read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
                rec["created"] = True
            content = kv.get("content", "")
            with path.open("a", encoding="utf-8") as fh:
                fh.write(("\n" if not content.startswith("\n") else "") + content)
            active = daily_rel
            rec["wrote"] = True
            rec["payload"] = content

        elif op == "files":
            files = sorted(p.relative_to(vault).as_posix() for p in vault.rglob("*") if p.is_file())
            out = "\n".join(files)

        elif op == "file":
            if not kv:  # `obsidian file` reports the active note (legitimate)
                rec["target"] = active
                rec["returned_id"] = active
                out = active or ""
            else:
                rel, fb = _read_target(kv, pos)
                rec["target"] = rel
                rec["fallback"] = fb
                rec["returned_id"] = rel
                out = rel or ""

        elif op == "read":
            rel, fb = _read_target(kv, pos)
            rec["target"] = rel
            rec["fallback"] = fb
            rec["returned_id"] = rel
            out = _abs(vault, rel).read_text(encoding="utf-8") if rel else ""

        elif op == "create":
            rel = kv.get("path", "")
            rec["target"] = rel
            overwrite = "overwrite" in pos or kv.get("overwrite") == "true"
            rec["overwrite"] = overwrite
            path = _abs(vault, rel)
            rec["pre_exists"] = path.is_file()
            if "template" in kv:
                content = _abs(
                    vault,
                    _template_rel(vault)
                    if kv["template"] in ("", "daily")
                    else f"{kv['template']}.md",
                ).read_text(encoding="utf-8")
            else:
                content = kv.get("content", "")
            if path.is_file() and not overwrite:
                raise StubError(f"create: refusing to overwrite existing {rel}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            rec["wrote"] = True
            rec["created"] = not rec["pre_exists"]
            rec["payload"] = content

        elif op == "append":
            rel, fb = _read_target(kv, pos)
            rec["target"] = rel
            rec["fallback"] = fb
            content = kv.get("content", "")
            if rel:
                path = _abs(vault, rel)
                rec["pre_exists"] = path.is_file()
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as fh:
                    fh.write(("\n" if not content.startswith("\n") else "") + content)
                rec["wrote"] = True
            rec["payload"] = content

        elif op == "command":
            cid = kv.get("id", "")
            rec["op"] = f"command:{cid}"
            if cid == "daily-notes":
                rec["target"] = daily_rel
                path = _abs(vault, daily_rel)
                rec["pre_exists"] = path.is_file()
                if not path.is_file():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(
                        _abs(vault, _template_rel(vault)).read_text(encoding="utf-8"),
                        encoding="utf-8",
                    )
                    rec["wrote"] = rec["created"] = True
                active = daily_rel
            elif cid == "templater-obsidian:replace-in-file-templater":
                rec["op"] = "command:templater"
                rec["target"] = active
                if active:
                    path = _abs(vault, active)
                    before = path.read_text(encoding="utf-8")
                    after = resolve_templater(before, today)
                    if after != before:
                        path.write_text(after, encoding="utf-8")
                        rec["wrote"] = True

        elif op == "tasks":
            lines = []
            for p in sorted(vault.rglob("*.md")):
                for line in p.read_text(encoding="utf-8").splitlines():
                    if re.match(r"\s*[-*+] \[ \]", line):
                        lines.append(line.strip())
            out = "\n".join(lines)

        elif op == "property:set":
            rel = kv.get("file") or active
            rec["target"] = rel
            rec["payload"] = f"{kv.get('name', '')}: {kv.get('value', '')}"
            rec["wrote"] = True  # frontmatter edit; contract allows own keys

        elif op == "plugins:enabled":
            seed = vault / ".obsidian" / "community-plugins.json"
            ids = json.loads(seed.read_text(encoding="utf-8")) if seed.is_file() else []
            out = "\n".join(ids)

        elif op in DESTRUCTIVE_OPS:
            # Escalate-only ops; the stub performs them so a bad transcript that
            # runs one is caught by the additive-only contract.
            rec["target"] = kv.get("path") or kv.get("from")
            rec["wrote"] = True
            if op == "delete" and rec["target"]:
                tgt = _abs(vault, rec["target"])
                if tgt.is_file():
                    tgt.unlink()

        else:
            code = 2
            out = f"stub: unknown command {op!r}"

    except StubError as exc:
        code = 1
        out = str(exc)

    rec["code"] = code
    _save_active(state_path, active)
    _emit(trace_path, rec)
    return code, out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    vault = Path(os.environ["OBSIDIAN_STUB_VAULT"])
    state_path = Path(os.environ["OBSIDIAN_STUB_STATE"])
    trace_path = Path(os.environ["OBSIDIAN_STUB_TRACE"])
    today = os.environ.get("ONYXIAN_NOW", "2026-01-01")
    code, out = run(argv, vault=vault, state_path=state_path, trace_path=trace_path, today=today)
    if out:
        sys.stdout.write(out)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
