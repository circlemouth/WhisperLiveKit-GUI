import argparse
import json
import os
from pathlib import Path

from wrapper.app import model_manager


def _apply_cache_env() -> None:
    # Align env to wrapper-specific caches so CLI actions affect same location
    hf_dir = os.environ.get("WRAPPER_HF_CACHE_DIR")
    torch_dir = os.environ.get("WRAPPER_TORCH_CACHE_DIR")
    base = os.environ.get("WRAPPER_CACHE_DIR")
    base_path: Path | None = None
    if base:
        try:
            base_path = Path(base)
        except Exception:
            base_path = None
    if base_path is not None:
        if not hf_dir:
            hf_dir = str(base_path / "hf-cache")
        if not torch_dir:
            torch_dir = str(base_path / "torch-hub")
    if not hf_dir or not torch_dir:
        try:
            from platformdirs import user_cache_path  # type: ignore

            default_base = Path(user_cache_path("WhisperLiveKit", "wrapper"))
        except Exception:
            default_base = None
        else:
            if not hf_dir:
                hf_dir = str(default_base / "hf-cache")
            if not torch_dir:
                torch_dir = str(default_base / "torch-hub")
    if hf_dir:
        try:
            Path(hf_dir).mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        os.environ.setdefault("HUGGINGFACE_HUB_CACHE", hf_dir)
        os.environ.setdefault("HF_HOME", hf_dir)
    if torch_dir:
        try:
            Path(torch_dir).mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        os.environ.setdefault("TORCH_HOME", torch_dir)


def main() -> None:
    _apply_cache_env()
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list")
    p_is = sub.add_parser("is_downloaded")
    p_is.add_argument("name")
    p_is.add_argument("--backend", choices=["faster-whisper", "simulstreaming"], default=None)

    p_dl = sub.add_parser("download")
    p_dl.add_argument("name")
    p_dl.add_argument("--backend", choices=["faster-whisper", "simulstreaming"], default=None)

    p_rm = sub.add_parser("delete")
    p_rm.add_argument("name")
    p_rm.add_argument("--backend", choices=["faster-whisper", "simulstreaming"], default=None)

    p_path = sub.add_parser("get_path")
    p_path.add_argument("name")
    p_path.add_argument("--backend", choices=["faster-whisper", "simulstreaming"], default=None)

    args = ap.parse_args()

    if args.cmd == "list":
        print(json.dumps(model_manager.list_downloaded_models()))
        return
    if args.cmd == "is_downloaded":
        print("1" if model_manager.is_model_downloaded(args.name, backend=args.backend) else "0")
        return
    if args.cmd == "get_path":
        print(str(model_manager.get_model_path(args.name, backend=args.backend)))
        return
    if args.cmd == "download":
        def _cb(fr: float) -> None:
            try:
                print(json.dumps({"progress": fr}), flush=True)
            except Exception:
                pass

        model_manager.download_model(args.name, backend=args.backend, progress_cb=_cb)
        return
    if args.cmd == "delete":
        model_manager.delete_model(args.name, backend=args.backend)
        return


if __name__ == "__main__":
    main()

