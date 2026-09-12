import time
import threading


class UtteranceManager:
    """
    Combines multiple Riva FINAL ASR segments into one complete
    spoken utterance.

    Riva FINAL means the segment is stable. It does not necessarily
    mean the user has stopped speaking.

    A spoken utterance is considered complete after no new Riva
    FINAL segment has arrived for ``silence_timeout`` seconds.
    The completed utterance is then sent as a final update to the translator.
    """

    def __init__(
        self,
        silence_timeout=0.4,
        min_utterance_length=2,
    ):
        self.silence_timeout = silence_timeout
        self.min_utterance_length = min_utterance_length

        self.segments = []
        self.last_final_time = None

        # All state is protected because Riva and the monitor thread
        # access the manager concurrently.
        self._lock = threading.Lock()

    # =========================================================
    # ADD RIVA FINAL SEGMENT
    # =========================================================

    def add_final_segment(self, text):
        text = text.strip()

        if not text:
            return

        with self._lock:
            self.segments.append(text)
            self.last_final_time = time.monotonic()

    # =========================================================
    # CURRENT UTTERANCE
    # =========================================================

    def get_current_text(self):
        with self._lock:
            return " ".join(self.segments).strip()

    # =========================================================
    # FINALIZE WHEN SILENT
    # =========================================================

    def finalize_if_ready(self):
        with self._lock:
            if not self.segments:
                return None

            if self.last_final_time is None:
                return None

            elapsed = time.monotonic() - self.last_final_time

            if elapsed < self.silence_timeout:
                return None

            text = " ".join(self.segments).strip()

            # Start a fresh utterance.
            self.segments.clear()
            self.last_final_time = None

        if len(text) < self.min_utterance_length:
            return None

        return text

    # =========================================================
    # CHECK CONTENT
    # =========================================================

    def has_content(self):
        with self._lock:
            return bool(self.segments)

    # =========================================================
    # CLEAR
    # =========================================================

    def clear(self):
        with self._lock:
            self.segments.clear()
            self.last_final_time = None
