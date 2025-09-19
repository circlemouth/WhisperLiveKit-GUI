#!/usr/bin/env python3
"""Regression test for faster-whisper cache detection helpers.

This script creates temporary Hugging Face cache layouts that mimic the
structures produced by ``snapshot_download`` and verifies that
``model_manager.is_model_downloaded`` recognises valid CTranslate2 snapshots
while rejecting incomplete ones. It is intentionally lightweight so it can be
run in CI without network access.
"""

from __future__ import annotations

import http.server
import importlib
import io
import os
import shutil
import socketserver
import sys
import tempfile
import threading
import wave
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _reload_model_manager(tmp_dir: Path):
    """Reload ``model_manager`` with cache paths rooted at ``tmp_dir``."""

    for var in (
        "WRAPPER_CACHE_DIR",
        "WRAPPER_HF_CACHE_DIR",
        "WRAPPER_TORCH_CACHE_DIR",
        "HUGGINGFACE_HUB_CACHE",
        "HF_HOME",
        "TORCH_HOME",
    ):
        os.environ.pop(var, None)
    os.environ["WRAPPER_CACHE_DIR"] = str(tmp_dir)
    for key in list(sys.modules):
        if key.startswith("wrapper.app.model_manager"):
            sys.modules.pop(key)
    return importlib.import_module("wrapper.app.model_manager")


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        mm = _reload_model_manager(tmp_path)

        repo_dir = mm.HF_CACHE_DIR / "models--Systran--faster-whisper-tiny"

        _assert(
            not mm.is_model_downloaded("tiny", backend="faster-whisper"),
            "Fresh cache should report the model as missing.",
        )

        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / "model.bin").write_bytes(b"0")
        _assert(
            not mm.is_model_downloaded("tiny", backend="faster-whisper"),
            "Tokenizer metadata must exist alongside model.bin.",
        )
        (repo_dir / "tokenizer.json").write_text("{}", encoding="utf-8")
        _assert(
            mm.is_model_downloaded("tiny", backend="faster-whisper"),
            "Direct model.bin + tokenizer.json should be detected as downloaded.",
        )

        shutil.rmtree(repo_dir)
        repo_dir.mkdir(parents=True, exist_ok=True)
        snapshot = repo_dir / "snapshots" / "rev-123"
        snapshot.mkdir(parents=True, exist_ok=True)
        (snapshot / "tokenizer_config.json").write_text("{}", encoding="utf-8")
        _assert(
            not mm.is_model_downloaded("tiny", backend="faster-whisper"),
            "Weights are required before detection succeeds.",
        )
        (snapshot / "model.bin.0").write_bytes(b"0")
        (snapshot / "model.bin.1").write_bytes(b"0")
        (snapshot / "model.bin.index.json").write_text("{}", encoding="utf-8")
        _assert(
            mm.is_model_downloaded("tiny", backend="faster-whisper"),
            "Sharded model weights with index metadata should be detected.",
        )

        (snapshot / "model.bin.0").unlink()
        (snapshot / "model.bin.1").unlink()
        _assert(
            not mm.is_model_downloaded("tiny", backend="faster-whisper"),
            "Removing shards should mark the model as missing again.",
        )

        local_warmup = tmp_path / "local.wav"
        local_warmup.write_bytes(b"local")
        _assert(
            mm.ensure_warmup_file(str(local_warmup)) == local_warmup,
            "Local warmup paths should be returned unchanged.",
        )

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00\x00" * 10)
        sample_data = buf.getvalue()

        class _WarmupHandler(http.server.BaseHTTPRequestHandler):
            hits = 0

            def do_GET(self):  # type: ignore[override]
                type(self).hits += 1
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(sample_data)))
                self.end_headers()
                self.wfile.write(sample_data)

            def log_message(self, *_args, **_kwargs):  # pragma: no cover - silence test output
                return

        class _WarmupServer(socketserver.TCPServer):
            allow_reuse_address = True

        _WarmupHandler.hits = 0
        with _WarmupServer(("127.0.0.1", 0), _WarmupHandler) as httpd:
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                port = httpd.server_address[1]
                url = f"http://127.0.0.1:{port}/warmup.wav"
                _assert(
                    mm.needs_warmup_download(url),
                    "Remote warmup should require download when cache is empty.",
                )
                path = mm.ensure_warmup_file(url)
                _assert(path.exists(), "Downloaded warmup file should exist on disk.")
                _assert(
                    path.read_bytes() == sample_data,
                    "Warmup download should preserve the source bytes.",
                )
                _assert(
                    not mm.needs_warmup_download(url),
                    "Cached warmup should be detected as present.",
                )
                path_again = mm.ensure_warmup_file(url)
                _assert(path_again == path, "ensure_warmup_file should reuse the cached path.")
                _assert(
                    _WarmupHandler.hits == 1,
                    "Warmup HTTP handler should be hit exactly once.",
                )
            finally:
                httpd.shutdown()
                thread.join(timeout=2.0)

    print("faster-whisper and warmup cache tests passed.")


if __name__ == "__main__":
    main()
