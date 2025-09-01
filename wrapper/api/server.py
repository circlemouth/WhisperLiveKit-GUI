import json
import os
import subprocess
from typing import List

from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Request, Depends
from fastapi.responses import JSONResponse

import websockets

BACKEND_HOST = os.getenv("WRAPPER_BACKEND_HOST", "localhost")
BACKEND_PORT = os.getenv("WRAPPER_BACKEND_PORT", "8000")
# Choose ws/wss based on backend SSL flag from GUI
BACKEND_SSL = os.getenv("WRAPPER_BACKEND_SSL", "0") == "1"
BACKEND_WS_SCHEME = "wss" if BACKEND_SSL else "ws"
BACKEND_WS_URL = f"{BACKEND_WS_SCHEME}://{BACKEND_HOST}:{BACKEND_PORT}/asr"

# API key settings (provided by GUI via environment variables)
REQUIRE_API_KEY = os.getenv("WRAPPER_REQUIRE_API_KEY", "0") == "1"
API_KEY = os.getenv("WRAPPER_API_KEY", "")

app = FastAPI(title="WhisperLiveKit Wrapper API")


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


async def _stream_to_backend(pcm_bytes: bytes) -> List[str]:
    """Stream PCM audio to the backend WebSocket and collect transcription."""
    texts: List[str] = []
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
            lines = data.get("lines", [])
            buffer_transcription = data.get("buffer_transcription", "")
            buffer_diarization = data.get("buffer_diarization", "")
            for item in lines:
                text = item.get("text")
                if text:
                    texts.append(text)
            if buffer_transcription:
                texts.append(buffer_transcription)
            if buffer_diarization:
                texts.append(buffer_diarization)
        await ws.close()
    return texts


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


@app.post("/v1/audio/transcriptions")
async def transcribe(
    file: UploadFile = File(...),
    model: str = Form("whisper-1"),
    _auth: None = Depends(require_api_key_dep),
):
    """Whisper API compatible transcription endpoint."""
    raw = await file.read()
    pcm = _convert_to_pcm16(raw)
    texts = await _stream_to_backend(pcm)
    final_text = " ".join(t.strip() for t in texts if t).strip()
    return JSONResponse({"text": final_text, "model": model})
