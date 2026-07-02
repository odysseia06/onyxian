"""Thin YAML loading with readable failure messages."""

from __future__ import annotations

from pathlib import Path

import yaml

from .errors import OnyxianError
from .fsio import read_text


def load_yaml(path: Path, *, what: str) -> object:
    """Parse a YAML file; an empty file parses as an empty mapping."""
    try:
        text = read_text(path)
    except FileNotFoundError:
        raise OnyxianError(f"{what} not found: {path}") from None
    except OSError as exc:
        raise OnyxianError(f"cannot read {what} {path}: {exc}") from None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise OnyxianError(f"{what} {path} is not valid YAML: {exc}") from None
    return {} if data is None else data


def require_mapping(data: object, *, what: str) -> dict:
    if not isinstance(data, dict):
        raise OnyxianError(f"{what} must be a YAML mapping, got {type(data).__name__}")
    return data
