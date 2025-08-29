from __future__ import annotations

import shutil
from functools import partial
from pathlib import Path
from typing import Callable

from platformdirs import user_cache_path

try:
    from huggingface_hub import snapshot_download
    from huggingface_hub.utils import tqdm as hf_tqdm
except Exception:  # pragma: no cover - optional dependency
    snapshot_download = None
    hf_tqdm = None

# Root directory for Hugging Face cache used by the wrapper
HF_CACHE_DIR = user_cache_path("WhisperLiveKit", "wrapper") / "hf-cache"
HF_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _resolve_repo_id(name: str) -> str:
    """Return full repo id for a given model name."""
    return name if "/" in name else f"openai/whisper-{name}"


def _cache_dir(repo_id: str) -> Path:
    safe = repo_id.replace("/", "--")
    return HF_CACHE_DIR / f"models--{safe}"


def get_model_path(name: str) -> Path:
    """Return local snapshot path for the model (latest if multiple)."""
    repo = _resolve_repo_id(name)
    base = _cache_dir(repo)
    snapshots = base / "snapshots"
    if snapshots.exists():
        dirs = [p for p in snapshots.iterdir() if p.is_dir()]
        if dirs:
            return max(dirs, key=lambda p: p.stat().st_mtime)
    return base


def is_model_downloaded(name: str) -> bool:
    repo = _resolve_repo_id(name)
    snapshots = _cache_dir(repo) / "snapshots"
    return snapshots.exists() and any(p.is_dir() for p in snapshots.iterdir())


def list_downloaded_models() -> list[str]:
    models: list[str] = []
    for p in HF_CACHE_DIR.glob("models--*"):
        if (p / "snapshots").exists():
            repo_id = p.name[len("models--") :].replace("--", "/")
            models.append(repo_id)
    return models


class _TqdmWithCallback(hf_tqdm):
    def __init__(self, *args, progress_cb: Callable[[float], None] | None = None, **kwargs):
        self._progress_cb = progress_cb
        super().__init__(*args, **kwargs)

    def update(self, n=1):  # pragma: no cover - visual feedback only
        super().update(n)
        if self.total and self._progress_cb:
            self._progress_cb(self.n / self.total)


def download_model(name: str, progress_cb: Callable[[float], None] | None = None) -> Path:
    """Download model from Hugging Face into cache directory."""
    if snapshot_download is None:
        raise RuntimeError("huggingface_hub is required to download models")
    repo = _resolve_repo_id(name)
    TqdmCls = partial(_TqdmWithCallback, progress_cb=progress_cb)
    return Path(snapshot_download(repo_id=repo, cache_dir=HF_CACHE_DIR, tqdm_class=TqdmCls))


def delete_model(name: str) -> None:
    repo = _resolve_repo_id(name)
    shutil.rmtree(_cache_dir(repo), ignore_errors=True)
