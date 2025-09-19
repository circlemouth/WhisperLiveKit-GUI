from __future__ import annotations

import contextlib
import hashlib
import inspect
import os
import shutil
from pathlib import Path
from typing import Callable, Optional
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from platformdirs import user_cache_path

try:
    from huggingface_hub import snapshot_download
    from huggingface_hub.utils import tqdm as hf_tqdm
except Exception:  # pragma: no cover - optional dependency
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


_CACHE_ROOT = _path_from_env("WRAPPER_CACHE_DIR")
if _CACHE_ROOT is None:
    _CACHE_ROOT = user_cache_path("WhisperLiveKit", "wrapper")
_CACHE_ROOT = _ensure_dir(_CACHE_ROOT)


_HF_CACHE = _path_from_env("WRAPPER_HF_CACHE_DIR", "HUGGINGFACE_HUB_CACHE", "HF_HOME")
if _HF_CACHE is None:
    _HF_CACHE = _CACHE_ROOT / "hf-cache"
HF_CACHE_DIR = _ensure_dir(_HF_CACHE)


_TORCH_CACHE = _path_from_env("WRAPPER_TORCH_CACHE_DIR", "TORCH_HOME")
if _TORCH_CACHE is None:
    _TORCH_CACHE = _CACHE_ROOT / "torch-hub"
TORCH_CACHE_DIR = _ensure_dir(_TORCH_CACHE)

os.environ.setdefault("WRAPPER_CACHE_DIR", str(_CACHE_ROOT))
os.environ.setdefault("WRAPPER_HF_CACHE_DIR", str(HF_CACHE_DIR))
os.environ.setdefault("WRAPPER_TORCH_CACHE_DIR", str(TORCH_CACHE_DIR))
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(HF_CACHE_DIR))
_WARMUP_CACHE = _path_from_env("WRAPPER_WARMUP_CACHE_DIR")
if _WARMUP_CACHE is None:
    _WARMUP_CACHE = _CACHE_ROOT / "warmups"
WARMUP_CACHE_DIR = _ensure_dir(_WARMUP_CACHE)

os.environ.setdefault("HF_HOME", str(HF_CACHE_DIR))
os.environ.setdefault("TORCH_HOME", str(TORCH_CACHE_DIR))
os.environ.setdefault("WRAPPER_WARMUP_CACHE_DIR", str(WARMUP_CACHE_DIR))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")

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


def _has_faster_whisper_weights(path: Path) -> bool:
    """Return True when the path contains faster-whisper CTranslate2 weights."""

    def _check_dir(candidate: Path) -> bool:
        try:
            candidate = candidate.expanduser()
        except Exception:
            pass
        if not candidate.is_dir():
            return False
        has_tokenizer = any(
            (candidate / name).is_file() for name in ("tokenizer.json", "tokenizer_config.json")
        )
        if not has_tokenizer:
            return False
        weights: list[Path] = []
        direct = candidate / "model.bin"
        if direct.is_file():
            weights.append(direct)
        for shard in candidate.glob("model.bin.*"):
            if shard.is_file() and not shard.name.endswith(".index.json"):
                weights.append(shard)
        if weights:
            return True
        index = candidate / "model.bin.index.json"
        if index.is_file():
            shards = [p for p in candidate.glob("model.bin.*") if p.is_file() and p != index]
            if shards:
                return True
        return False

    path = Path(path)
    try:
        path = path.expanduser()
    except Exception:
        pass
    if path.is_file():
        path = path.parent
    if _check_dir(path):
        return True
    for sub in ("ct2_model", "ctranslate2", "model"):
        if _check_dir(path / sub):
            return True
    return False


def _is_http_url(value: str) -> bool:
    try:
        parsed = urlparse.urlparse(value)
    except Exception:
        return False
    return parsed.scheme in {"http", "https"}


def _sanitize_filename(name: str) -> str:
    safe = []
    for ch in name:
        if ch.isalnum() or ch in {"-", "_", "."}:
            safe.append(ch)
        else:
            safe.append("-")
    candidate = "".join(safe).strip("-.")
    return candidate or "warmup.wav"


def _warmup_cache_path(url: str) -> Path:
    parsed = urlparse.urlparse(url)
    name = Path(urlparse.unquote(parsed.path or "")).name
    if not name:
        name = "warmup.wav"
    name = _sanitize_filename(name)
    if not Path(name).suffix:
        name = f"{name}.wav"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return WARMUP_CACHE_DIR / f"{digest}-{name}"


def needs_warmup_download(source: str) -> bool:
    if not source:
        return False
    if not _is_http_url(source):
        return False
    target = _warmup_cache_path(source)
    try:
        return not (target.is_file() and target.stat().st_size > 0)
    except Exception:
        return True


def _download_warmup(url: str, *, progress_cb: Callable[[float], None] | None = None) -> Path:
    target = _warmup_cache_path(url)
    if target.is_file() and target.stat().st_size > 0:
        if progress_cb:
            try:
                progress_cb(1.0)
            except Exception:
                pass
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")

    req = urlrequest.Request(url, headers={"User-Agent": "WhisperLiveKit-Wrapper"})
    success = False
    try:
        with urlrequest.urlopen(req) as resp:  # nosec B310 - trusted URL configured by user
            total = resp.getheader("Content-Length")
            try:
                total_len = int(total) if total else None
            except Exception:
                total_len = None
            received = 0
            with open(tmp, "wb") as fh:
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
                    received += len(chunk)
                    if progress_cb and total_len:
                        try:
                            progress_cb(min(1.0, received / total_len))
                        except Exception:
                            pass
            if progress_cb:
                try:
                    progress_cb(1.0)
                except Exception:
                    pass
        success = True
    except urlerror.HTTPError as exc:  # pragma: no cover - handled generically below
        raise RuntimeError(f"HTTP error {exc.code} when downloading warmup: {exc.reason}") from exc
    except urlerror.URLError as exc:  # pragma: no cover - handled generically below
        raise RuntimeError(f"Failed to download warmup file: {exc.reason}") from exc
    finally:
        if not success:
            with contextlib.suppress(Exception):
                tmp.unlink()

    if not tmp.exists() or tmp.stat().st_size == 0:
        with contextlib.suppress(Exception):
            tmp.unlink()
        raise RuntimeError("Warmup download produced an empty file")

    tmp.replace(target)
    return target


def ensure_warmup_file(source: str, *, progress_cb: Callable[[float], None] | None = None) -> Path:
    if not source:
        raise ValueError("Warmup source must be a non-empty string")
    if _is_http_url(source):
        return _download_warmup(source, progress_cb=progress_cb)
    path = Path(source)
    try:
        path = path.expanduser()
    except Exception:
        pass
    if path.is_file():
        return path
    if path.exists():
        raise FileNotFoundError(f"Warmup path is not a file: {path}")
    raise FileNotFoundError(f"Warmup file not found: {source}")


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
    if backend == "faster-whisper":
        if snapshot is not None and _has_faster_whisper_weights(snapshot):
            return True
        path = get_model_path(name, backend="faster-whisper")
        return _has_faster_whisper_weights(path)
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
