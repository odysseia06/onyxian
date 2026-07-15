"""The per-agent scope-check decision engine (issue #11, phase 3).

Pure and stdlib-only (``shlex``, ``fnmatch``): given an ``obsidian``-CLI command
line and an agent's resolved write globs, decide three-valued —

- **allow**  every mutating subcommand provably targets the write globs;
- **deny**   a mutating subcommand provably targets outside them;
- **ask**    anything unprovable — ``file=`` name resolution, an omitted target
             (the active-note fallback), an unrecognized command shape, or a
             command that could not be parsed.

Read-only obsidian commands and non-``obsidian`` commands are never blocked: the
hook polices the sanctioned write path (the ``obsidian`` CLI), and the residual
holes — ``file=``/active-note targets that resolve *inside* Obsidian, and any
process that writes files without going through the CLI — cannot be closed by a
client-side hook and are documented, not hidden. ``ask`` *is* the escalation
floor made mechanical.

The engine is deliberately free of any filesystem or config access so it stays a
pure function; the one config-derived value it needs — today's daily-note path,
so ``daily:append`` becomes provable — is passed in by the caller.
"""

from __future__ import annotations

import fnmatch
import shlex
from dataclasses import dataclass

ALLOW = "allow"
DENY = "deny"
ASK = "ask"

_SEVERITY = {ALLOW: 0, ASK: 1, DENY: 2}

# obsidian subcommands that never mutate the vault — always allowed through.
_READ_ONLY = frozenset(
    {
        "vault", "files", "file", "read", "tasks", "search", "list", "open", "info",
        "help", "version", "plugins:enabled", "daily:path", "daily:read",
        "property:get", "properties",
    }
)
# Mutating ops whose target is `path=` (provable) — else `file=`/omitted is unprovable.
_PATH_MUTATING = frozenset({"create", "append", "write"})
# Restructuring ops; their path-shaped targets (`path`/`from`/`to`) are provable.
_DESTRUCTIVE = frozenset({"delete", "move", "rename", "property:remove"})

# Shell tokens that separate one command from the next (shlex punctuation_chars).
_OPERATORS = frozenset({"&&", "||", "|", "&", ";", ";;", "(", ")", "\n"})


@dataclass(frozen=True)
class Decision:
    verdict: str
    reason: str = ""


def _basename(command: str) -> str:
    """The bare executable name, so `/usr/local/bin/obsidian` and `Obsidian.com`
    both read as `obsidian` (the Windows redirector, §vault-operations)."""
    base = command.replace("\\", "/").rsplit("/", 1)[-1].lower()
    for ext in (".com", ".exe"):
        if base.endswith(ext):
            base = base[: -len(ext)]
    return base


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


def _normalize(path: str) -> str:
    p = path.strip()
    if p.startswith("./"):
        p = p[2:]
    return p.rstrip("/")


def _match(path: str, glob: str) -> bool:
    """Gitignore-style match where ``**`` spans path separators and ``*``/``?`` do not."""
    return _seg_match(_normalize(path).split("/"), glob.split("/"))


def _seg_match(p: list[str], g: list[str]) -> bool:
    if not g:
        return not p
    if g[0] == "**":
        return _seg_match(p, g[1:]) or (bool(p) and _seg_match(p[1:], g))
    if not p:
        return False
    if fnmatch.fnmatchcase(p[0], g[0]):
        return _seg_match(p[1:], g[1:])
    return False


def _check_targets(op: str, targets: list[str], write_globs: list[str]) -> Decision:
    for target in targets:
        norm = _normalize(target)
        if not any(_match(norm, glob) for glob in write_globs):
            return Decision(
                DENY, f"`obsidian {op}` writes `{norm}`, outside this agent's write scope"
            )
    return Decision(ALLOW)


def _decide_subcommand(
    tokens: list[str], write_globs: list[str], daily_note: str | None
) -> Decision:
    if not tokens:
        return Decision(ALLOW)
    if _basename(tokens[0]) != "obsidian":
        return Decision(ALLOW)  # not the sanctioned write path; out of this hook's remit
    if len(tokens) < 2:
        return Decision(ASK, "bare `obsidian` with no subcommand")
    op = tokens[1]
    kv, _pos = _kv(tokens[2:])

    if op in _READ_ONLY:
        return Decision(ALLOW)

    # daily:append (and the daily-notes command) target today's daily note, which
    # the caller resolves from config; without it the target is unprovable.
    if op == "daily:append" or (op == "command" and kv.get("id") == "daily-notes"):
        if daily_note:
            return _check_targets(op, [daily_note], write_globs)
        return Decision(ASK, "`daily:append` target (today's daily note) is not statically known")

    if op == "command":
        return Decision(
            ASK, f"`command id={kv.get('id', '')}` writes a target resolved inside Obsidian"
        )

    if op in _PATH_MUTATING:
        if "path" in kv:
            return _check_targets(op, [kv["path"]], write_globs)
        where = "file=" if "file" in kv else "an omitted"
        return Decision(ASK, f"`obsidian {op}` with {where} target resolves inside Obsidian")

    if op in _DESTRUCTIVE:
        targets = [kv[k] for k in ("path", "from", "to") if k in kv]
        if targets:
            return _check_targets(op, targets, write_globs)
        return Decision(ASK, f"`obsidian {op}` target resolves inside Obsidian")

    if op == "property:set":
        return Decision(ASK, "`property:set` targets a note by name or the active note")

    return Decision(ASK, f"unrecognized obsidian command `{op}`")


def evaluate(command: str, write_globs: list[str], *, daily_note: str | None = None) -> Decision:
    """Decide allow/deny/ask for one Bash command string against an agent's write scope."""
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        tokens = list(lex)
    except ValueError:
        return Decision(ASK, "command could not be parsed; cannot prove it stays in scope")

    worst = Decision(ALLOW)
    current: list[str] = []
    for token in [*tokens, ";"]:  # trailing sentinel flushes the last subcommand
        if token in _OPERATORS:
            decision = _decide_subcommand(current, write_globs, daily_note)
            if _SEVERITY[decision.verdict] > _SEVERITY[worst.verdict]:
                worst = decision
            current = []
        else:
            current.append(token)
    return worst
