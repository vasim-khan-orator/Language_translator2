import queue
import threading
import time


class TranslationWorker:

    def __init__(
        self,
        translator,
        conversation,
        renderer=None,
        bridge=None,
    ):

        self.translator = translator
        self.conversation = conversation
        self.renderer = renderer
        self.bridge = bridge

        self._queue = queue.Queue()
        self._thread = None
        self._running = False
        self._lock = threading.Lock()

    # =========================================================
    # START
    # =========================================================

    def start(self):

        with self._lock:

            if self._running:
                return

            self._running = True

            self._thread = threading.Thread(
                target=self._run,
                daemon=True,
            )

            self._thread.start()

    # =========================================================
    # SUBMIT
    # =========================================================

    def submit(self, turn):

        if not self._running:
            return

        self._queue.put(turn)

    # =========================================================
    # STOP
    # =========================================================

    def stop(self):

        with self._lock:

            if not self._running:
                return

            self._running = False

            self._queue.put(None)

        if self._thread is not None:

            self._thread.join(
                timeout=2
            )

            self._thread = None

    # =========================================================
    # WORKER LOOP
    # =========================================================

    def _run(self):

        while True:

            turn = self._queue.get()

            if turn is None:
                break

            try:

                # -------------------------------------------------
                # START TRANSLATION TIMER
                # -------------------------------------------------

                translation_start = time.perf_counter()

                if self.bridge is not None:
                    self.bridge.translation_started()

                # -------------------------------------------------
                # TRANSLATE
                # -------------------------------------------------

                translated_text = self.translator.translate(
                    turn.source_text,
                    turn.source_language,
                    turn.target_language,
                )

                # -------------------------------------------------
                # END TRANSLATION TIMER
                # -------------------------------------------------

                translation_end = time.perf_counter()

                api_ms = (
                    translation_end
                    - translation_start
                ) * 1000

                # -------------------------------------------------
                # UPDATE CONVERSATION
                # -------------------------------------------------

                self.conversation.update_translation(
                    turn.id,
                    translated_text,
                )

                # -------------------------------------------------
                # UI
                # -------------------------------------------------

                if self.bridge is not None:

                    self.bridge.translation_finished(
                        text=translated_text,
                        api_ms=api_ms,
                        total_ms=api_ms,
                    )

                # -------------------------------------------------
                # OLD TERMINAL RENDERER
                # -------------------------------------------------

                if self.renderer is not None:

                    self.renderer.render_translation(
                        turn
                    )

            except Exception as exc:

                print(
                    f"[TranslationWorker] {exc}"
                )

                if self.bridge is not None:

                    self.bridge.error(
                        str(exc)
                    )