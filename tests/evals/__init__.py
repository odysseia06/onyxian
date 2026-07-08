"""Behavioral eval harness for agent skills (issue #2).

Not part of the shipped engine — this package lives under ``tests/`` and executes
skill *procedures* (the deterministic morning scaffold, task capture) against a
fake ``obsidian`` CLI, then grades the recorded trace with pure-function
contracts. See ``README.md`` for what it can and cannot assert.
"""
