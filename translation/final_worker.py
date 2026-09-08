import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor


class FinalTranslationWorker:
    """
    Translates complete finalized conversation turns.

    Final translation runs independently from ChunkWorker.

    After a final translation is successfully accepted,
    an optional callback can schedule context-aware refinement.

    Multiple finalized turns may be processed concurrently
    using a bounded thread pool.
    """

    def __init__(
        self,
        translator,
        conversation,
        bridge=None,
        refinement_callback=None,
        max_workers=2,
    ):

        self.translator = translator
        self.conversation = conversation
        self.bridge = bridge

        # Called only after a final translation is successfully
        # accepted by ConversationManager.
        #
        # Expected callback:
        #
        #     refinement_worker.submit
        #
        self.refinement_callback = (
            refinement_callback
        )

        self.max_workers = max_workers

        # Incoming completed turns.
        self._queue = queue.Queue()

        self._thread = None
        self._running = False
        self._lock = threading.RLock()

        # Ollama executor.
        self._executor = None

    # =========================================================
    # START
    # =========================================================

    def start(self):

        with self._lock:

            if self._running:
                return

            self._running = True

            # Create a fresh executor every time the worker starts.
            self._executor = ThreadPoolExecutor(
                max_workers=self.max_workers
            )

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

        if turn is None:
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

        with self._lock:

            executor = self._executor
            self._executor = None

        if executor is not None:

            executor.shutdown(
                wait=False,
                cancel_futures=True,
            )

    # =========================================================
    # WORKER LOOP
    # =========================================================

    def _run(self):

        while True:

            turn = self._queue.get()

            if turn is None:
                break

            # -------------------------------------------------
            # Reserve a new revision BEFORE sending the request.
            #
            # This immediately makes any older progressive
            # translation for this turn stale.
            # -------------------------------------------------

            revision = (
                self.conversation.reserve_revision(
                    turn.id
                )
            )

            if revision is None:
                continue

            # -------------------------------------------------
            # Get executor.
            # -------------------------------------------------

            with self._lock:

                executor = self._executor

            if executor is None:
                continue

            # -------------------------------------------------
            # Submit actual Ollama work asynchronously.
            # -------------------------------------------------

            executor.submit(
                self._translate,
                turn,
                revision,
            )

    # =========================================================
    # FINAL TRANSLATION
    # =========================================================

    def _translate(
        self,
        turn,
        revision,
    ):

        try:

            if self.bridge is not None:

                self.bridge.translation_started()

            translation_start = (
                time.perf_counter()
            )

            translated_text, api_ms = (
                self.translator.translate_final(
                    text=turn.source_text,
                    source_language=turn.source_language,
                    target_language=turn.target_language,
                )
            )

            translation_end = (
                time.perf_counter()
            )

            total_ms = (
                translation_end
                - translation_start
            ) * 1000

            # -------------------------------------------------
            # Apply only when this is still the newest revision.
            # -------------------------------------------------

            accepted = (
                self.conversation.apply_translation(
                    turn_id=turn.id,
                    translated_text=translated_text,
                    revision=revision,
                )
            )

            # -------------------------------------------------
            # Ignore stale final responses.
            # -------------------------------------------------

            if not accepted:
                return

            # -------------------------------------------------
            # Send accepted final translation to UI.
            # -------------------------------------------------

            if self.bridge is not None:

                self.bridge.translation_final(
                    text=translated_text,
                    turn_id=turn.id,
                    revision=revision,
                    api_ms=api_ms,
                    total_ms=total_ms,
                )

            # -------------------------------------------------
            # Schedule refinement ONLY after the final
            # translation has been successfully accepted.
            # -------------------------------------------------

            if self.refinement_callback is not None:

                try:

                    # Get the latest turn state rather than using
                    # an older mutable reference.
                    latest_turn = (
                        self.conversation.get_turn(
                            turn.id
                        )
                    )

                    if latest_turn is not None:

                        self.refinement_callback(
                            latest_turn
                        )

                except Exception as exc:

                    print(
                        "[FinalTranslationWorker] "
                        f"Refinement scheduling error: {exc}"
                    )

                    if self.bridge is not None:

                        self.bridge.error(
                            str(exc)
                        )

        except Exception as exc:

            print(
                f"[FinalTranslationWorker] {exc}"
            )

            if self.bridge is not None:

                self.bridge.error(
                    str(exc)
                )

        finally:

            if self.bridge is not None:

                self.bridge.translation_completed()