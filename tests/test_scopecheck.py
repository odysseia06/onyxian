"""The per-agent scope-check decision engine (issue #11, phase 3).

A pure, stdlib-only function that reads an obsidian-CLI command line and an agent's
resolved write globs and answers three-valued: provably in scope -> allow, provably
out -> deny, unprovable (name resolution, omitted target, unknown shape) -> ask.
Read-only and non-obsidian commands are never blocked.
"""

from __future__ import annotations

import pytest

from onyxian.scopecheck import ALLOW, ASK, DENY, evaluate

WRITE = ["Daily-Notes/**", "Reading/**", "Courses/*/Exam-Prep/**"]

# (command, daily_note, expected verdict)
CASES = [
    # read-only obsidian ops are always allowed through
    ('obsidian read path="Secret/anything.md"', None, ALLOW),
    ("obsidian files", None, ALLOW),
    ("obsidian daily:path", None, ALLOW),
    ("obsidian tasks", None, ALLOW),
    # non-obsidian commands are out of the hook's remit (documented Bash hole)
    ("ls -la Secret", None, ALLOW),
    ("git status", None, ALLOW),
    # provable, in scope -> allow
    ('obsidian create path="Reading/Articles/a.md" content="hi"', None, ALLOW),
    ('obsidian append path="Daily-Notes/2026/01/x.md" content="- [ ] t"', None, ALLOW),
    ('obsidian create path="Reading/x.md" overwrite content="hi"', None, ALLOW),
    ('obsidian create path="Courses/CS101/Exam-Prep/review.md" content="x"', None, ALLOW),
    ("obsidian create path='Reading/quote note.md' content=x", None, ALLOW),
    # provable, out of scope -> deny
    ('obsidian create path="Secret/a.md" content="hi"', None, DENY),
    ('obsidian append path="Journal/2026.md" content="x"', None, DENY),
    ('obsidian create path="Courses/CS101/Notes/x.md" content="x"', None, DENY),
    ('obsidian delete path="Secret/x.md"', None, DENY),
    # unprovable -> ask
    ('obsidian append file="Some Note" content="x"', None, ASK),
    ('obsidian append content="x"', None, ASK),
    ('obsidian property:set file="A Note" name=status value=done', None, ASK),
    ("obsidian daily:append content=x", None, ASK),  # no daily note resolved
    ("obsidian frobnicate path=Reading/x.md", None, ASK),  # unknown mutating shape
    # daily:append is provable once the daily note is resolved from config
    ("obsidian daily:append content=x", "Daily-Notes/2026/01/01.md", ALLOW),
    ("obsidian daily:append content=x", "Journal/2026-01-01.md", DENY),
    # compound: strictest wins (deny > ask > allow)
    ('obsidian read path=X && obsidian create path="Secret/y.md"', None, DENY),
    ('obsidian create path="Reading/a.md" && obsidian append file="B"', None, ASK),
    ('obsidian create path="Reading/a.md" ; obsidian append path="Daily-Notes/b.md"', None, ALLOW),
]


@pytest.mark.parametrize("command,daily,expected", CASES)
def test_scope_check_decisions(command, daily, expected):
    assert evaluate(command, WRITE, daily_note=daily).verdict == expected, command


def test_deny_reason_names_the_offending_target_and_scope():
    d = evaluate('obsidian create path="Secret/a.md" content="x"', WRITE)
    assert d.verdict == DENY
    assert "Secret/a.md" in d.reason
    assert "write scope" in d.reason.lower()


def test_whole_vault_scope_allows_anything_written():
    d = evaluate('obsidian create path="Anywhere/Deep/x.md" content="x"', ["**"])
    assert d.verdict == ALLOW


def test_readonly_agent_denies_every_mutation():
    d = evaluate('obsidian create path="X/y.md" content="x"', [])
    assert d.verdict == DENY
