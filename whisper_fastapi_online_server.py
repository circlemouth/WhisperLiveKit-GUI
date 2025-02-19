import io
import argparse
import asyncio
import numpy as np
import ffmpeg
from time import time, sleep
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from src.whisper_streaming.whisper_online import backend_factory, online_factory, add_shared_args

import math
import logging
from datetime import timedelta

def format_time(seconds):
    return str(timedelta(seconds=int(seconds)))


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logging.getLogger().setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

##### LOAD ARGS #####

parser = argparse.ArgumentParser(description="Whisper FastAPI Online Server")
parser.add_argument(
    "--host",
    type=str,
    default="localhost",
    help="The host address to bind the server to.",
)
parser.add_argument(
    "--port", type=int, default=8000, help="The port number to bind the server to."
)
parser.add_argument(
    "--warmup-file",
    type=str,
    dest="warmup_file",
    help="The path to a speech audio wav file to warm up Whisper so that the very first chunk processing is fast. It can be e.g. https://github.com/ggerganov/whisper.cpp/raw/master/samples/jfk.wav .",
)

parser.add_argument(
    "--diarization",
    type=bool,
    default=False,
    help="Whether to enable speaker diarization.",
)

parser.add_argument(
    "--transcription",
    type=bool,
    default=True,
    help="To disable to only see live diarization results.",
)

add_shared_args(parser)
args = parser.parse_args()

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLES_PER_SEC = SAMPLE_RATE * int(args.min_chunk_size)
BYTES_PER_SAMPLE = 2  # s16le = 2 bytes per sample
BYTES_PER_SEC = SAMPLES_PER_SEC * BYTES_PER_SAMPLE
MAX_BYTES_PER_SEC = 32000 * 5  # 5 seconds of audio at 32 kHz

if args.diarization:
    from src.diarization.diarization_online import DiartDiarization


##### LOAD APP #####

@asynccontextmanager
async def lifespan(app: FastAPI):
    global asr, tokenizer
    if args.transcription:
        asr, tokenizer = backend_factory(args)
    else:
        asr, tokenizer = None, None
    yield

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Load demo HTML for the root endpoint
with open("src/web/live_transcription.html", "r", encoding="utf-8") as f:
    html = f.read()

async def start_ffmpeg_decoder():
    """
    Start an FFmpeg process in async streaming mode that reads WebM from stdin
    and outputs raw s16le PCM on stdout. Returns the process object.
    """
    process = (
        ffmpeg.input("pipe:0", format="webm")
        .output(
            "pipe:1",
            format="s16le",
            acodec="pcm_s16le",
            ac=CHANNELS,
            ar=str(SAMPLE_RATE),
        )
        .run_async(pipe_stdin=True, pipe_stdout=True, pipe_stderr=True)
    )
    return process


##### ENDPOINTS #####

@app.get("/")
async def get():
    return HTMLResponse(html)

@app.websocket("/asr")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connection opened.")

    ffmpeg_process = None
    pcm_buffer = bytearray()
    online = online_factory(args, asr, tokenizer) if args.transcription else None
    diarization = DiartDiarization(SAMPLE_RATE) if args.diarization else None

    async def restart_ffmpeg():
        nonlocal ffmpeg_process, online, diarization, pcm_buffer
        if ffmpeg_process:
            try:
                ffmpeg_process.kill()
                await asyncio.get_event_loop().run_in_executor(None, ffmpeg_process.wait)
            except Exception as e:
                logger.warning(f"Error killing FFmpeg process: {e}")
        ffmpeg_process = await start_ffmpeg_decoder()
        pcm_buffer = bytearray()
        online = online_factory(args, asr, tokenizer) if args.transcription else None
        if args.diarization:
            diarization = DiartDiarization(SAMPLE_RATE)
        logger.info("FFmpeg process started.")

    await restart_ffmpeg()

    async def ffmpeg_stdout_reader():
        nonlocal ffmpeg_process, online, diarization, pcm_buffer
        loop = asyncio.get_event_loop()
        full_transcription = ""
        beg = time()
        beg_loop = time()
        chunk_history = []  # Will store dicts: {beg, end, text, speaker}
        
        while True:
            try:
                elapsed_time = math.floor((time() - beg) * 10) / 10 # Round to 0.1 sec
                ffmpeg_buffer_from_duration = max(int(32000 * elapsed_time), 4096)
                beg = time()

                # Read chunk with timeout
                try:
                    chunk = await asyncio.wait_for(
                        loop.run_in_executor(
                            None, ffmpeg_process.stdout.read, ffmpeg_buffer_from_duration
                        ),
                        timeout=5.0
                    )
                except asyncio.TimeoutError:
                    logger.warning("FFmpeg read timeout. Restarting...")
                    await restart_ffmpeg()
                    full_transcription = ""
                    chunk_history = []
                    beg = time()
                    continue  # Skip processing and read from new process

                if not chunk:
                    logger.info("FFmpeg stdout closed.")
                    break

                pcm_buffer.extend(chunk)
                if len(pcm_buffer) >= BYTES_PER_SEC:
                    if len(pcm_buffer) > MAX_BYTES_PER_SEC:
                        logger.warning(
                            f"""Audio buffer is too large: {len(pcm_buffer) / BYTES_PER_SEC:.2f} seconds.
                            The model probably struggles to keep up. Consider using a smaller model.
                            """)
                    # Convert int16 -> float32
                    pcm_array = (
                        np.frombuffer(pcm_buffer[:MAX_BYTES_PER_SEC], dtype=np.int16).astype(np.float32)
                        / 32768.0
                    )
                    pcm_buffer = pcm_buffer[MAX_BYTES_PER_SEC:]
                    
                    if args.transcription:
                        logger.info(f"{len(online.audio_buffer) / online.SAMPLING_RATE} seconds of audio will be processed by the model.")
                        online.insert_audio_chunk(pcm_array)
                        transcription = online.process_iter()
                        if transcription.start:
                            chunk_history.append({
                                "beg": transcription.start,
                                "end": transcription.end,
                                "text": transcription.text,
                            })
                        full_transcription += transcription.text if transcription else ""
                        buffer = online.get_buffer()
                        if buffer in full_transcription: # With VAC, the buffer is not updated until the next chunk is processed
                            buffer = ""
                    else:
                        chunk_history.append({
                                "beg": time() - beg_loop,
                                "end": time() - beg_loop + 0.1,
                                "text": '',
                        })
                        sleep(0.1)
                        buffer = ''

                    if args.diarization:
                        await diarization.diarize(pcm_array)
                        diarization.assign_speakers_to_chunks(chunk_history)

                    
                    current_speaker = -1
                    lines = [{
                        "beg": 0,
                        "end": 0,
                        "speaker": current_speaker,
                        "text": ""
                        }]
                    for ch in chunk_history:
                        if args.diarization and ch["speaker"] and ch["speaker"] != current_speaker:
                            new_speaker = ch["speaker"]
                            lines.append(
                                {
                                    "speaker": new_speaker,
                                    "text": ch['text'],
                                    "beg": format_time(ch['beg']),
                                    "end": format_time(ch['end']),
                                }
                            )
                            current_speaker = new_speaker
                        else:
                            lines[-1]["text"] += ch['text']
                            lines[-1]["end"] = format_time(ch['end'])

                    response = {"lines": lines, "buffer": buffer}
                    await websocket.send_json(response)
                    
            except Exception as e:
                logger.warning(f"Exception in ffmpeg_stdout_reader: {e}")
                break

        logger.info("Exiting ffmpeg_stdout_reader...")

    stdout_reader_task = asyncio.create_task(ffmpeg_stdout_reader())

    try:
        while True:
            # Receive incoming WebM audio chunks from the client
            message = await websocket.receive_bytes()
            try:
                ffmpeg_process.stdin.write(message)
                ffmpeg_process.stdin.flush()
            except (BrokenPipeError, AttributeError) as e:
                logger.warning(f"Error writing to FFmpeg: {e}. Restarting...")
                await restart_ffmpeg()
                ffmpeg_process.stdin.write(message)
                ffmpeg_process.stdin.flush()
    except WebSocketDisconnect:
        logger.warning("WebSocket disconnected.")
    finally:
        stdout_reader_task.cancel()
        try:
            ffmpeg_process.stdin.close()
            ffmpeg_process.wait()
        except:
            pass
        if args.diarization:
            diarization.close()



if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "whisper_fastapi_online_server:app", host=args.host, port=args.port, reload=True,
        log_level="info"
    )