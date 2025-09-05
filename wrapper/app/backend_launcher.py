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


def _patch_torch_hub() -> None:
    import torch.hub as hub  # type: ignore

    _orig_load = hub.load

    def _load_with_trust_repo(repo_or_dir, model, *args, trust_repo=None, **kwargs):
        if trust_repo is None:
            trust_repo = True
        return _orig_load(repo_or_dir, model, *args, trust_repo=trust_repo, **kwargs)

    hub.load = _load_with_trust_repo


_patch_torch_hub()

# Defer import until after patching
basic_server = importlib.import_module("whisperlivekit.basic_server")


def main() -> None:
    basic_server.main()


if __name__ == "__main__":  # pragma: no cover
    main()
