"""Packaged assets exposed by the wrapper runtime."""

from __future__ import annotations

from importlib import resources
from typing import Optional

_PACKAGED_WARMUP_RELATIVE = ("warmup", "whisper_warmup_jfk.wav")


def get_packaged_warmup_file() -> Optional[str]:
    """Return the absolute path to the bundled warmup audio if available."""
    try:
        traversable = resources.files(__name__).joinpath(*_PACKAGED_WARMUP_RELATIVE)
    except ModuleNotFoundError:
        return None

    try:
        with resources.as_file(traversable) as resolved:
            if resolved.is_file():
                return str(resolved)
    except FileNotFoundError:
        return None
    return None


__all__ = ["get_packaged_warmup_file"]
