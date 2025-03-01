# My experience

Even using `--diarization False`, it still required to install and accept hf gated repo.

1.  [Accept user conditions](https://huggingface.co/pyannote/segmentation) for the `pyannote/segmentation` model
2.  [Accept user conditions](https://huggingface.co/pyannote/segmentation-3.0) for the newest `pyannote/segmentation-3.0` model
3.  [Accept user conditions](https://huggingface.co/pyannote/embedding) for the `pyannote/embedding` model
4.  Install [huggingface-cli](https://huggingface.co/docs/huggingface_hub/quick-start#install-the-hub-library) and [log in](https://huggingface.co/docs/huggingface_hub/quick-start#login) with your user access token (or provide it manually in diart CLI or API).

- https://huggingface.co/settings/tokens<br>
- WhisperStreamingWeb: Read access to contents of all public gated repos you can access<br>
- `huggingface-cli login`
- Keyin WhisperStreamingWeb token.

```cmd
pip install librosa soundfile
pip install fastapi ffmpeg-python
pip install faster-whisper
pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126
pip install uvicorn[standard]
pip install diart
python whisper_fastapi_online_server.py --host 0.0.0.0 --port 8000 --model tiny --lan zh --diarization False
--vac --vad
# --diarization False
```
http://localhost:8000

It hangs on 8 to 20 seconds.

```cmd
python whisper_noserver_test.py --audio_path "D:\Projects\GitHub\Cloned\whisper_streaming\audio\whisper_streaming_normalized.wav" --model tiny --lan zh
```

# Whisper Streaming Web: Real-time Speech-to-Text with FastAPI WebSocket

This project is based on [Whisper Streaming](https://github.com/ufal/whisper_streaming) and lets you transcribe audio directly from your browser. Simply launch the local server and grant microphone access. Everything runs locally on your machine ✨

<p align="center">
  <img src="web/demo.png" alt="Demo Screenshot" width="600">
</p>

### Differences from [Whisper Streaming](https://github.com/ufal/whisper_streaming)

#### 🌐 **Web & API**  
- **Built-in Web UI** – No frontend setup required, just open your browser and start transcribing.  
- **FastAPI WebSocket Server** – Real-time speech-to-text processing with async FFmpeg streaming.  
- **JavaScript Client** – Ready-to-use MediaRecorder implementation for seamless client-side integration.

#### ⚙️ **Core Improvements**  
- **Buffering Preview** – Displays unvalidated transcription segments for immediate feedback.  
- **Multi-User Support** – Handles multiple users simultaneously without conflicts.  
- **MLX Whisper Backend** – Optimized for Apple Silicon for faster local processing.  
- **Enhanced Sentence Segmentation** – Improved buffer trimming for better accuracy across languages.  
- **Extended Logging** – More detailed logs to improve debugging and monitoring.  

#### 🎙️ **Advanced Features**  
- **Real-Time Diarization** – Identify different speakers in real time using [Diart](https://github.com/juanmc2005/diart).  

#### 🚀 **Coming Soon**

- **Faster Word Validation** – Accelerate real-time transcription by validating high-confidence words immediately upon first appearance for whisper backends that return word & segment probabilities
- **Enhanced Diarization Performance** – Optimize speaker identification by implementing longer steps for Diart processing and leveraging language-specific segmentation patterns to improve speaker boundary detection


## Installation

1. **Clone the Repository**:

   ```bash
   git clone https://github.com/QuentinFuxa/whisper_streaming_web
   cd whisper_streaming_web
   ```


### How to Launch the Server

1. **Dependencies**:

- Install required dependences :

    ```bash
    # Whisper streaming required dependencies
    pip install librosa soundfile

    # Whisper streaming web required dependencies
    pip install fastapi ffmpeg-python
    ```
- Install at least one whisper backend among:

    ```
   whisper
   whisper-timestamped
   faster-whisper (faster backend on NVIDIA GPU)
   mlx-whisper (faster backend on Apple Silicon)
   ```
- Optionnal dependencies

    ```
    # If you want to use VAC (Voice Activity Controller). Useful for preventing hallucinations
    torch
   
    # If you choose sentences as buffer trimming strategy
    mosestokenizer
    wtpsplit
    tokenize_uk # If you work with Ukrainian text

    # If you want to run the server using uvicorn (recommended)
    uvicorn

    # If you want to use diarization
    diart
    ```

    Diart uses by default [pyannote.audio](https://github.com/pyannote/pyannote-audio) models from the _huggingface hub_. To use them, please follow the steps described [here](https://github.com/juanmc2005/diart?tab=readme-ov-file#get-access-to--pyannote-models).


3. **Run the FastAPI Server**:

    ```bash
    python whisper_fastapi_online_server.py --host 0.0.0.0 --port 8000
    ```

    - `--host` and `--port` let you specify the server’s IP/port. 
    - `-min-chunk-size` sets the minimum chunk size for audio processing. Make sure this value aligns with the chunk size selected in the frontend. If not aligned, the system will work but may unnecessarily over-process audio data.
    - For a full list of configurable options, run `python whisper_fastapi_online_server.py -h`
    - `--transcription`, default to True. Change to False if you want to run only diarization
    - `--diarization`, default to False, let you choose whether or not you want to run diarization in parallel
    - For other parameters, look at [whisper streaming](https://github.com/ufal/whisper_streaming) readme.

4. **Open the Provided HTML**:

    - By default, the server root endpoint `/` serves a simple `live_transcription.html` page.  
    - Open your browser at `http://localhost:8000` (or replace `localhost` and `8000` with whatever you specified).  
    - The page uses vanilla JavaScript and the WebSocket API to capture your microphone and stream audio to the server in real time.

### How the Live Interface Works

- Once you **allow microphone access**, the page records small chunks of audio using the **MediaRecorder** API in **webm/opus** format.  
- These chunks are sent over a **WebSocket** to the FastAPI endpoint at `/asr`.  
- The Python server decodes `.webm` chunks on the fly using **FFmpeg** and streams them into the **whisper streaming** implementation for transcription.  
- **Partial transcription** appears as soon as enough audio is processed. The “unvalidated” text is shown in **lighter or grey color** (i.e., an ‘aperçu’) to indicate it’s still buffered partial output. Once Whisper finalizes that segment, it’s displayed in normal text.  
- You can watch the transcription update in near real time, ideal for demos, prototyping, or quick debugging.

### Deploying to a Remote Server

If you want to **deploy** this setup:

1. **Host the FastAPI app** behind a production-grade HTTP(S) server (like **Uvicorn + Nginx** or Docker). If you use HTTPS, use "wss" instead of "ws" in WebSocket URL.
2. The **HTML/JS page** can be served by the same FastAPI app or a separate static host.  
3. Users open the page in **Chrome/Firefox** (any modern browser that supports MediaRecorder + WebSocket).  

No additional front-end libraries or frameworks are required. The WebSocket logic in `live_transcription.html` is minimal enough to adapt for your own custom UI or embed in other pages.

## Acknowledgments

This project builds upon the foundational work of the Whisper Streaming project. We extend our gratitude to the original authors for their contributions.

