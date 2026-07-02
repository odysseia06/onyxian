"""Expected, user-facing engine failures.

Every error a user can trigger through normal use derives from ``OnyxianError``;
the CLI turns these into a one-line ``error:`` message and exit code 1.
Anything else escaping to the top level is a bug and keeps its traceback.
"""


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
    """Module set cannot be resolved: missing module, missing dependency, conflict, cycle, or bad variable."""


class RenderError(OnyxianError):
    """Asset rendering failed, e.g. an undefined `{{variable}}` (§5.3)."""


class LockError(OnyxianError):
    """`.vault/lock.json` is malformed or internally inconsistent (§8.1)."""


class ApplyError(OnyxianError):
    """A write could not be performed safely under the §8 contract."""


class VaultStateError(OnyxianError):
    """The target directory is in the wrong state for the command (e.g. `init` on a non-empty directory)."""
