from __future__ import annotations

import inspect
import os
import shutil
import sys
from pathlib import Path
from typing import Callable, Optional

from platformdirs import user_cache_path

snapshot_download = None
hf_tqdm = None

# Determine cache roots taking existing environment into account. This keeps
# MSIX パッケージなど書き込み制限のある環境でも、ダウンロードとロード元が同じ
# ディレクトリを参照するよう統一する。


def _path_from_env(*names: str) -> Path | None:
    for name in names:
        raw = os.environ.get(name, "").strip()
        if not raw:
            continue
        try:
            return Path(raw).expanduser()
        except Exception:
            continue
    return None


def _ensure_dir(path: Path) -> Path:
    path = Path(path)
    try:
        path = path.expanduser()
    except Exception:
        pass
    path.mkdir(parents=True, exist_ok=True)
    try:
        return path.resolve()
    except Exception:
        return path


_MAX_CACHE_BASE_LEN = 120
_FALLBACK_CACHE_ROOT = Path.home() / ".cache" / "WhisperLiveKitWrapper"


def _shorten_if_needed(path: Path, *, fallback: Path) -> tuple[Path, bool]:
    """Return a cache path that stays within Windows MAX_PATH limits.

    Returns a tuple of ``(selected_path, fallback_used)`` so callers can
    migrate or log when a long Windows Store path was detected.
    """
    try:
        candidate = path.expanduser()
    except Exception:
        candidate = path
    candidate_str = str(candidate)
    candidate_norm = candidate_str.replace("\\", "/").lower()
    if "packages/pythonsoftwarefoundation.python." in candidate_norm:
        return fallback, True
    if len(candidate_str) > _MAX_CACHE_BASE_LEN:
        return fallback, True
    return candidate, False


def _maybe_migrate_cache(src: Path, dest: Path) -> None:
    """Move existing cache contents from ``src`` into ``dest`` if possible."""

    try:
        src = src.expanduser()
    except Exception:
        pass
    try:
        dest = dest.expanduser()
    except Exception:
        pass

    if dest == src:
        return

    if not src.exists():
        return

    # Windows Store 版 Python のキャッシュは移行後に不要となるため、内容のみを
    # 新ディレクトリへ移動する。エラーは致命的ではないため握りつぶす。
    for entry in src.iterdir():
        target = dest / entry.name
        if target.exists():
            continue
        try:
            shutil.move(str(entry), target)
        except Exception as exc:
            print(
                f"[wrapper.model_manager] cache migrate warning: {entry} -> {target}: {exc}",
                file=sys.stderr,
            )


_CACHE_ROOT_ENV = _path_from_env("WRAPPER_CACHE_DIR")
if _CACHE_ROOT_ENV is None:
    candidate_cache = user_cache_path("WhisperLiveKit", "wrapper")
else:
    candidate_cache = _CACHE_ROOT_ENV

_CACHE_ROOT, _cache_used_fallback = _shorten_if_needed(
    candidate_cache, fallback=_FALLBACK_CACHE_ROOT
)
_CACHE_ROOT = _ensure_dir(_CACHE_ROOT)
if _cache_used_fallback and candidate_cache:
    _maybe_migrate_cache(Path(candidate_cache), _CACHE_ROOT)
    os.environ["WRAPPER_CACHE_MIGRATED_FROM"] = str(candidate_cache)


_HF_CACHE_ENV = _path_from_env("WRAPPER_HF_CACHE_DIR", "HUGGINGFACE_HUB_CACHE", "HF_HOME")
if _HF_CACHE_ENV is None:
    candidate_hf = _CACHE_ROOT / "hf-cache"
else:
    candidate_hf = _HF_CACHE_ENV

HF_CACHE_DIR, _hf_used_fallback = _shorten_if_needed(
    candidate_hf, fallback=_CACHE_ROOT / "hf-cache"
)
HF_CACHE_DIR = _ensure_dir(HF_CACHE_DIR)
if _hf_used_fallback and candidate_hf:
    _maybe_migrate_cache(Path(candidate_hf), HF_CACHE_DIR)


_TORCH_CACHE_ENV = _path_from_env("WRAPPER_TORCH_CACHE_DIR", "TORCH_HOME")
if _TORCH_CACHE_ENV is None:
    candidate_torch = _CACHE_ROOT / "torch-hub"
else:
    candidate_torch = _TORCH_CACHE_ENV

TORCH_CACHE_DIR, _torch_used_fallback = _shorten_if_needed(
    candidate_torch, fallback=_CACHE_ROOT / "torch-hub"
)
TORCH_CACHE_DIR = _ensure_dir(TORCH_CACHE_DIR)
if _torch_used_fallback and candidate_torch:
    _maybe_migrate_cache(Path(candidate_torch), TORCH_CACHE_DIR)

os.environ["WRAPPER_CACHE_DIR"] = str(_CACHE_ROOT)
os.environ["WRAPPER_HF_CACHE_DIR"] = str(HF_CACHE_DIR)
os.environ["WRAPPER_TORCH_CACHE_DIR"] = str(TORCH_CACHE_DIR)
os.environ["HUGGINGFACE_HUB_CACHE"] = str(HF_CACHE_DIR)
os.environ["HF_HOME"] = str(HF_CACHE_DIR)
os.environ["TORCH_HOME"] = str(TORCH_CACHE_DIR)
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
print(f"[wrapper.model_manager] cache root -> {os.environ['WRAPPER_CACHE_DIR']}", file=sys.stderr)
print(f"[wrapper.model_manager] HF cache -> {os.environ['WRAPPER_HF_CACHE_DIR']}", file=sys.stderr)

try:
    from huggingface_hub import snapshot_download  # type: ignore
    from huggingface_hub.utils import tqdm as hf_tqdm  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    snapshot_download = None
    hf_tqdm = None

_SNAPSHOT_KWARGS: dict[str, object] = {}
if snapshot_download is not None:
    try:
        sig = inspect.signature(snapshot_download)
        if "local_dir_use_symlinks" in sig.parameters:
            _SNAPSHOT_KWARGS["local_dir_use_symlinks"] = False
    except Exception:
        _SNAPSHOT_KWARGS = {}

VAD_REPO = "snakers4/silero-vad"
VAD_MODEL = "silero_vad"


def _pt_file(name: str) -> Path:
    """Return path to simulstreaming-style .pt file for a Whisper model."""
    base = name.split("/")[-1]
    if base.startswith("whisper-"):
        base = base[len("whisper-") :]
    return HF_CACHE_DIR / f"{base}.pt"


def _resolve_repo_id(name: str, *, backend: Optional[str] = None) -> str:
    """Return full Hugging Face repo id for a given model name.

    - default/OpenAI whisper: openai/whisper-<name>
    - faster-whisper backend: prefer Systran/faster-whisper-<name>
      (falls back to the provided name if it already contains '/').
    """
    if "/" in name:
        return name
    if backend == "faster-whisper":
        # CTranslate2 weights commonly distributed under Systran
        return f"Systran/faster-whisper-{name}"
    return f"openai/whisper-{name}"


def _cache_dir(repo_id: str) -> Path:
    safe = repo_id.replace("/", "--")
    return HF_CACHE_DIR / f"models--{safe}"


def _latest_snapshot_path(repo_id: str) -> Path | None:
    """Return the newest snapshot directory for a given Hugging Face repo.

    Returns ``None`` when no snapshot has been materialised yet.
    """
    base = _cache_dir(repo_id)
    snapshots = base / "snapshots"
    if not snapshots.exists():
        return None
    try:
        dirs = [p for p in snapshots.iterdir() if p.is_dir()]
    except Exception:
        return None
    if not dirs:
        return None
    return max(dirs, key=lambda p: p.stat().st_mtime)


def _vad_cache_dirs() -> list[Path]:
    return list(TORCH_CACHE_DIR.glob("snakers4_silero-vad*"))


def _is_vad_downloaded() -> bool:
    return any(p.is_dir() for p in _vad_cache_dirs())


def _download_vad_model(progress_cb: Callable[[float], None] | None = None) -> Path:
    import torch  # type: ignore

    torch.hub.set_dir(str(TORCH_CACHE_DIR))
    torch.hub.load(repo_or_dir=VAD_REPO, model=VAD_MODEL, trust_repo=True)
    if progress_cb:
        progress_cb(1.0)
    dirs = _vad_cache_dirs()
    return dirs[0] if dirs else TORCH_CACHE_DIR


def _delete_vad_model() -> None:
    for p in _vad_cache_dirs():
        shutil.rmtree(p, ignore_errors=True)


def get_model_path(name: str, *, backend: Optional[str] = None) -> Path:
    """Return local snapshot path for the model (latest if multiple)."""
    if name == VAD_REPO:
        dirs = _vad_cache_dirs()
        return dirs[0] if dirs else TORCH_CACHE_DIR
    if backend == "simulstreaming":
        pt = _pt_file(name)
        if pt.exists():
            return pt
        # fall back to expected location even if missing
        return pt
    repo = _resolve_repo_id(name, backend=backend)
    snapshot = _latest_snapshot_path(repo)
    if snapshot is not None:
        return snapshot
    base = _cache_dir(repo)
    marker = base / "latest"
    if marker.is_file():
        try:
            saved = Path(marker.read_text().strip())
            if saved.exists():
                return saved
        except Exception:
            pass
    # Fallback: legacy cache or manually placed models
    # Search typical weight filenames at root or one level deep.
    for cand in ("model.bin", "pytorch_model.bin"):
        p = base / cand
        if p.exists():
            return base
    if base.exists():
        for sub in base.iterdir():
            if sub.is_dir():
                for cand in ("model.bin", "pytorch_model.bin"):
                    p = sub / cand
                    if p.exists():
                        return sub
    return base


def is_model_downloaded(name: str, *, backend: Optional[str] = None) -> bool:
    if name == VAD_REPO:
        return _is_vad_downloaded()
    if backend == "simulstreaming":
        return _pt_file(name).is_file()
    repo = _resolve_repo_id(name, backend=backend)
    snapshot = _latest_snapshot_path(repo)
    if snapshot is not None:
        return True
    # Only Whisper default backend falls back to .pt compatibility files.
    if backend in (None, "whisper_timestamped"):
        return _pt_file(name).is_file()
    return False


def list_downloaded_models() -> list[str]:
    models: list[str] = []
    for p in HF_CACHE_DIR.glob("models--*"):
        if (p / "snapshots").exists():
            repo_id = p.name[len("models--") :].replace("--", "/")
            models.append(repo_id)
    # Include simulstreaming-style .pt files (treated as openai/whisper-<name>)
    for pt in HF_CACHE_DIR.glob("*.pt"):
        name = pt.stem
        models.append(f"openai/whisper-{name}")
    if _is_vad_downloaded():
        models.append(VAD_REPO)
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


def download_model(
    name: str,
    *,
    backend: Optional[str] = None,
    progress_cb: Callable[[float], None] | None = None,
) -> Path:
    """Download model into cache directory."""
    if name == VAD_REPO:
        return _download_vad_model(progress_cb)
    if snapshot_download is None:
        raise RuntimeError("huggingface_hub is required to download models")
    repo = _resolve_repo_id(name, backend=backend)
    TqdmCls = _make_tqdm_with_cb(progress_cb)
    kwargs = {"repo_id": repo, "cache_dir": HF_CACHE_DIR, "tqdm_class": TqdmCls}
    if _SNAPSHOT_KWARGS:
        kwargs.update(_SNAPSHOT_KWARGS)
    path = Path(snapshot_download(**kwargs))
    try:
        (_cache_dir(repo) / "latest").write_text(str(path), encoding="utf-8")
    except Exception:
        pass
    if backend == "simulstreaming":
        # SimulStreaming expects a `<name>.pt` file in cache root
        src_candidates = [path / "model.bin", path / "pytorch_model.bin", path / f"{name}.pt"]
        for src in src_candidates:
            if src.exists():
                shutil.copy2(src, _pt_file(name))
                break
    return path


def delete_model(name: str, *, backend: Optional[str] = None) -> None:
    if name == VAD_REPO:
        _delete_vad_model()
        return
    repo = _resolve_repo_id(name, backend=backend)
    shutil.rmtree(_cache_dir(repo), ignore_errors=True)
    # Remove potential .pt file for simulstreaming/openai models
    if backend in (None, "simulstreaming"):
        try:
            _pt_file(name).unlink()
        except Exception:
            pass
