#!/usr/bin/env python3
"""Integration test covering wrapper GUI workflow end-to-end.

This script performs the following checks:
- Ensures Whisper transcription, VAD, and diarization-related models can be
  "downloaded" using wrapper.app.model_manager (with on-the-fly stubs that avoid
  external network access).
- Launches the wrapper backend through wrapper.app.backend_launcher using a
  lightweight stub backend that mimics the WhisperLiveKit basic server.
- Starts the FastAPI wrapper API (uvicorn) pointing to the stub backend.
- Sends synthetic audio to the OpenAI-compatible transcription endpoint and
  verifies typical response formats (json / verbose_json).

The goal is to mirror the behaviour triggered when the GUI's "Start API" button
is pressed, while remaining fully self-contained and deterministic for CI.
"""
from __future__ import annotations

import contextlib
import json
import math
import os
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, Iterable, NamedTuple, Optional

DEFAULT_TIMEOUT = 40.0
ROOT_DIR = Path(__file__).resolve().parents[2]

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from unittest import mock

import requests

from wrapper.app import model_manager
from wrapper.app import gui as gui_module


class ProcessError(RuntimeError):
    """Raised when a managed subprocess exits unexpectedly."""


def _debug(msg: str) -> None:
    print(f"[integration-test] {msg}")


class DownloadSummary(NamedTuple):
    paths: dict[str, Path]
    whisper_models: list[str]
    whisper_backends: list[str]


def _find_free_port(exclude: Iterable[int] | None = None) -> int:
    exclude_set = set(exclude or [])
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        if port not in exclude_set:
            return port


def _wait_for_port(host: str, port: int, *, timeout: float = DEFAULT_TIMEOUT) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError(f"Timed out waiting for {host}:{port} to accept connections")


def _generate_pcm16(duration_s: float = 0.3, *, sample_rate: int = 16000, freq: float = 440.0) -> bytes:
    total_samples = int(duration_s * sample_rate)
    frames = bytearray()
    for i in range(total_samples):
        # Simple sine wave scaled to 0.2 amplitude
        sample = int(32767 * 0.2 * math.sin(2.0 * math.pi * freq * (i / sample_rate)))
        frames.extend(struct.pack("<h", sample))
    return bytes(frames)


def _write_stub_backend(target_dir: Path) -> None:
    pkg_dir = target_dir / "whisperlivekit"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "__init__.py").write_text("""\n""", encoding="utf-8")
    stub_code = """
import argparse
import asyncio
import contextlib
import json
import signal
import sys
from typing import Tuple

from websockets.server import serve


async def _handler(websocket, path):
    if path != "/asr":
        await websocket.close()
        return
    buffer = bytearray()
    try:
        async for message in websocket:
            if isinstance(message, bytes):
                if len(message) == 0:
                    response = {
                        "type": "transcription",
                        "lines": [
                            {
                                "speaker": 1,
                                "text": "test transcript",
                                "beg": "00:00:00",
                                "end": "00:00:01",
                                "diff": 0.0,
                            }
                        ],
                    }
                    await websocket.send(json.dumps(response))
                    await websocket.send(json.dumps({"type": "ready_to_stop"}))
                    break
                buffer.extend(message)
            else:
                # Ignore control messages
                continue
    finally:
        await websocket.close()


async def _serve(host: str, port: int) -> None:
    async with serve(_handler, host, port):
        await asyncio.Future()


def main(argv: Tuple[str, ...] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default="8000")
    args, _unknown = parser.parse_known_args(argv)

    loop = asyncio.get_event_loop()

    stop_event = asyncio.Event()

    def _handle_signal(*_args):
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            signal.signal(sig, lambda *_: stop_event.set())

    async def _main():
        server_task = asyncio.create_task(_serve(args.host, int(args.port)))
        await stop_event.wait()
        server_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await server_task

    try:
        loop.run_until_complete(_main())
    finally:
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        with contextlib.suppress(Exception):
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))


if __name__ == "__main__":
    main(tuple(sys.argv[1:]))
"""
    (pkg_dir / "basic_server.py").write_text(stub_code, encoding="utf-8")


@contextlib.contextmanager
def _patch_model_manager(tmp_root: Path):
    hf_cache = tmp_root / "hf-cache"
    torch_cache = tmp_root / "torch-cache"
    hf_cache.mkdir(parents=True, exist_ok=True)
    torch_cache.mkdir(parents=True, exist_ok=True)

    def fake_snapshot_download(*, repo_id: str, cache_dir: str, tqdm_class: Optional[type] = None, **_kwargs) -> str:
        cache_path = Path(cache_dir)
        safe = repo_id.replace("/", "--")
        target = cache_path / f"models--{safe}" / "snapshots" / "stub"
        target.mkdir(parents=True, exist_ok=True)
        if "faster-whisper" in repo_id:
            (target / "model.bin").write_bytes(b"stub")
            (target / "tokenizer.json").write_text("{}", encoding="utf-8")
            (target / "tokenizer_config.json").write_text("{}", encoding="utf-8")
        else:
            (target / "pytorch_model.bin").write_bytes(b"stub")
        return str(target)

    def fake_vad_download(progress_cb: Optional[Callable[[float], None]] = None) -> Path:
        target = torch_cache / "snakers4_silero-vad-stub"
        target.mkdir(parents=True, exist_ok=True)
        if progress_cb:
            progress_cb(1.0)
        return target

    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(model_manager, "HF_CACHE_DIR", hf_cache))
        stack.enter_context(mock.patch.object(model_manager, "TORCH_CACHE_DIR", torch_cache))
        stack.enter_context(
            mock.patch(
                "wrapper.app.model_manager.snapshot_download",
                new=lambda *args, **kwargs: fake_snapshot_download(*args, **kwargs),
            )
        )
        stack.enter_context(
            mock.patch("wrapper.app.model_manager._download_vad_model", new=fake_vad_download)
        )
        yield hf_cache, torch_cache


def _download_required_models() -> DownloadSummary:
    """Download all model types exposed via the GUI and verify their cache entries."""

    whisper_models = list(gui_module.WHISPER_MODELS) or ["tiny"]
    whisper_backends = list(gui_module.WHISPER_BACKENDS)
    segmentation_models = list(gui_module.SEGMENTATION_MODELS)
    embedding_models = list(gui_module.EMBEDDING_MODELS)
    vad_models = list(gui_module.VAD_MODELS) or [model_manager.VAD_REPO]

    paths: dict[str, Path] = {}

    def _record_path(key: str, path: Path) -> None:
        paths[key] = path
        if not path.exists():
            raise FileNotFoundError(f"Model path missing for {key}: {path}")

    def _expected_repo(name: str, backend: Optional[str] = None) -> str:
        if "/" in name:
            return name
        if backend == "faster-whisper":
            return f"Systran/faster-whisper-{name}"
        return f"openai/whisper-{name}"

    for model_name in whisper_models:
        default_path = model_manager.download_model(model_name)
        _record_path(f"whisper:{model_name}", default_path)
        if not model_manager.is_model_downloaded(model_name):
            raise RuntimeError(f"Model download verification failed for whisper:{model_name}")

        for backend in whisper_backends:
            backend_path = model_manager.download_model(model_name, backend=backend)
            key = f"whisper:{model_name}:{backend}"
            _record_path(key, backend_path)
            if not model_manager.is_model_downloaded(model_name, backend=backend):
                raise RuntimeError(f"Model download verification failed for {key}")

    for repo_id in segmentation_models:
        seg_path = model_manager.download_model(repo_id)
        _record_path(f"seg:{repo_id}", seg_path)
        if not model_manager.is_model_downloaded(repo_id):
            raise RuntimeError(f"Model download verification failed for seg:{repo_id}")

    for repo_id in embedding_models:
        emb_path = model_manager.download_model(repo_id)
        _record_path(f"emb:{repo_id}", emb_path)
        if not model_manager.is_model_downloaded(repo_id):
            raise RuntimeError(f"Model download verification failed for emb:{repo_id}")

    for repo_id in vad_models:
        vad_path = model_manager.download_model(repo_id)
        _record_path(f"vad:{repo_id}", vad_path)
        if not model_manager.is_model_downloaded(repo_id):
            raise RuntimeError(f"Model download verification failed for vad:{repo_id}")

    listed = set(model_manager.list_downloaded_models())
    expected_entries: set[str] = set()

    for model_name in whisper_models:
        expected_entries.add(_expected_repo(model_name))
        for backend in whisper_backends:
            expected_entries.add(_expected_repo(model_name, backend=backend))

    expected_entries.update(segmentation_models)
    expected_entries.update(embedding_models)
    expected_entries.update(vad_models)

    missing_in_list = sorted(entry for entry in expected_entries if entry not in listed)
    if missing_in_list:
        raise RuntimeError(
            "Model download verification failed: missing entries in list_downloaded_models: "
            + ", ".join(missing_in_list)
        )

    return DownloadSummary(paths=paths, whisper_models=whisper_models, whisper_backends=whisper_backends)


def _launch_process(cmd: list[str], *, env: dict[str, str], name: str) -> subprocess.Popen:
    _debug(f"Launching {name}: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(0.5)
    if proc.poll() is not None:
        stdout, stderr = proc.communicate()
        raise ProcessError(f"{name} exited immediately with code {proc.returncode}\nSTDOUT:{stdout}\nSTDERR:{stderr}")
    return proc


def _terminate_process(proc: subprocess.Popen, name: str, *, timeout: float = 5.0) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=timeout)


def _collect_output(proc: subprocess.Popen) -> tuple[str, str]:
    try:
        stdout, stderr = proc.communicate(timeout=5.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
    return stdout or "", stderr or ""


def run_integration_test() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        stub_dir = tmp_path / "stubs"
        _write_stub_backend(stub_dir)

        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        env["PYTHONPATH"] = f"{stub_dir}{os.pathsep}{env.get('PYTHONPATH', '')}" if env.get("PYTHONPATH") else str(stub_dir)

        backend_port = _find_free_port()
        api_port = _find_free_port(exclude=[backend_port])
        env["WRAPPER_BACKEND_HOST"] = "127.0.0.1"
        env["WRAPPER_BACKEND_PORT"] = str(backend_port)
        env["WRAPPER_API_HOST"] = "127.0.0.1"
        env["WRAPPER_API_PORT"] = str(api_port)
        env["WRAPPER_BACKEND_SSL"] = "0"
        env["WRAPPER_REQUIRE_API_KEY"] = "0"

        with _patch_model_manager(tmp_path) as (hf_cache, torch_cache):
            env["HUGGINGFACE_HUB_CACHE"] = str(hf_cache)
            env["TORCH_HOME"] = str(torch_cache)

            download_summary = _download_required_models()
            model_paths = download_summary.paths
            whisper_models = download_summary.whisper_models
            whisper_backends = download_summary.whisper_backends

            if not whisper_models:
                raise RuntimeError("No Whisper models available from GUI catalog")

            primary_model = whisper_models[0]
            if not whisper_backends:
                raise RuntimeError("No Whisper backends available from GUI catalog")
            primary_backend = whisper_backends[0]

            selected_key = f"whisper:{primary_model}:{primary_backend}" if primary_backend else f"whisper:{primary_model}"
            if selected_key not in model_paths:
                raise RuntimeError(f"Missing downloaded model entry for {selected_key}")

            backend_cmd = [
                sys.executable,
                "-u",
                "-m",
                "wrapper.app.backend_launcher",
                "--host",
                env["WRAPPER_BACKEND_HOST"],
                "--port",
                env["WRAPPER_BACKEND_PORT"],
                "--model_cache_dir",
                str(hf_cache),
            ]

            model_dir_path: Path | None = None
            if primary_backend == "simulstreaming":
                backend_cmd += ["--model", primary_model]
                model_dir_path = model_manager.get_model_path(primary_model, backend="simulstreaming")
                backend_cmd += ["--model_dir", str(model_dir_path)]
            elif primary_backend == "faster-whisper":
                backend_cmd += ["--model", primary_model]
                if model_manager.is_model_downloaded(primary_model, backend="faster-whisper"):
                    model_dir_path = model_manager.get_model_path(primary_model, backend="faster-whisper")
                    backend_cmd += ["--model_dir", str(model_dir_path)]
            else:
                model_dir_path = model_manager.get_model_path(primary_model)
                backend_cmd += ["--model_dir", str(model_dir_path)]

            if model_dir_path and not model_dir_path.exists():
                raise FileNotFoundError(f"Backend model path missing: {model_dir_path}")

            backend_cmd += ["--backend", primary_backend]

            backend_cmd += [
                "--min-chunk-size",
                "0.5",
                "--language",
                "auto",
                "--task",
                "transcribe",
                "--no-vac",
                "--buffer_trimming",
                "segment",
                "--buffer_trimming_sec",
                "15",
                "--log-level",
                "DEBUG",
                "--frame-threshold",
                "25",
            ]

            backend_proc = _launch_process(backend_cmd, env=env, name="backend")
            try:
                _wait_for_port(env["WRAPPER_BACKEND_HOST"], int(env["WRAPPER_BACKEND_PORT"]))

                api_cmd = [
                    sys.executable,
                    "-u",
                    "-m",
                    "uvicorn",
                    "wrapper.api.server:app",
                    "--host",
                    env["WRAPPER_API_HOST"],
                    "--port",
                    env["WRAPPER_API_PORT"],
                ]
                api_proc = _launch_process(api_cmd, env=env, name="api")
                try:
                    _wait_for_port(env["WRAPPER_API_HOST"], int(env["WRAPPER_API_PORT"]))

                    url = f"http://{env['WRAPPER_API_HOST']}:{env['WRAPPER_API_PORT']}/v1/audio/transcriptions"
                    pcm = _generate_pcm16()
                    files = {"file": ("test.raw", pcm, "application/octet-stream")}
                    data = {"model": "whisper", "response_format": "json"}
                    _debug("Sending transcription request (json)")
                    resp = requests.post(url, files=files, data=data, timeout=10)
                    resp.raise_for_status()
                    payload = resp.json()
                    if payload.get("text") != "test transcript":
                        raise AssertionError(f"Unexpected transcription text: {payload}")

                    data_verbose = {"model": "whisper", "response_format": "verbose_json"}
                    _debug("Sending transcription request (verbose_json)")
                    resp_verbose = requests.post(url, files=files, data=data_verbose, timeout=10)
                    resp_verbose.raise_for_status()
                    verbose_json = resp_verbose.json()
                    segments = verbose_json.get("segments") or []
                    if not segments:
                        raise AssertionError("Expected segments in verbose_json response")
                    if segments[0].get("text") != "test transcript":
                        raise AssertionError(f"Unexpected segment payload: {segments}")

                    _debug("Integration test completed successfully")
                finally:
                    _terminate_process(api_proc, "api")
                    api_stdout, api_stderr = _collect_output(api_proc)
                    _debug(f"API stdout:\n{api_stdout}")
                    if api_stderr:
                        _debug(f"API stderr:\n{api_stderr}")
            finally:
                _terminate_process(backend_proc, "backend")
                backend_stdout, backend_stderr = _collect_output(backend_proc)
                _debug(f"Backend stdout:\n{backend_stdout}")
                if backend_stderr:
                    _debug(f"Backend stderr:\n{backend_stderr}")


if __name__ == "__main__":
    run_integration_test()
