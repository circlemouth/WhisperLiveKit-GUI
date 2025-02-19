from diart import SpeakerDiarization
from diart.inference import StreamingInference
from diart.sources import AudioSource
from rx.subject import Subject
import threading
import numpy as np
import asyncio
import re

def extract_number(s):
    match = re.search(r'\d+', s)
    return int(match.group()) if match else None

class WebSocketAudioSource(AudioSource):
    """
    Simple custom AudioSource that blocks in read()
    until close() is called.
    push_audio() is used to inject new PCM chunks.
    """
    def __init__(self, uri: str = "websocket", sample_rate: int = 16000):
        super().__init__(uri, sample_rate)
        self._close_event = threading.Event()
        self._closed = False

    def read(self):
        self._close_event.wait()

    def close(self):
        if not self._closed:
            self._closed = True
            self.stream.on_completed()
            self._close_event.set()

    def push_audio(self, chunk: np.ndarray):
        chunk = np.expand_dims(chunk, axis=0)
        if not self._closed:
            self.stream.on_next(chunk)


def create_pipeline(SAMPLE_RATE):
    diar_pipeline = SpeakerDiarization()
    ws_source = WebSocketAudioSource(uri="websocket_source", sample_rate=SAMPLE_RATE)
    inference = StreamingInference(
        pipeline=diar_pipeline,
        source=ws_source,
        do_plot=False,
        show_progress=False,
    )
    return inference, ws_source


def init_diart(SAMPLE_RATE, diar_instance):
    diar_pipeline = SpeakerDiarization()
    ws_source = WebSocketAudioSource(uri="websocket_source", sample_rate=SAMPLE_RATE)
    inference = StreamingInference(
        pipeline=diar_pipeline,
        source=ws_source,
        do_plot=False,
        show_progress=False,
    )

    l_speakers_queue = asyncio.Queue()

    def diar_hook(result):
        """
        Hook called each time Diart processes a chunk.
        result is (annotation, audio).
        For each detected speaker segment, push its info to the queue and update processed_time.
        """
        annotation, audio = result
        if annotation._labels:
            for speaker in annotation._labels:
                segments_beg = annotation._labels[speaker].segments_boundaries_[0]
                segments_end = annotation._labels[speaker].segments_boundaries_[-1]
                if segments_end > diar_instance.processed_time:
                    diar_instance.processed_time = segments_end
                asyncio.create_task(
                    l_speakers_queue.put({"speaker": speaker, "beg": segments_beg, "end": segments_end})
                )
        else:
            audio_duration = audio.extent.end
            if audio_duration > diar_instance.processed_time:
                diar_instance.processed_time = audio_duration

    inference.attach_hooks(diar_hook)
    loop = asyncio.get_event_loop()
    diar_future = loop.run_in_executor(None, inference)
    return inference, l_speakers_queue, ws_source

class DiartDiarization:
    def __init__(self, SAMPLE_RATE):
        self.processed_time = 0  
        self.inference, self.l_speakers_queue, self.ws_source = init_diart(SAMPLE_RATE, self)
        self.segment_speakers = []

    async def diarize(self, pcm_array):
        self.ws_source.push_audio(pcm_array)
        self.segment_speakers = []
        while not self.l_speakers_queue.empty():
            self.segment_speakers.append(await self.l_speakers_queue.get())

    def close(self):
        self.ws_source.close()

    def assign_speakers_to_chunks(self, chunks):
        """
        For each chunk (a dict with keys "beg" and "end"), assign a speaker label.
        
        - If a chunk overlaps with a detected speaker segment, assign that label.
        - If the chunk's end time is within the processed time and no speaker was assigned,
          mark it as "No speaker".
        - If the chunk's time hasn't been fully processed yet, leave it (or mark as "Processing").
        """
        for ch in chunks:
            ch["speaker"] = ch.get("speaker", -1)

        for segment in self.segment_speakers:
            seg_beg = segment["beg"]
            seg_end = segment["end"]
            speaker = segment["speaker"]
            for ch in chunks:
                if seg_end <= ch["beg"] or seg_beg >= ch["end"]:
                    continue
                ch["speaker"] = extract_number(speaker) + 1
        if self.processed_time > 0:
            for ch in chunks:
                if ch["end"] <= self.processed_time and ch["speaker"] == -1:
                    ch["speaker"] = -2

        return chunks