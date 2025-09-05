from __future__ import annotations

"""Backend launcher that ensures torch.hub.load trusts the repository.

This is a workaround for upstream TranscriptionEngine which calls
``torch.hub.load`` without ``trust_repo=True`` when downloading the
Silero VAD model. PyTorch 2.x defaults to trusting none which may raise
an exception on first download. By monkeypatching ``torch.hub.load`` to
set ``trust_repo=True`` when unspecified, the backend remains compatible
without requiring upstream modification.
"""

import importlib
import sys
from pathlib import Path


def _patch_torch_hub() -> None:
    import torch.hub as hub  # type: ignore

    _orig_load = hub.load

    def _load_with_trust_repo(repo_or_dir, model, *args, trust_repo=None, **kwargs):
        if trust_repo is None:
            trust_repo = True
        return _orig_load(repo_or_dir, model, *args, trust_repo=trust_repo, **kwargs)

    hub.load = _load_with_trust_repo


_patch_torch_hub()

# Ensure upstream submodule is importable as `whisperlivekit`
def _ensure_upstream_on_path() -> None:
    """Add the WhisperLiveKit submodule to sys.path if needed.

    Looks for `submodules/WhisperLiveKit` (git submodule path) from repo root
    and appends it to `sys.path` so that `import whisperlivekit` works
    without installing from PyPI.
    """
    try:
        import whisperlivekit  # noqa: F401
        return
    except Exception:
        pass

    repo_root = Path(__file__).resolve().parents[2]
    candidate = repo_root / "submodules" / "WhisperLiveKit"
    if candidate.exists():
        sys.path.insert(0, str(candidate))


_ensure_upstream_on_path()

# Defer import until after patching and sys.path setup
basic_server = importlib.import_module("whisperlivekit.basic_server")


def main() -> None:
    basic_server.main()


if __name__ == "__main__":  # pragma: no cover
    main()
