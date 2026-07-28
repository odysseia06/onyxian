"""Expected, user-facing engine failures, and the CLI's exit-code convention.

Every error a user can trigger through normal use derives from ``OnyxianError``;
the CLI turns these into a one-line ``error:`` message and ``EXIT_ERROR``.
Anything else escaping to the top level is a bug and keeps its traceback.

Exit codes are three-valued and mean the same thing in every command, so a script
can branch on them without reading prose (#66). This is the one documented home;
`cli.py`'s invariant 5 and `docs/user-guide.md` both point here:

* ``EXIT_OK`` (0) — the command ran and nothing is outstanding. Also every dry run:
  a dry run reports what *would* happen and is not itself a finding.
* ``EXIT_ERROR`` (1) — the command could not do its job: a raised ``OnyxianError``,
  an argparse usage error, a declined confirmation, an apply that had to skip a
  write. Anything a script should treat as "this run did not count".
* ``EXIT_FINDINGS`` (2) — the command ran fine and is *reporting*: `plan` has
  changes pending, `diff` has conflict pairs or leftovers, `doctor` has a WARN or
  a FAIL, `module lint` found an authoring-convention violation. Never an error;
  `--json` carries which and how bad.

130 (interrupt) is the only other value the CLI returns.
"""

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_FINDINGS = 2


class OnyxianError(Exception):
    """Base class for all expected engine failures."""


class ConfigError(OnyxianError):
    """`.vault/config.yaml` is missing, malformed, or violates the schema (§4.4)."""


class ManifestError(OnyxianError):
    """A `module.yaml` is malformed or violates the manifest schema (§5.2)."""


class AnswersError(OnyxianError):
    """An `--answers` or profile file is malformed (§9.1, §5.5)."""


class PathError(OnyxianError):
    """A vault-relative path is invalid or unsafe on some supported OS (§9.5)."""


class ResolveError(OnyxianError):
    """Module set cannot be resolved: missing module, missing dependency, conflict, cycle,
    or bad variable."""


class RenderError(OnyxianError):
    """Asset rendering failed, e.g. an undefined `{{variable}}` (§5.3)."""


class LockError(OnyxianError):
    """`.vault/lock.json` is malformed or internally inconsistent (§8.1)."""


class ApplyError(OnyxianError):
    """A write could not be performed safely under the §8 contract."""


class VaultStateError(OnyxianError):
    """The target directory is in the wrong state for the command
    (e.g. `init` on a non-empty directory)."""


class VaultBusyError(OnyxianError):
    """Another process is already mutating this vault: the coarse write mutex
    (`.vault/apply.lock`) is held (issue #8)."""


class CheckpointError(OnyxianError):
    """A requested checkpoint restore is invalid or could not be completed safely."""
