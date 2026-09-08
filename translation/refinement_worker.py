import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor


class RefinementWorker:
    """
    Context-aware concurrent translation refinement worker.

    Refinement is scheduled after a delay so that the system
    does not immediately spend another Ollama request after
    every final translation.

    Multiple different turns can be refined concurrently.

    For the same turn, only the latest refinement request is
    allowed to update the conversation.
    """

    def __init__(
        self,
        translator,
        context_manager,
        bridge=None,
        refresh_interval=1.2,
        max_workers=2,
    ):

        self.translator = translator
        self.context_manager = context_manager
        self.bridge = bridge

        self.refresh_interval = refresh_interval
        self.max_workers = max_workers

        # =====================================================
        # INPUT EVENTS
        # =====================================================

        self._queue = queue.Queue()

        self._thread = None
        self._running = False
        self._lock = threading.RLock()

        # =====================================================
        # OLLAMA EXECUTOR
        # =====================================================

        self._executor = None

        # =====================================================
        # LATEST SCHEDULED REFINEMENT PER TURN
        # =====================================================

        self._pending = {}

        # Prevent duplicate refinement scheduling.
        self._scheduled_turns = set()

    # =========================================================
    # START
    # =========================================================

    def start(self):

        with self._lock:

            if self._running:
                return

            self._running = True

            self._executor = ThreadPoolExecutor(
                max_workers=self.max_workers
            )

            self._pending.clear()
            self._scheduled_turns.clear()

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

            item = self._queue.get()

            if item is None:
                break

            turn = item

            # -------------------------------------------------
            # Store the latest state for this turn.
            #
            # If another refinement request for the same turn
            # already exists, the newer state replaces it.
            # -------------------------------------------------

            with self._lock:

                self._pending[
                    turn.id
                ] = turn

                if turn.id in self._scheduled_turns:

                    continue

                self._scheduled_turns.add(
                    turn.id
                )

            # -------------------------------------------------
            # Schedule delayed refinement.
            # -------------------------------------------------

            thread = threading.Thread(
                target=self._delayed_refinement,
                args=(turn.id,),
                daemon=True,
            )

            thread.start()

    # =========================================================
    # DELAYED REFINEMENT
    # =========================================================

    def _delayed_refinement(self, turn_id):

        try:

            # -------------------------------------------------
            # Wait before starting refinement.
            # -------------------------------------------------

            time.sleep(
                self.refresh_interval
            )

            if not self._running:
                return

            # -------------------------------------------------
            # Get latest submitted state for this turn.
            # -------------------------------------------------

            with self._lock:

                turn = self._pending.pop(
                    turn_id,
                    None
                )

                self._scheduled_turns.discard(
                    turn_id
                )

                executor = self._executor

            if turn is None:
                return

            if executor is None:
                return

            # -------------------------------------------------
            # Read CURRENT translation.
            #
            # A newer progressive/final result may have
            # arrived while we were waiting 1.2 seconds.
            # -------------------------------------------------

            current_translation = (
                self.context_manager.get_current_translation(
                    turn.id
                )
            )

            if not current_translation:
                return

            # -------------------------------------------------
            # Get a fresh context snapshot.
            #
            # Exclude the current turn so that the turn being
            # refined is not treated as previous conversation.
            # -------------------------------------------------

            context = (
                self.context_manager.get_context(
                    exclude_turn_id=turn.id
                )
            )

            # -------------------------------------------------
            # Submit actual Ollama work to thread pool.
            # -------------------------------------------------

            executor.submit(
                self._refine,
                turn,
                current_translation,
                context,
            )

        except Exception as exc:

            print(
                f"[RefinementWorker] "
                f"scheduling error: {exc}"
            )

            if self.bridge is not None:

                self.bridge.error(
                    str(exc)
                )

    # =========================================================
    # REFINEMENT REQUEST
    # =========================================================

    def _refine(
        self,
        turn,
        current_translation,
        context,
    ):

        try:

            # -------------------------------------------------
            # Reserve revision immediately before Ollama.
            #
            # This means the refinement becomes the newest
            # requested state for this turn.
            # -------------------------------------------------

            revision = (
                self.context_manager.reserve_revision(
                    turn.id
                )
            )

            if revision is None:
                return

            if self.bridge is not None:

                self.bridge.translation_started()

            refinement_start = (
                time.perf_counter()
            )

            refined_text, api_ms = (
                self.translator.refine(
                    source_text=turn.source_text,
                    current_translation=current_translation,
                    context=context,
                    source_language=turn.source_language,
                    target_language=turn.target_language,
                )
            )

            refinement_end = (
                time.perf_counter()
            )

            total_ms = (
                refinement_end
                - refinement_start
            ) * 1000

            if not refined_text:
                return

            refined_text = (
                refined_text.strip()
            )

            current_translation = (
                current_translation.strip()
            )

            # -------------------------------------------------
            # Nothing actually improved.
            # -------------------------------------------------

            if refined_text == current_translation:

                # The revision was reserved specifically for
                # this refinement request. Restore no state;
                # simply don't update the displayed translation.
                return

            # -------------------------------------------------
            # Apply only if this revision is still current.
            # -------------------------------------------------

            accepted = (
                self.context_manager.apply_translation(
                    turn_id=turn.id,
                    translated_text=refined_text,
                    revision=revision,
                )
            )

            if not accepted:
                return

            # -------------------------------------------------
            # Send accepted refinement to UI.
            # -------------------------------------------------

            if self.bridge is not None:

                self.bridge.translation_refined(
                    text=refined_text,
                    turn_id=turn.id,
                    revision=revision,
                    api_ms=api_ms,
                    total_ms=total_ms,
                )

        except Exception as exc:

            print(
                f"[RefinementWorker] "
                f"translation error: {exc}"
            )

            if self.bridge is not None:

                self.bridge.error(
                    str(exc)
                )

        finally:

            if self.bridge is not None:

                self.bridge.translation_completed()