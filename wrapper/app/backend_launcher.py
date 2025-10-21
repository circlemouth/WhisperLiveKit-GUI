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
    try:
        import torch.hub as hub  # type: ignore
    except ModuleNotFoundError:  # pragma: no cover - optional dependency
        print("[wrapper.backend_launcher] torch not available; skipping torch.hub trust patch.", file=sys.stderr, flush=True)
        return
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[wrapper.backend_launcher] failed to prepare torch.hub patch: {exc}", file=sys.stderr, flush=True)
        return

    _orig_load = hub.load

    def _load_with_trust_repo(repo_or_dir, model, *args, trust_repo=None, **kwargs):
        if trust_repo is None:
            trust_repo = True
        return _orig_load(repo_or_dir, model, *args, trust_repo=trust_repo, **kwargs)

    hub.load = _load_with_trust_repo


_patch_torch_hub()

# Ensure upstream submodule is importable as `whisperlivekit`
def _ensure_upstream_on_path() -> None:
    """Ensure the packaged submodule is preferred over any legacy copy."""

    repo_root = Path(__file__).resolve().parents[2]
    legacy_path = (repo_root / "whisperlivekit").resolve()
    upstream_path = (repo_root / "submodules" / "WhisperLiveKit").resolve()

    def _path_matches(entry: str, target: Path) -> bool:
        try:
            return Path(entry).resolve() == target
        except Exception:
            return False

    # Drop legacy path from sys.path so it cannot shadow the submodule.
    sys.path = [p for p in sys.path if not _path_matches(p, legacy_path)]

    # Remove already-imported modules that originated from the legacy path.
    for name in list(sys.modules.keys()):
        if name != "whisperlivekit" and not name.startswith("whisperlivekit."):
            continue
        module = sys.modules.get(name)
        module_file = getattr(module, "__file__", None)
        if not module_file:
            continue
        try:
            module_root = Path(module_file).resolve()
        except Exception:
            continue
        if module_root == legacy_path or legacy_path in module_root.parents:
            sys.modules.pop(name, None)

    if upstream_path.exists():
        upstream_str = str(upstream_path)
        if not any(_path_matches(p, upstream_path) for p in sys.path):
            sys.path.insert(0, upstream_str)


_ensure_upstream_on_path()

# Defer import until after patching and sys.path setup
basic_server = importlib.import_module("whisperlivekit.basic_server")


def main() -> None:
    basic_server.main()


if __name__ == "__main__":  # pragma: no cover
    main()
