from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

from platformdirs import user_cache_path

try:
    from huggingface_hub import snapshot_download
    from huggingface_hub.utils import tqdm as hf_tqdm
except Exception:  # pragma: no cover - optional dependency
    snapshot_download = None
    hf_tqdm = None

try:
    import torch
    import torch.hub  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    torch = None

# Root directory for Hugging Face cache used by the wrapper
HF_CACHE_DIR = user_cache_path("WhisperLiveKit", "wrapper") / "hf-cache"
HF_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Torch hub cache directory for non-HF models (e.g., Silero VAD)
TORCH_HUB_DIR = user_cache_path("WhisperLiveKit", "wrapper") / "torch-hub"
TORCH_HUB_DIR.mkdir(parents=True, exist_ok=True)

# VAD model repository identifier
VAD_MODEL = "snakers4/silero-vad"


def _resolve_repo_id(name: str) -> str:
    """Return full repo id for a given model name."""
    return name if "/" in name else f"openai/whisper-{name}"


def _cache_dir(repo_id: str) -> Path:
    safe = repo_id.replace("/", "--")
    return HF_CACHE_DIR / f"models--{safe}"


def get_model_path(name: str) -> Path:
    """Return local snapshot path for the model (latest if multiple)."""
    if name == VAD_MODEL:
        return TORCH_HUB_DIR
    repo = _resolve_repo_id(name)
    base = _cache_dir(repo)
    snapshots = base / "snapshots"
    if snapshots.exists():
        dirs = [p for p in snapshots.iterdir() if p.is_dir()]
        if dirs:
            return max(dirs, key=lambda p: p.stat().st_mtime)
    return base


def is_model_downloaded(name: str) -> bool:
    if name == VAD_MODEL:
        if torch is None:
            return False
        torch.hub.set_dir(str(TORCH_HUB_DIR))
        return any(p.is_dir() for p in TORCH_HUB_DIR.glob("snakers4_silero-vad*"))
    repo = _resolve_repo_id(name)
    snapshots = _cache_dir(repo) / "snapshots"
    return snapshots.exists() and any(p.is_dir() for p in snapshots.iterdir())


def list_downloaded_models() -> list[str]:
    models: list[str] = []
    for p in HF_CACHE_DIR.glob("models--*"):
        if (p / "snapshots").exists():
            repo_id = p.name[len("models--") :].replace("--", "/")
            models.append(repo_id)
    if is_model_downloaded(VAD_MODEL):
        models.append(VAD_MODEL)
    return models


class _TqdmWithCallback(hf_tqdm):
    """tqdm subclass that reports fractional progress via callback.

    Note: huggingface_hub expects a tqdm class (not an instance) and will
    access class attributes like `get_lock`. Therefore we cannot pass a
    functools.partial as `tqdm_class`. Instead, use a small class factory
    that returns a subclass binding the callback.
    """

    def __init__(self, *args, **kwargs):
        # Placeholder; real subclass binds _progress_cb via factory.
        self._progress_cb = kwargs.pop("_progress_cb", None)
        super().__init__(*args, **kwargs)

    def update(self, n=1):  # pragma: no cover - visual feedback only
        super().update(n)
        if self.total and self._progress_cb:
            try:
                self._progress_cb(self.n / self.total)
            except Exception:
                pass


def _make_tqdm_with_cb(progress_cb: Callable[[float], None] | None):
    class _BoundTqdm(_TqdmWithCallback):
        def __init__(self, *args, **kwargs):
            kwargs["_progress_cb"] = progress_cb
            super().__init__(*args, **kwargs)

    return _BoundTqdm


def download_model(name: str, progress_cb: Callable[[float], None] | None = None) -> Path:
    """Download model into cache directory."""
    if name == VAD_MODEL:
        if torch is None:
            raise RuntimeError("torch is required to download VAD model")
        torch.hub.set_dir(str(TORCH_HUB_DIR))
        if progress_cb:
            try:
                progress_cb(0.0)
            except Exception:
                pass
        torch.hub.load(VAD_MODEL, "silero_vad", trust_repo=True)
        if progress_cb:
            try:
                progress_cb(1.0)
            except Exception:
                pass
        return TORCH_HUB_DIR
    if snapshot_download is None:
        raise RuntimeError("huggingface_hub is required to download models")
    repo = _resolve_repo_id(name)
    TqdmCls = _make_tqdm_with_cb(progress_cb)
    return Path(snapshot_download(repo_id=repo, cache_dir=HF_CACHE_DIR, tqdm_class=TqdmCls))


def delete_model(name: str) -> None:
    if name == VAD_MODEL:
        for p in TORCH_HUB_DIR.glob("snakers4_silero-vad*"):
            shutil.rmtree(p, ignore_errors=True)
        return
    repo = _resolve_repo_id(name)
    shutil.rmtree(_cache_dir(repo), ignore_errors=True)
