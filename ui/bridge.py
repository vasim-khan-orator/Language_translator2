import queue


class UIBridge:
    """
    Safely transfers events from translator/background threads
    to the Tkinter UI thread.

    Translation results may arrive out of order because chunk,
    final, and refinement requests can run concurrently.

    The bridge tracks the latest displayed revision for each
    conversation turn and ignores stale results.

    It also tracks the number of active translation requests
    independently from whether a result was accepted or stale.
    """

    def __init__(self, window):

        self.window = window

        self.events = queue.Queue()

        # Latest translation revision displayed for each turn.
        self._latest_revision = {}

        # Number of translation/model requests currently running.
        self._active_translations = 0

    # =========================================================
    # SOURCE EVENTS
    # =========================================================

    def source_partial(self, text):

        self.events.put(
            (
                "source_partial",
                text,
            )
        )

    def source_final(self, text):

        self.events.put(
            (
                "source_final",
                text,
            )
        )

    # =========================================================
    # TRANSLATION START
    # =========================================================

    def translation_started(self):

        self.events.put(
            (
                "translation_started",
                None,
            )
        )

    # =========================================================
    # TRANSLATION COMPLETED
    # =========================================================

    def translation_completed(self):

        """
        Indicates that one translation/model request has
        completely finished.

        This event MUST be sent whether the result was:

            - accepted
            - stale
            - empty
            - unsuccessful
            - rejected by revision logic

        This keeps _active_translations accurate when multiple
        requests are running concurrently.
        """

        self.events.put(
            (
                "translation_completed",
                None,
            )
        )

    # =========================================================
    # PROGRESSIVE CHUNK RESULT
    # =========================================================

    def translation_chunk(
        self,
        text,
        turn_id=None,
        revision=None,
        api_ms=0.0,
        total_ms=0.0,
    ):

        self.events.put(
            (
                "translation_chunk",
                {
                    "text": text,
                    "turn_id": turn_id,
                    "revision": revision,
                    "api_ms": api_ms,
                    "total_ms": total_ms,
                },
            )
        )

    # =========================================================
    # FINAL TRANSLATION RESULT
    # =========================================================

    def translation_final(
        self,
        text,
        turn_id,
        revision=None,
        api_ms=0.0,
        total_ms=0.0,
    ):

        self.events.put(
            (
                "translation_final",
                {
                    "text": text,
                    "turn_id": turn_id,
                    "revision": revision,
                    "api_ms": api_ms,
                    "total_ms": total_ms,
                },
            )
        )

    # =========================================================
    # CONTEXT REFINEMENT RESULT
    # =========================================================

    def translation_refined(
        self,
        text,
        turn_id,
        revision=None,
        api_ms=0.0,
        total_ms=0.0,
    ):

        self.events.put(
            (
                "translation_refined",
                {
                    "text": text,
                    "turn_id": turn_id,
                    "revision": revision,
                    "api_ms": api_ms,
                    "total_ms": total_ms,
                },
            )
        )

    # =========================================================
    # STATUS
    # =========================================================

    def status(self, text):

        self.events.put(
            (
                "status",
                text,
            )
        )

    # =========================================================
    # ERROR
    # =========================================================

    def error(self, text):

        self.events.put(
            (
                "error",
                text,
            )
        )

    # =========================================================
    # CHECK REVISION
    # =========================================================

    def _is_newer_revision(
        self,
        turn_id,
        revision,
    ):
        """
        Return True only when this result is newer than
        the latest result already displayed for this turn.

        Results without revision information are accepted
        for backward compatibility.
        """

        if turn_id is None or revision is None:
            return True

        latest = self._latest_revision.get(
            turn_id,
            -1,
        )

        if revision <= latest:
            return False

        self._latest_revision[
            turn_id
        ] = revision

        return True

    # =========================================================
    # PROCESS EVENTS
    # =========================================================

    def process_events(self):
        """
        Called periodically by Tkinter's main thread.

        Background threads NEVER modify Tkinter widgets directly.
        They only place events in the queue.
        """

        while True:

            try:

                event, data = (
                    self.events.get_nowait()
                )

            except queue.Empty:

                break

            # -------------------------------------------------
            # SOURCE PARTIAL
            # -------------------------------------------------

            if event == "source_partial":

                self.window.set_source_text(
                    data
                )

            # -------------------------------------------------
            # SOURCE FINAL
            # -------------------------------------------------

            elif event == "source_final":

                self.window.set_source_text(
                    data
                )

            # -------------------------------------------------
            # TRANSLATION STARTED
            # -------------------------------------------------

            elif event == "translation_started":

                self._active_translations += 1

                self.window.set_status(
                    "TRANSLATING"
                )

            # -------------------------------------------------
            # TRANSLATION COMPLETED
            # -------------------------------------------------

            elif event == "translation_completed":

                self._translation_finished()

            # -------------------------------------------------
            # PROGRESSIVE CHUNK
            # -------------------------------------------------

            elif event == "translation_chunk":

                turn_id = data["turn_id"]
                revision = data["revision"]

                # Ignore stale result.

                if not self._is_newer_revision(
                    turn_id,
                    revision,
                ):

                    continue

                self.window.set_translation(
                    data["text"]
                )

                self.window.set_metrics(
                    api_ms=data["api_ms"],
                    total_ms=data["total_ms"],
                )

            # -------------------------------------------------
            # FINAL TRANSLATION
            # -------------------------------------------------

            elif event == "translation_final":

                turn_id = data["turn_id"]
                revision = data["revision"]

                # Ignore stale result.

                if not self._is_newer_revision(
                    turn_id,
                    revision,
                ):

                    continue

                self.window.set_translation(
                    data["text"]
                )

                self.window.set_metrics(
                    api_ms=data["api_ms"],
                    total_ms=data["total_ms"],
                )

            # -------------------------------------------------
            # CONTEXT REFINEMENT
            # -------------------------------------------------

            elif event == "translation_refined":

                turn_id = data["turn_id"]
                revision = data["revision"]

                # Ignore stale result.

                if not self._is_newer_revision(
                    turn_id,
                    revision,
                ):

                    continue

                self.window.set_translation(
                    data["text"]
                )

                self.window.set_metrics(
                    api_ms=data["api_ms"],
                    total_ms=data["total_ms"],
                )

            # -------------------------------------------------
            # STATUS
            # -------------------------------------------------

            elif event == "status":

                self.window.set_status(
                    data
                )

            # -------------------------------------------------
            # ERROR
            # -------------------------------------------------

            elif event == "error":

                self.window.set_status(
                    f"ERROR: {data}"
                )

        # Check again after 50 ms.

        self.window.root.after(
            50,
            self.process_events,
        )

    # =========================================================
    # TRANSLATION FINISHED
    # =========================================================

    def _translation_finished(self):

        if self._active_translations > 0:

            self._active_translations -= 1

        if self._active_translations == 0:

            self.window.set_status(
                "LISTENING"
            )

    # =========================================================
    # START
    # =========================================================

    def start(self):

        self.window.root.after(
            50,
            self.process_events,
        )