from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Iterable

from . import model_manager


_SPEECHBRAIN_FILES: tuple[str, ...] = (
    "embedding_model.ckpt",
    "mean_var_norm_emb.ckpt",
    "classifier.ckpt",
    "label_encoder.txt",
)


def _pyannote_cache_root(env: dict[str, str] | None = None) -> Path:
    env = env or os.environ  # fall back to current process env
    # Priority: explicit PYANNOTE_CACHE -> TORCH_HOME/pyannote -> ~/.cache/torch/pyannote
    if "PYANNOTE_CACHE" in env and env["PYANNOTE_CACHE"].strip():
        return Path(env["PYANNOTE_CACHE"]).expanduser().resolve()
    if "TORCH_HOME" in env and env["TORCH_HOME"].strip():
        return Path(env["TORCH_HOME"]).expanduser().resolve() / "pyannote"
    # Default user cache path that pyannote/audio commonly uses
    return Path.home() / ".cache" / "torch" / "pyannote"


def configure_env_for_caches(env: dict[str, str]) -> None:
    """Populate cache-related environment variables for child processes.

    This keeps HF/torch/pyannote caches under the wrapper's own cache root
    and disables symlink usage in huggingface_hub for better Windows/MSIX
    compatibility.
    """
    # Hugging Face caches
    env.setdefault("HUGGINGFACE_HUB_CACHE", str(model_manager.HF_CACHE_DIR))
    # Prefer HF_HOME instead of TRANSFORMERS_CACHE to avoid deprecation warning
    env.setdefault("HF_HOME", str(model_manager.HF_CACHE_DIR))

    # Torch cache (used by torch.hub, and as base for pyannote by default)
    env.setdefault("TORCH_HOME", str(model_manager.TORCH_CACHE_DIR))

    # Do not force PYANNOTE_CACHE yet — decide after ensuring downloads.

    # Avoid symlink creation on Windows/MSIX (force real files)
    env.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")


def _default_hf_cache_root() -> Path:
    # Best-effort: mirror huggingface_hub default
    env_home = os.environ.get("HF_HOME", "").strip()
    if env_home:
        return Path(env_home)
    return Path.home() / ".cache" / "huggingface" / "hub"


def _hf_cache_roots() -> list[Path]:
    roots = [model_manager.HF_CACHE_DIR]
    try:
        default_root = _default_hf_cache_root()
        if default_root not in roots:
            roots.append(default_root)
    except Exception:
        pass
    return roots


def _find_in_snapshot(repo_id: str, names: Iterable[str]) -> dict[str, Path]:
    """Return map of filename -> path for files found in the local snapshot.

    Looks into the latest snapshot under the wrapper-managed HF cache.
    """
    found: dict[str, Path] = {}
    try:
        for root in _hf_cache_roots():
            snap_base = root / ("models--" + repo_id.replace("/", "--")) / "snapshots"
            if not snap_base.exists():
                continue
            # Pick latest snapshot first
            snaps = sorted([p for p in snap_base.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True)
            for snap in snaps:
                for name in names:
                    if name in found:
                        continue
                    cand = snap / name
                    if cand.exists():
                        found[name] = cand
            if len(found) == len(tuple(names)):
                break
    except Exception:
        pass
    return found


def materialize_speechbrain_files(env: dict[str, str] | None = None) -> None:
    """Ensure SpeechBrain ECAPA files exist as regular files (no symlinks).

    Some dependencies create symlinks pointing from the HF snapshot to a
    pyannote-local cache path (e.g. ~/.cache/torch/pyannote/speechbrain).
    On Windows/MSIX, symlinks may be unavailable or broken, leading to
    FileNotFoundError on those local paths. This function heals the state by
    copying required files into the pyannote location if missing, and by
    replacing any symlinks with real files.
    """
    env = env or os.environ
    pyannote_root = _pyannote_cache_root(env)
    sb_dir = pyannote_root / "speechbrain"
    sb_dir.mkdir(parents=True, exist_ok=True)

    # Locate files in local HF snapshot (wrapper-managed cache)
    repo_id = "speechbrain/spkrec-ecapa-voxceleb"
    snapshot_files = _find_in_snapshot(repo_id, _SPEECHBRAIN_FILES)
    if not snapshot_files:
        # Best-effort: try to ensure snapshot is present so we can source files
        try:
            model_manager.download_model(repo_id)
            snapshot_files = _find_in_snapshot(repo_id, _SPEECHBRAIN_FILES)
        except Exception:
            pass

    for name in _SPEECHBRAIN_FILES:
        dst = sb_dir / name
        try:
            if dst.exists() and dst.is_symlink():
                # Replace symlink with a real file if possible
                target: Path | None = None
                try:
                    target = Path(os.readlink(dst))  # may be relative
                    if not target.is_absolute():
                        target = (dst.parent / target).resolve()
                except Exception:
                    target = None
                if target and target.exists():
                    tmp = dst.with_suffix(dst.suffix + ".tmp")
                    shutil.copy2(target, tmp)
                    dst.unlink(missing_ok=True)
                    tmp.replace(dst)
                    continue
                # If target is unknown or missing, attempt to source from snapshot
                if name in snapshot_files:
                    dst.unlink(missing_ok=True)
                    shutil.copy2(snapshot_files[name], dst)
                    continue

            if not dst.exists():
                # Create from snapshot if present
                if name in snapshot_files:
                    shutil.copy2(snapshot_files[name], dst)
        except Exception:
            # Best-effort: never block startup on cache healing
            pass


def _has_pyannote_snapshot() -> bool:
    """Return True if segmentation-3.0 snapshot with weights exists in wrapper cache."""
    base = model_manager.HF_CACHE_DIR / "models--pyannote--segmentation-3.0" / "snapshots"
    try:
        if not base.exists():
            return False
        for snap in base.iterdir():
            if (snap / "pytorch_model.bin").exists():
                return True
    except Exception:
        pass
    return False


def align_pyannote_cache_env(env: dict[str, str]) -> None:
    """Set or clear PYANNOTE_CACHE based on availability in wrapper cache.

    - If wrapper-managed cache has the expected pyannote snapshots, set
      PYANNOTE_CACHE to that location so pyannote reads from it.
    - Otherwise, avoid setting PYANNOTE_CACHE so that pyannote falls back
      to its own default (usually HF_HOME or user cache), letting it download
      as needed without pointing to a missing path.
    """
    if _has_pyannote_snapshot():
        env["PYANNOTE_CACHE"] = str(model_manager.HF_CACHE_DIR)
    else:
        # Make sure we don't point to a non-existent wrapper cache
        if "PYANNOTE_CACHE" in env:
            env.pop("PYANNOTE_CACHE", None)

def ensure_pyannote_models() -> None:
    """Pre-download pyannote models used by Diart to avoid race/missing files.

    Download both the stable id and the 3.0 variant. If already present,
    this is a no-op as huggingface_hub uses the existing snapshot.
    """
    for repo_id in ("pyannote/segmentation-3.0", "pyannote/segmentation"):
        try:
            model_manager.download_model(repo_id)
        except Exception:
            # Best-effort: keep going even if one fails (e.g., missing auth)
            pass


def run(env: dict[str, str]) -> None:
    """Run all preflight steps to make backend startup MSIX-safe."""
    configure_env_for_caches(env)
    ensure_pyannote_models()
    materialize_speechbrain_files(env)
    align_pyannote_cache_env(env)
