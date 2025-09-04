import asyncio
import unittest

from whisperlivekit.audio_processor import AudioProcessor, SENTINEL
from whisperlivekit.timed_objects import ASRToken, Transcript


class DummyOnline:
    sep = " "
    SAMPLING_RATE = 16000
    audio_buffer = []

    def __init__(self):
        self.called_is_last = None
        self.asr = type("asr", (), {"sep": " "})()

    def process_iter(self, is_last: bool = False):
        self.called_is_last = is_last
        return [ASRToken(0.0, 0.5, "hi")], 0.5

    def get_buffer(self):
        return Transcript(start=None, end=None, text="", probability=None)


class TranscriptionProcessorTest(unittest.TestCase):
    def test_sentinel_flushes_buffer(self):
        ap = AudioProcessor.__new__(AudioProcessor)
        ap.sep = " "
        ap.online = DummyOnline()
        ap.tokens = []
        ap.buffer_transcription = ""
        ap.end_buffer = 0.0
        ap.transcription_queue = asyncio.Queue()

        async def dummy_update(new_tokens, buffer_text, end_buffer, sep):
            ap.tokens.extend(new_tokens)
            ap.buffer_transcription = buffer_text
            ap.end_buffer = end_buffer
            ap.sep = sep

        ap.update_transcription = dummy_update

        async def run():
            await ap.transcription_queue.put(SENTINEL)
            await ap.transcription_processor()

        asyncio.run(run())

        self.assertTrue(ap.online.called_is_last)
        self.assertEqual(len(ap.tokens), 1)


if __name__ == "__main__":
    unittest.main()
