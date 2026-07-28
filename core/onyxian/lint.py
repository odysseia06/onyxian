"""`onyxian module lint` — mechanical enforcement of the authoring conventions (#75).

`core/conventions/authoring.md`, `frontmatter.md`, and `naming.md` were enforced by
human review alone; the research-module frontmatter drift shipped precisely because
nothing checked module content against them. This is that check, and it is the same
one the repo runs over `modules/` — third-party authors get no weaker a bar (§14 M4).

Division of labour: *structural* validation stays in `manifests.py`, which raises on a
malformed manifest. Lint calls it and reports the failure as a finding instead, so a
sweep over a library keeps going and so `--json` carries every problem in one report.
Everything else here is a convention a valid manifest can still violate.

Findings, `--json`, and the exit codes are doctor's, unchanged: `lint` is a *reporting*
command, so a violation is exit 2 and never exit 1 (#66, see errors.py).
"""

from __future__ import annotations

import re
from pathlib import Path

from .doctor import FAIL, INFO, WARN, Finding
from .errors import ManifestError, OnyxianError, PathError
from .fsio import iter_files, read_text
from .intent import ENGINE_GLOBALS, INJECTED_VARS
from .manifests import load_manifest
from .model import Manifest, ProvidedFile
from .paths import check_casefold_unique, check_reserved_new_suffix
from .render import PLACEHOLDER_RE

CORE_FRONTMATTER_KEYS = ("type", "created", "status", "tags")
PAPER_FRONTMATTER_KEYS = ("type", "date_added", "status", "tags")

# A Templater body is code, not an engine reference — except when it names an engine
# variable, which is the confusion the two-placeholder-languages rule exists to stop.
_TEMPLATER_BODY_RE = re.compile(r"<%\*?-?\s*([A-Za-z0-9_.-]+)\s*-?%>")
_CHECKBOX_MACRO_RE = re.compile(r"^\s*[-*+] \[[ xX]\].*<%")
_YAML_KEY_RE = re.compile(r"^([A-Za-z0-9_-]+):", re.M)
_PAPER_TAG_RE = re.compile(r"^\s*-\s*paper\s*$", re.M)

# Markdown that starts a new block, so a line matching it is never a wrapped
# continuation of the line above: list item, heading, quote/callout, table row,
# thematic break, Templater block, Obsidian comment, or a YAML key (frontmatter).
_BLOCK_START_RE = re.compile(
    r"^\s*(([-*+]|\d+[.)])(\s|$)|#{1,6}\s|>|\||---\s*$|<%|%%|[A-Za-z0-9_-]+:(\s|$))"
)
# Blocks that also *end* at their own line: whatever follows a heading, a table row, or a
# rule opens a new block, so it is never a continuation either. A bullet is not one of
# these — a plain line under a bullet is a lazy continuation, i.e. the wrap we are hunting.
_BLOCK_END_RE = re.compile(r"^\s*(#{1,6}\s|\||---\s*$)")
_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")


def _prose_lines(text: str) -> list[tuple[int, str]]:
    """``(lineno, line)`` for every line that is prose the conventions govern.

    Skips what is not prose and would otherwise read as wrapped text: YAML frontmatter,
    fenced code (nesting-aware — a ```` ```tasks ```` block inside a ```` ```` ```` fence
    must not close it), and multi-line Templater blocks. A blank line is kept, as the
    caller needs it to know where a paragraph ends.
    """
    out: list[tuple[int, str]] = []
    fence = ""
    in_frontmatter = in_templater = False
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if lineno == 1 and stripped == "---":
            in_frontmatter = True
            continue
        if in_frontmatter:
            in_frontmatter = stripped != "---"
            continue
        if in_templater:
            in_templater = "%>" not in line
            continue
        marker = _FENCE_RE.match(line)
        if fence:
            if marker and marker.group(1)[0] == fence[0] and len(marker.group(1)) >= len(fence):
                fence = ""
            continue
        if marker:
            fence = marker.group(1)
            out.append((lineno, ""))
            continue
        if "<%" in line and "%>" not in line[line.index("<%") :]:
            in_templater = True
            out.append((lineno, ""))
            continue
        out.append((lineno, line))
    return out


def hardwrap_lines(text: str) -> list[int]:
    """Line numbers that continue the line above instead of starting their own block.

    One logical line per paragraph and per bullet (authoring.md): a continuation is
    either prose hard-wrapped at some column or a paragraph missing the blank line
    before it, and Obsidian renders both as a break partway through a sentence.
    """
    hits: list[int] = []
    continuable = False
    for lineno, line in _prose_lines(text):
        if not line.strip():
            continuable = False
            continue
        if continuable and not _BLOCK_START_RE.match(line):
            hits.append(lineno)
        continuable = not _BLOCK_END_RE.match(line)
    return hits


def frontmatter_block(text: str) -> str | None:
    """The note's raw YAML frontmatter, or None when it has none.

    Read as text, not parsed as YAML: a template's frontmatter legitimately holds
    ``{{root}}`` and ``<% tp.date.now() %>``, neither of which is valid YAML, and key
    *presence* is all the core schema is about. A leading Templater block is skipped —
    the paper templates prompt for values above the frontmatter they then fill.
    """
    lines = text.splitlines()
    start = 0
    if lines and lines[0].strip().startswith("<%"):
        while start < len(lines) and "%>" not in lines[start]:
            start += 1
        start += 1
    while start < len(lines) and not lines[start].strip():
        start += 1
    if start >= len(lines) or lines[start].strip() != "---":
        return None
    for end in range(start + 1, len(lines)):
        if lines[end].strip() == "---":
            return "\n".join(lines[start + 1 : end])
    return None


def _known_variables(manifest: Manifest) -> set[str]:
    """Every unqualified ``{{name}}`` this module may reference."""
    return {v.key for v in manifest.variables} | set(INJECTED_VARS.get(manifest.name, ()))


def _check_placeholders(
    text: str, *, where: str, known: set[str], modules: set[str]
) -> list[Finding]:
    """The two placeholder languages, used correctly and only on declared names.

    An undeclared ``{{name}}`` is a RenderError at apply time in every vault that enables
    the module — a lint finding here is the same failure, found before install. ``modules``
    is which other modules this text may read: the declared dependencies, plus the module a
    scope entry names in ``requires:``, which is dropped at render time when absent (§7.3).
    """
    findings: list[Finding] = []
    for name in sorted(set(PLACEHOLDER_RE.findall(text))):
        if name.startswith("tp."):
            findings.append(
                Finding(
                    FAIL,
                    f"{where}: {{{{{name}}}}} is a Templater macro in engine delimiters",
                    f"Templater owns `<% {name}(...) %>`; the engine owns {{{{variable}}}}",
                )
            )
        elif "." not in name:
            if name not in known:
                findings.append(
                    Finding(
                        FAIL,
                        f"{where}: {{{{{name}}}}} is not a variable this module declares",
                        f"add {name!r} under `variables:` in module.yaml, or fix the reference",
                    )
                )
        elif name.startswith("onyxian."):
            if name.removeprefix("onyxian.") not in ENGINE_GLOBALS:
                findings.append(
                    Finding(
                        FAIL,
                        f"{where}: {{{{{name}}}}} is not an engine global",
                        f"the globals are {', '.join('onyxian.' + g for g in ENGINE_GLOBALS)}",
                    )
                )
        elif name.split(".", 1)[0].replace("_", "-") not in modules:
            other = name.split(".", 1)[0]
            findings.append(
                Finding(
                    FAIL,
                    f"{where}: {{{{{name}}}}} reads module {other!r}, which is not available here",
                    f"add {other!r} to `depends:`, or — in an agent scope — "
                    f"give the entry `requires: {other}` so it drops when {other} is absent",
                )
            )
    for body in sorted(set(_TEMPLATER_BODY_RE.findall(text))):
        if body in known or body.startswith("onyxian."):
            findings.append(
                Finding(
                    FAIL,
                    f"{where}: <% {body} %> is an engine variable in Templater delimiters",
                    f"the engine substitutes {{{{{body}}}}}; Templater never sees it",
                )
            )
    return findings


def _check_markdown(text: str, *, where: str, field: str = "") -> list[Finding]:
    """Prose conventions for one piece of markdown.

    ``field`` names the manifest/agent field the text came from, when it is not a whole
    file: its line numbers are then within that block scalar, not within the file, and the
    message says so rather than printing a ``file:line`` a reader cannot jump to.
    """

    def at(lineno: int) -> str:
        return f"{where} ({field}, line {lineno})" if field else f"{where}:{lineno}"

    findings = [
        Finding(
            WARN,
            f"{at(lineno)} continues the line above instead of starting its own block",
            "one logical line per paragraph and per bullet — join the lines, "
            "or separate them with a blank line (authoring.md)",
        )
        for lineno in hardwrap_lines(text)
    ]
    findings.extend(
        Finding(
            WARN,
            f"{at(lineno)} is a literal checkbox carrying a raw Templater macro",
            "the Tasks plugin scans it as a phantom open task; let Templater emit the "
            "checkbox instead of shipping it literally",
        )
        # Fenced examples are documentation, not tasks — the Tasks plugin skips them too.
        for lineno, line in _prose_lines(text)
        if _CHECKBOX_MACRO_RE.match(line)
    )
    return findings


def _check_frontmatter(where: str, text: str) -> list[Finding]:
    """Framework-created notes carry the core four (frontmatter.md), paper notes their own."""
    block = frontmatter_block(text)
    if block is None:
        return [
            Finding(
                WARN,
                f"{where}: no YAML frontmatter",
                "framework-created notes are typed notes: "
                f"add {', '.join(CORE_FRONTMATTER_KEYS)} (frontmatter.md)",
            )
        ]
    # The one documented exception: a `paper` tag marks the note class, and the paper
    # schema *replaces* the core default (`date_added` instead of `created`).
    is_paper = _PAPER_TAG_RE.search(block) is not None
    required = PAPER_FRONTMATTER_KEYS if is_paper else CORE_FRONTMATTER_KEYS
    keys = set(_YAML_KEY_RE.findall(block))
    missing = [key for key in required if key not in keys]
    if not missing:
        return []
    return [
        Finding(
            WARN,
            f"{where}: frontmatter is missing {', '.join(missing)}",
            f"the schema for this note class is {', '.join(required)} (frontmatter.md); "
            "document a deliberate exception there before dropping a key",
        )
    ]


def _check_assets(manifest: Manifest, provided: tuple[ProvidedFile, ...]) -> list[Finding]:
    """Nothing under `assets/` may be unlisted: what the manifest does not name never
    installs, so it is invisible weight in a tree whose whole point is being reviewable by
    reading (§5.1). `load_manifest` already enforces the same rule for skills/ and agents/."""
    assets_dir = manifest.directory / "assets"
    if not assets_dir.is_dir():
        return []
    declared = {p.source.resolve() for p in provided}
    unlisted = sorted(
        p.relative_to(assets_dir).as_posix()
        for p in iter_files(assets_dir)
        if p.resolve() not in declared
    )
    if not unlisted:
        return []
    return [
        Finding(
            FAIL,
            f"asset(s) under assets/ that the manifest never installs: {', '.join(unlisted)}",
            "list each under provides.templates / provides.bases / seeds, or delete it",
        )
    ]


def lint_module(module_dir: Path) -> list[Finding]:
    """Every authoring-convention finding for one module directory."""
    # Resolved first: the manifest's `name` must equal the directory name, and the
    # name of `.` — the command's default, i.e. "lint the module I am standing in" — is
    # the empty string until it is.
    module_dir = module_dir.resolve()
    if not (module_dir / "module.yaml").is_file():
        raise ManifestError(f"{module_dir} has no module.yaml; it is not a module directory")
    try:
        manifest = load_manifest(module_dir)
    except OnyxianError as exc:
        # Everything below reads the parsed manifest, so this is the end of the report.
        return [Finding(FAIL, f"manifest does not validate: {exc}")]

    findings: list[Finding] = []
    provided = manifest.templates + manifest.bases + manifest.seeds
    findings.extend(_check_assets(manifest, provided))

    install_paths = [(p.install_path, manifest.name) for p in provided]
    historical_paths = [(rename.old_path, manifest.name) for rename in manifest.renames]
    for check, paths in (
        (check_reserved_new_suffix, install_paths + historical_paths),
        (check_casefold_unique, install_paths),
    ):
        try:
            check(paths)
        except PathError as exc:
            findings.append(Finding(FAIL, str(exc)))

    known = _known_variables(manifest)
    deps = set(manifest.depends)

    def placeholders(text: str, where: str, *, requires: str | None = None) -> list[Finding]:
        return _check_placeholders(
            text, where=where, known=known, modules=(deps | {requires}) if requires else deps
        )

    for raw in (*manifest.folders, *(p.install_path for p in provided)):
        findings.extend(placeholders(raw, f"install path {raw!r}"))
    for rename in manifest.renames:
        findings.extend(placeholders(rename.old_path, f"rename source {rename.old_path!r}"))
        findings.extend(placeholders(rename.new_path, f"rename destination {rename.new_path!r}"))

    for provided_file in provided:
        text = read_text(provided_file.source)
        where = provided_file.install_path
        findings.extend(placeholders(text, where))
        if where.endswith(".md"):
            findings.extend(_check_markdown(text, where=where))
            findings.extend(_check_frontmatter(where, text))

    # Skills are copied verbatim, never rendered, so only their prose is in scope;
    # agent definitions are rendered, so both checks apply to their prose fields.
    for skill in manifest.skills:
        for md in iter_files(skill.directory):
            if md.suffix == ".md":
                rel = md.relative_to(manifest.directory).as_posix()
                findings.extend(_check_markdown(read_text(md), where=rel))
    for agent in manifest.agents:
        where = f"agents/{agent.name}.yaml"
        for field, prose in (
            ("mission", agent.mission),
            ("playbook", agent.playbook),
            ("disclaimer", agent.disclaimer),
        ):
            findings.extend(_check_markdown(prose, where=where, field=field))
            findings.extend(placeholders(prose, f"{where} ({field})"))
        for entry in (*agent.read, *agent.write):
            findings.extend(
                placeholders(
                    entry.pattern, f"{where} scope {entry.pattern!r}", requires=entry.requires
                )
            )
        for trigger in agent.triggers:
            findings.extend(placeholders(trigger, f"{where} trigger {trigger!r}"))

    if not findings:
        findings.append(Finding(INFO, f"module {manifest.name!r} v{manifest.version}: clean"))
    return findings
