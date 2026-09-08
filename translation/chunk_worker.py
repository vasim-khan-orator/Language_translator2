import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor


class ChunkWorker:
    """
    Concurrent progressive translation worker.

    Receives stable Riva FINAL ASR segments and translates
    progressive source windows using a bounded thread pool.

    Design:

        Riva FINAL
             |
             v
        ChunkWorker
             |
        +----+----+----------------
        |         |               |
        v         v               v
     Ollama    Ollama          Ollama
     worker 1  worker 2        worker 3

    When all workers are busy, only the newest pending
    source window is retained.

    Translation results are protected using ConversationManager
    revisions so older responses cannot overwrite newer ones.
    """

    def __init__(
        self,
        translator,
        conversation=None,
        bridge=None,
        max_workers=3,
        chunk_interval=0.15,
    ):

        self.translator = translator
        self.conversation = conversation
        self.bridge = bridge

        self.max_workers = max_workers
        self.chunk_interval = chunk_interval

        # =====================================================
        # INPUT QUEUE
        # =====================================================

        self._queue = queue.Queue()

        # =====================================================
        # THREAD / STATE
        # =====================================================

        self._thread = None
        self._running = False

        self._lock = threading.RLock()

        # =====================================================
        # OLLAMA EXECUTOR
        # =====================================================

        self._executor = None

        # Number of currently running Ollama requests.
        self._in_flight = 0

        # =====================================================
        # CURRENT TURN
        # =====================================================

        self._current_turn_id = None

        self._source_segments = []

        self._last_submitted_segment = ""

        # =====================================================
        # LATEST PENDING SOURCE WINDOW
        # =====================================================

        self._pending_source = None

        # Used for the 100-200 ms progressive scheduling window.
        self._last_dispatch_time = 0.0

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

            self._in_flight = 0

            self._thread = threading.Thread(
                target=self._run,
                daemon=True,
            )

            self._thread.start()

    # =========================================================
    # SUBMIT
    # =========================================================

    def submit(
        self,
        text,
        source_language,
        target_language,
        turn_id,
    ):
        """
        Submit one stable Riva FINAL segment.

        turn_id is intentionally required.

        main.py should create the ConversationTurn when
        the first stable segment of an utterance arrives.
        """

        if not self._running:
            return

        text = text.strip()

        if not text:
            return

        self._queue.put(
            (
                "segment",
                text,
                source_language,
                target_language,
                turn_id,
            )
        )

    # =========================================================
    # RESET TURN
    # =========================================================

    def reset_turn(self):

        if not self._running:
            return

        self._queue.put(
            (
                "reset",
                None,
                None,
                None,
                None,
            )
        )

    # =========================================================
    # STOP
    # =========================================================

    def stop(self):

        with self._lock:

            if not self._running:
                return

            self._running = False

            self._queue.put(
                (
                    "stop",
                    None,
                    None,
                    None,
                    None,
                )
            )

        if self._thread is not None:

            self._thread.join(
                timeout=2
            )

            self._thread = None

        executor = None

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

            try:

                item = self._queue.get(
                    timeout=0.02
                )

            except queue.Empty:

                self._try_dispatch_pending()

                continue

            event_type = item[0]

            # -------------------------------------------------
            # STOP
            # -------------------------------------------------

            if event_type == "stop":
                break

            # -------------------------------------------------
            # RESET
            # -------------------------------------------------

            if event_type == "reset":

                with self._lock:

                    self._current_turn_id = None
                    self._source_segments.clear()
                    self._last_submitted_segment = ""
                    self._pending_source = None

                continue

            # -------------------------------------------------
            # STABLE SEGMENT
            # -------------------------------------------------

            (
                _,
                text,
                source_language,
                target_language,
                turn_id,
            ) = item

            # -------------------------------------------------
            # DUPLICATE PROTECTION
            # -------------------------------------------------

            if text == self._last_submitted_segment:
                continue

            self._last_submitted_segment = text

            # -------------------------------------------------
            # NEW TURN
            # -------------------------------------------------

            if turn_id != self._current_turn_id:

                with self._lock:

                    self._current_turn_id = turn_id

                    self._source_segments.clear()

                    self._pending_source = None

            # -------------------------------------------------
            # ADD STABLE SOURCE
            # -------------------------------------------------

            self._source_segments.append(
                text
            )

            source_text = " ".join(
                self._source_segments
            ).strip()

            if not source_text:
                continue

            # -------------------------------------------------
            # SAVE AS LATEST PENDING WINDOW
            # -------------------------------------------------

            with self._lock:

                self._pending_source = (
                    source_text,
                    source_language,
                    target_language,
                    turn_id,
                )

            # -------------------------------------------------
            # TRY TO DISPATCH
            # -------------------------------------------------

            self._try_dispatch_pending()

    # =========================================================
    # DISPATCH PENDING REQUEST
    # =========================================================

    def _try_dispatch_pending(self):

        with self._lock:

            if not self._running:
                return

            if self._pending_source is None:
                return

            if self._executor is None:
                return

            # All workers are occupied.
            # Keep the newest source window pending.
            if self._in_flight >= self.max_workers:
                return

            now = time.perf_counter()

            elapsed = (
                now
                - self._last_dispatch_time
            )

            # Avoid firing requests faster than the configured
            # progressive interval.
            if (
                self._last_dispatch_time > 0
                and elapsed < self.chunk_interval
            ):
                return

            (
                source_text,
                source_language,
                target_language,
                turn_id,
            ) = self._pending_source

            self._pending_source = None

            # -------------------------------------------------
            # RESERVE REVISION
            # -------------------------------------------------

            revision = None

            if (
                self.conversation is not None
                and turn_id is not None
            ):

                revision = (
                    self.conversation.reserve_revision(
                        turn_id
                    )
                )

                if revision is None:

                    return

            # -------------------------------------------------
            # MARK REQUEST IN FLIGHT
            # -------------------------------------------------

            self._in_flight += 1

            self._last_dispatch_time = now

            # -------------------------------------------------
            # START ASYNC OLLAMA REQUEST
            # -------------------------------------------------

            self._executor.submit(
                self._translate,
                source_text,
                source_language,
                target_language,
                turn_id,
                revision,
            )

    # =========================================================
    # OLLAMA TRANSLATION
    # =========================================================

    def _translate(
        self,
        source_text,
        source_language,
        target_language,
        turn_id,
        revision,
    ):

        try:

            if self.bridge is not None:

                self.bridge.translation_started()

            translation_start = (
                time.perf_counter()
            )

            translated_text, api_ms = (
                self.translator.translate_chunk(
                    text=source_text,
                    source_language=source_language,
                    target_language=target_language,
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
            # CHECK WHETHER RESULT IS STILL CURRENT
            # -------------------------------------------------

            accepted = True

            if (
                self.conversation is not None
                and turn_id is not None
                and revision is not None
            ):

                accepted = (
                    self.conversation.apply_translation(
                        turn_id=turn_id,
                        translated_text=translated_text,
                        revision=revision,
                    )
                )

            # -------------------------------------------------
            # DISPLAY ONLY CURRENT RESULT
            # -------------------------------------------------

            if accepted:

                if self.bridge is not None:

                    self.bridge.translation_chunk(
                        text=translated_text,
                        turn_id=turn_id,
                        revision=revision,
                        api_ms=api_ms,
                        total_ms=total_ms,
                    )

        except Exception as exc:

            print(
                f"[ChunkWorker] {exc}"
            )

            if self.bridge is not None:

                self.bridge.error(
                    str(exc)
                )

        finally:

            if self.bridge is not None:
                self.bridge.translation_completed()

            # -------------------------------------------------
            # RELEASE WORKER SLOT
            # -------------------------------------------------

            with self._lock:

                if self._in_flight > 0:

                    self._in_flight -= 1

            # -------------------------------------------------
            # Immediately try the newest pending source.
            # -------------------------------------------------

            self._try_dispatch_pending()