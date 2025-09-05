import argparse
import json
import os
from pathlib import Path

from wrapper.app import model_manager


def _apply_cache_env() -> None:
    # Align env to wrapper-specific caches so CLI actions affect same location
    base = os.environ.get("WRAPPER_CACHE_DIR")
    if not base:
        try:
            from platformdirs import user_cache_path  # type: ignore

            base = str(user_cache_path("WhisperLiveKit", "wrapper"))
        except Exception:
            base = None
    if base:
        hf = str(Path(base) / "hf-cache")
        th = str(Path(base) / "torch-hub")
        os.environ.setdefault("HUGGINGFACE_HUB_CACHE", hf)
        os.environ.setdefault("HF_HOME", hf)
        os.environ.setdefault("TORCH_HOME", th)


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

