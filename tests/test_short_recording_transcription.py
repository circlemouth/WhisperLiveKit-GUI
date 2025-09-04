import asyncio
import unittest
import numpy as np
from types import SimpleNamespace

from whisperlivekit.audio_processor import AudioProcessor, SENTINEL
from whisperlivekit.ffmpeg_manager import FFmpegState
from whisperlivekit.timed_objects import ASRToken, Transcript


class DummyFFmpegManager:
    async def get_state(self):
        return FFmpegState.RUNNING

    async def read_data(self, buffer_size):
        return b""


class DummyOnline:
    sep = " "
    SAMPLING_RATE = 16000
    audio_buffer = []

    def __init__(self):
        self.asr = type("asr", (), {"sep": " "})()
        self.called_is_last = None

    def insert_audio_chunk(self, pcm_array, end_time):
        pass

    def process_iter(self, is_last: bool = False):
        self.called_is_last = is_last
        return [ASRToken(0.0, 0.1, "hi")], 0.1

    def get_buffer(self):
        return Transcript(start=None, end=None, text="", probability=None)

    def insert_silence(self, duration, last_end):
        pass


class ShortRecordingTranscriptionTest(unittest.TestCase):
    def test_short_recording_produces_transcript(self):
        ap = AudioProcessor.__new__(AudioProcessor)
        ap.args = SimpleNamespace(transcription=True, diarization=False, vac=False)
        ap.sample_rate = 16000
        ap.bytes_per_sample = 2
        ap.bytes_per_sec = 32000
        ap.max_bytes_per_sec = 32000
        ap.pcm_buffer = bytearray(np.zeros(1600, dtype=np.int16).tobytes())
        ap.ffmpeg_manager = DummyFFmpegManager()
        ap.is_stopping = True
        ap.transcription_queue = asyncio.Queue()
        ap.diarization_queue = None
        ap.vac = None
        ap.silence = False
        ap.convert_pcm_to_float = AudioProcessor.convert_pcm_to_float.__get__(ap)
        ap.online = DummyOnline()
        ap.tokens = []
        ap.buffer_transcription = ""
        ap.end_buffer = 0.0
        ap.beg_loop = 0
        ap.sep = " "

        async def dummy_update(new_tokens, buffer_text, end_buffer, sep):
            ap.tokens.extend(new_tokens)
            ap.buffer_transcription = buffer_text
            ap.end_buffer = end_buffer
            ap.sep = sep

        ap.update_transcription = dummy_update

        async def run():
            await ap.ffmpeg_stdout_reader()
            await ap.transcription_processor()

        asyncio.run(run())

        self.assertGreater(len(ap.tokens), 0)
        self.assertTrue(ap.online.called_is_last)


if __name__ == "__main__":
    unittest.main()
