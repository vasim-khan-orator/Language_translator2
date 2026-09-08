import time
import threading


class UtteranceManager:
    """
    Combines multiple Riva FINAL ASR segments into
    one complete user utterance.

    Riva FINAL means the segment is stable.
    It does NOT necessarily mean the user has
    stopped speaking.

    Also keeps track of which stable segments have
    already been consumed by the progressive
    translation worker.
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

        # Number of segments already given to
        # the progressive translation worker.
        self._translated_segment_index = 0

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

            self.last_final_time = (
                time.monotonic()
            )

    # =========================================================
    # CURRENT UTTERANCE
    # =========================================================

    def get_current_text(self):

        with self._lock:

            return " ".join(
                self.segments
            ).strip()

    # =========================================================
    # GET NEW STABLE TEXT
    # =========================================================

    def get_new_stable_text(self):

        """
        Returns only Riva FINAL segments that have
        not yet been sent to the progressive translator.

        Example:

            segments:
                ["Hello", "how are you", "today"]

        First call:
            "Hello"

        Second call:
            "how are you"

        Third call:
            "today"

        After that:
            None
        """

        with self._lock:

            if (
                self._translated_segment_index
                >= len(self.segments)
            ):
                return None

            new_segments = self.segments[
                self._translated_segment_index:
            ]

            self._translated_segment_index = (
                len(self.segments)
            )

            text = " ".join(
                new_segments
            ).strip()

            return text if text else None

    # =========================================================
    # FINALIZE WHEN SILENT
    # =========================================================

    def finalize_if_ready(self):

        with self._lock:

            if not self.segments:
                return None

            if self.last_final_time is None:
                return None

            elapsed = (
                time.monotonic()
                - self.last_final_time
            )

            if elapsed < self.silence_timeout:
                return None

            text = " ".join(
                self.segments
            ).strip()

            self.segments.clear()

            self.last_final_time = None

            # New utterance starts after this point.
            self._translated_segment_index = 0

        if len(text) < self.min_utterance_length:
            return None

        return text

    # =========================================================
    # CHECK CONTENT
    # =========================================================

    def has_content(self):

        with self._lock:

            return bool(
                self.segments
            )

    # =========================================================
    # CLEAR
    # =========================================================

    def clear(self):

        with self._lock:

            self.segments.clear()

            self.last_final_time = None

            self._translated_segment_index = 0