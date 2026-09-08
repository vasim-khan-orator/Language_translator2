import shutil
import threading


class TerminalRenderer:

    def __init__(self):
        self._lock = threading.Lock()
        self._listening = False
        self._partial_text = ""

    # =========================================================
    # TERMINAL HELPERS
    # =========================================================

    def _terminal_width(self):
        return shutil.get_terminal_size((100, 20)).columns

    def _clear_current_line(self):
        width = self._terminal_width()

        print(
            "\r" + (" " * (width - 1)),
            end="\r",
        )

    # =========================================================
    # LISTENING
    # =========================================================

    def render_listening(self):
        with self._lock:
            self._listening = True
            self._partial_text = ""

            print()
            print("🎤 Listening...", flush=True)

    # =========================================================
    # LIVE ASR
    # =========================================================

    def render_partial(self, text, buffered_text=""):

        text = text.strip()
        buffered_text = buffered_text.strip()

        display_text = ""

        if buffered_text and text:
            display_text = f"{buffered_text} {text}"

        elif buffered_text:
            display_text = buffered_text

        elif text:
            display_text = text

        if not display_text:
            return

        with self._lock:

            self._partial_text = display_text

            width = self._terminal_width()

            # Keep the live display on ONE terminal line.
            #
            # This is important because \r cannot safely erase
            # text that has wrapped onto multiple terminal lines.

            prefix = "[Listening] "

            available = max(
                10,
                width - len(prefix) - 1
            )

            if len(display_text) > available:
                display_text = "..." + display_text[-(available - 3):]

            self._clear_current_line()

            print(
                prefix + display_text,
                end="",
                flush=True,
            )

    # =========================================================
    # CLEAR LIVE ASR
    # =========================================================

    def clear_partial(self):

        with self._lock:

            if self._partial_text:

                self._clear_current_line()

                self._partial_text = ""

    # =========================================================
    # FINALIZED SOURCE UTTERANCE
    # =========================================================

    def render_turn(self, turn):

        with self._lock:

            self._clear_current_line()

            self._partial_text = ""

            print()
            print("=" * 70)

            print(
                f"Turn #{turn.id}  "
                f"[{turn.timestamp.strftime('%H:%M:%S')}]"
            )

            print()

            print(f"[{turn.source_language}]")
            print(turn.source_text)

            print("=" * 70)

            print()
            print("🎤 Listening...")

    # =========================================================
    # TRANSLATION RESULT
    # =========================================================

    def render_translation(self, turn):

        if not turn.translated_text:
            return

        with self._lock:

            self._clear_current_line()

            self._partial_text = ""

            print()
            print(
                f"Turn #{turn.id} translation:"
            )

            print(
                f"[{turn.target_language}]"
            )

            print(
                turn.translated_text
            )

            print()

            print("🎤 Listening...")

            # Restore current live ASR text if speech has already
            # started while Ollama was translating.

            if self._partial_text:
                self.render_partial(
                    "",
                    self._partial_text
                )