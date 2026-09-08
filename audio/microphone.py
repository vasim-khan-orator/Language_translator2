"""
audio/microphone.py

Captures microphone audio continuously in small PCM16 chunks.
"""

import queue
import threading
from typing import Iterator, Optional

import sounddevice as sd  # pyright: ignore[reportMissingImports]

from config import SAMPLE_RATE, CHANNELS, FRAME_SIZE


class Microphone:
    """Continuous microphone audio capture."""

    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        channels: int = CHANNELS,
        frame_size: int = FRAME_SIZE,
        device: Optional[int] = None,
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_size = frame_size
        self.device = device

        self._queue = queue.Queue()
        self._stream = None
        self._running = False
        self._lock = threading.Lock()

    def _callback(self, indata, frames, time_info, status):
        """Called by sounddevice whenever new audio arrives."""

        if status:
            print(f"[Microphone] {status}")

        if not self._running:
            return

        # Convert the incoming PCM16 audio to bytes.
        self._queue.put(bytes(indata))

    def start(self):
        """Start microphone recording."""

        with self._lock:

            if self._running:
                return

            self._running = True

            self._stream = sd.RawInputStream(
                samplerate=self.sample_rate,
                blocksize=self.frame_size,
                channels=self.channels,
                dtype="int16",
                callback=self._callback,
                device=self.device,
            )

            self._stream.start()

    def frames(self) -> Iterator[bytes]:
        """
        Continuously yield microphone audio frames.

        Each frame is raw PCM16 audio.
        """

        while self._running:

            chunk = self._queue.get()

            if chunk is None:
                break

            yield chunk

    def stop(self):
        """Stop microphone recording."""

        with self._lock:

            if not self._running:
                return

            self._running = False

            # Wake the frames() method.
            self._queue.put(None)

            if self._stream is not None:

                self._stream.stop()
                self._stream.close()

                self._stream = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()