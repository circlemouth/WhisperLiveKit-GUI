import json
import os
import subprocess
import io
import wave
from typing import List, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.exceptions import RequestValidationError

import websockets

BACKEND_HOST = os.getenv("WRAPPER_BACKEND_HOST", "localhost")
BACKEND_PORT = os.getenv("WRAPPER_BACKEND_PORT", "8000")
# Optional override for connect host (can differ from bind host)
BACKEND_CONNECT_HOST = os.getenv("WRAPPER_BACKEND_CONNECT_HOST")
if not BACKEND_CONNECT_HOST:
    # If backend bound to 0.0.0.0/::, prefer loopback for local connect
    if BACKEND_HOST in ("0.0.0.0", "::", ""):
        BACKEND_CONNECT_HOST = "127.0.0.1"
    else:
        BACKEND_CONNECT_HOST = BACKEND_HOST
# Choose ws/wss based on backend SSL flag from GUI
BACKEND_SSL = os.getenv("WRAPPER_BACKEND_SSL", "0") == "1"
BACKEND_WS_SCHEME = "wss" if BACKEND_SSL else "ws"
BACKEND_WS_URL = f"{BACKEND_WS_SCHEME}://{BACKEND_CONNECT_HOST}:{BACKEND_PORT}/asr"

# API key settings (provided by GUI via environment variables)
REQUIRE_API_KEY = os.getenv("WRAPPER_REQUIRE_API_KEY", "0") == "1"
API_KEY = os.getenv("WRAPPER_API_KEY", "")


def _extract_api_key_from_request(request: Request) -> str | None:
    # Prefer X-API-Key header; fallback to Authorization: Bearer <key>
    key = request.headers.get("x-api-key")
    if key:
        return key
    auth = request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(None, 1)[1].strip()
    return None


def require_api_key_dep(request: Request) -> None:
    if not REQUIRE_API_KEY:
        return
    if not API_KEY:
        # Misconfiguration: key required but not set
        raise HTTPException(status_code=500, detail="api_key_not_configured")
    provided = _extract_api_key_from_request(request)
    if provided != API_KEY:
        raise HTTPException(status_code=401, detail="unauthorized")


app = FastAPI(title="WhisperLiveKit Wrapper API")


@app.middleware("http")
async def _api_key_middleware(request: Request, call_next):
    try:
        require_api_key_dep(request)
    except HTTPException as exc:
        return await _http_exception_handler(request, exc)
    return await call_next(request)


# -----------------------------
# OpenAI-style error formatting
# -----------------------------
def _openai_error_response(message: str, status_code: int) -> JSONResponse:
    if status_code == 401:
        err_type = "authentication_error"
    elif status_code == 400:
        err_type = "invalid_request_error"
    else:
        err_type = "server_error"
    return JSONResponse(status_code=status_code, content={
        "error": {
            "message": message,
            "type": err_type,
            "code": None,
        }
    })


@app.exception_handler(HTTPException)
async def _http_exception_handler(_request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    # Map known details to user-friendly messages
    if detail == "unauthorized":
        return _openai_error_response("Invalid authentication credentials.", 401)
    if detail == "api_key_not_configured":
        return _openai_error_response("API key required but not configured on server.", 500)
    if detail == "ffmpeg_not_found":
        return _openai_error_response("FFmpeg is not installed or not in PATH.", 500)
    if detail == "ffmpeg_failed":
        return _openai_error_response("FFmpeg failed to decode the provided audio.", 400)
    return _openai_error_response(detail or "Unhandled error.", exc.status_code)


@app.exception_handler(Exception)
async def _generic_exception_handler(_request: Request, exc: Exception):
    return _openai_error_response(f"Internal server error: {exc}", 500)


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(_request: Request, exc: RequestValidationError):
    return _openai_error_response(f"Invalid request: {exc}", 400)


def _convert_to_pcm16(file_bytes: bytes) -> bytes:
    """Convert arbitrary audio bytes to 16kHz mono PCM using ffmpeg."""
    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-i",
                "pipe:0",
                "-f",
                "s16le",
                "-ac",
                "1",
                "-ar",
                "16000",
                "pipe:1",
            ],
            input=file_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail="ffmpeg_not_found") from e
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=400, detail="ffmpeg_failed") from e
    return proc.stdout


def _extract_pcm16(upload: UploadFile, file_bytes: bytes) -> bytes:
    """Deprecated in route: prefer container bytes for FFmpeg stdin.

    Kept for potential future use. Returns PCM16/16kHz/mono.
    """
    name = (upload.filename or "").lower()
    if name.endswith(".raw"):
        return file_bytes
    if name.endswith(".wav"):
        try:
            with wave.open(io.BytesIO(file_bytes)) as wf:
                if (
                    wf.getframerate() == 16000
                    and wf.getnchannels() == 1
                    and wf.getsampwidth() == 2
                ):
                    return wf.readframes(wf.getnframes())
        except wave.Error:
            pass
    return _convert_to_pcm16(file_bytes)


def _wrap_pcm16_as_wav(pcm_bytes: bytes, sample_rate: int = 16000, channels: int = 1) -> bytes:
    """Wrap raw PCM16 (little-endian) into a WAV container in-memory."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


async def _stream_to_backend(pcm_bytes: bytes):
    """Stream PCM audio to the backend WebSocket and collect results.

    Returns a tuple: (all_texts: List[str], lines: List[dict]) where lines
    are dicts with keys like: speaker, text, beg, end, diff.
    """
    # Use latest snapshot approach to avoid duplications from streaming updates
    latest_lines: List[dict] = []
    async with websockets.connect(BACKEND_WS_URL) as ws:
        chunk = 3200
        for i in range(0, len(pcm_bytes), chunk):
            await ws.send(pcm_bytes[i : i + chunk])
        # Signal end of audio
        await ws.send(b"")
        while True:
            message = await ws.recv()
            data = json.loads(message)
            if data.get("type") == "ready_to_stop":
                break
            lines = data.get("lines", []) or []
            # Build a clean snapshot, skipping silence/loading and empty texts
            snapshot: List[dict] = []
            for item in lines:
                if not isinstance(item, dict):
                    continue
                text_val = (item.get("text") or "").strip()
                if not text_val:
                    continue
                spk = item.get("speaker")
                if isinstance(spk, int) and spk in (-2, 0):
                    continue
                snapshot.append({
                    "speaker": spk,
                    "text": text_val,
                    "beg": item.get("beg"),
                    "end": item.get("end"),
                    "diff": item.get("diff"),
                })
            if snapshot:
                latest_lines = snapshot
        await ws.close()
    # Aggregate final text from the latest snapshot only
    texts: List[str] = [(it.get("text") or "").strip() for it in latest_lines if it.get("text")]
    return texts, latest_lines


def _parse_hhmmss_to_seconds(value: str) -> float:
    """Parse 'HH:MM:SS' string to seconds (float). Milliseconds are not provided upstream."""
    try:
        parts = value.split(":")
        if len(parts) != 3:
            return 0.0
        h, m, s = map(int, parts)
        return float(h * 3600 + m * 60 + s)
    except Exception:
        return 0.0


def _speaker_label(speaker: Optional[int]) -> str:
    try:
        if speaker is None:
            return ""
        if int(speaker) <= 0:
            return ""
        return f"Speaker {int(speaker)}: "
    except Exception:
        return ""


def _format_srt(lines: List[dict]) -> str:
    out_lines: List[str] = []
    idx = 1
    for item in lines:
        text = (item.get("text") or "").strip()
        if not text:
            continue
        spk = item.get("speaker")
        if isinstance(spk, int) and spk in (-2, 0):
            continue
        beg = _parse_hhmmss_to_seconds(item.get("beg", "00:00:00"))
        end = _parse_hhmmss_to_seconds(item.get("end", "00:00:00"))
        def to_ts(t: float) -> str:
            h = int(t // 3600)
            m = int((t % 3600) // 60)
            s = int(t % 60)
            return f"{h:02d}:{m:02d}:{s:02d},000"
        out_lines.append(str(idx))
        out_lines.append(f"{to_ts(beg)} --> {to_ts(end)}")
        lbl = _speaker_label(spk)
        out_lines.append(f"{lbl}{text}" if lbl else text)
        out_lines.append("")
        idx += 1
    return "\n".join(out_lines).rstrip() + ("\n" if out_lines else "")


def _format_vtt(lines: List[dict]) -> str:
    out_lines: List[str] = ["WEBVTT", ""]
    for item in lines:
        text = (item.get("text") or "").strip()
        if not text:
            continue
        spk = item.get("speaker")
        if isinstance(spk, int) and spk in (-2, 0):
            continue
        beg = _parse_hhmmss_to_seconds(item.get("beg", "00:00:00"))
        end = _parse_hhmmss_to_seconds(item.get("end", "00:00:00"))
        def to_ts(t: float) -> str:
            h = int(t // 3600)
            m = int((t % 3600) // 60)
            s = int(t % 60)
            return f"{h:02d}:{m:02d}:{s:02d}.000"
        out_lines.append(f"{to_ts(beg)} --> {to_ts(end)}")
        lbl = _speaker_label(spk)
        out_lines.append(f"{lbl}{text}" if lbl else text)
        out_lines.append("")
    return "\n".join(out_lines).rstrip() + ("\n" if len(out_lines) > 2 else "")


@app.post("/v1/audio/transcriptions")
async def transcribe(
    file: UploadFile = File(...),
    # OpenAI Whisper API requires 'model', but we ignore its value and always use GUI-configured backend
    model: str = Form(...),
    response_format: str = Form("json"),
    prompt: str | None = Form(None),
    temperature: float = Form(0.0),
    language: str | None = Form(None),
    user: str | None = Form(None),
    timestamp_granularities_brackets: List[str] | None = Form(None, alias="timestamp_granularities[]"),
    timestamp_granularities: List[str] | None = Form(None),
):
    """OpenAI Whisper API compatible transcription endpoint.

    - Accepts multipart/form-data with 'file' and 'model' (required by spec).
    - Uses GUI-configured model/settings via backend; ignores provided 'model' value.
    - Supports response_format: json (default), text, srt, vtt, verbose_json.
    """
    # Validate response_format
    rf = (response_format or "json").lower()
    allowed_rf = {"json", "text", "srt", "vtt", "verbose_json"}
    if rf not in allowed_rf:
        return _openai_error_response("Invalid response_format.", 400)

    # Ensure file content present
    raw = await file.read()
    if not raw:
        return _openai_error_response("No audio file provided or file is empty.", 400)

    # Decide what to send to backend FFmpeg stdin (expects a recognizable container)
    # - For .raw: wrap into WAV 16kHz/mono
    # - Else: send original bytes (wav/mp3/m4a/webm...)
    to_send = raw
    name = (file.filename or "").lower()
    if name.endswith(".raw"):
        # Assume already PCM16/16kHz/mono; if not, backend FFmpeg will still decode but timing may be off
        to_send = _wrap_pcm16_as_wav(raw, 16000, 1)

    # Stream to backend and collect results
    try:
        texts, lines = await _stream_to_backend(to_send)
    except Exception as e:
        return _openai_error_response(f"Backend processing failed: {e}", 500)

    final_text = " ".join(t.strip() for t in texts if t).strip()

    # Build response
    if rf == "json":
        return JSONResponse({"text": final_text})
    if rf == "text":
        return PlainTextResponse(content=final_text)
    if rf == "srt":
        return PlainTextResponse(content=_format_srt(lines), media_type="text/srt")
    if rf == "vtt":
        return PlainTextResponse(content=_format_vtt(lines), media_type="text/vtt")
    if rf == "verbose_json":
        segments = []
        for item in lines:
            text = (item.get("text") or "").strip()
            if not text:
                continue
            start = _parse_hhmmss_to_seconds(item.get("beg", "00:00:00"))
            end = _parse_hhmmss_to_seconds(item.get("end", "00:00:00"))
            spk = item.get("speaker")
            segments.append({
                "start": start,
                "end": end,
                "text": text,
                "speaker": spk if isinstance(spk, int) else None,
                "speaker_label": (_speaker_label(spk).rstrip() if _speaker_label(spk) else None),
            })
        return JSONResponse({"text": final_text, "segments": segments})

    # Fallback (should not reach)
    return JSONResponse({"text": final_text})
