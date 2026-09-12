import queue


class UIBridge:
    """
    Thread-safe translator -> Tkinter event bridge.

    Translation requests now run in parallel. The translation worker
    commits completed fragments in source sequence order, so this
    bridge receives an already ordered aggregate translation even when
    the underlying Ollama requests finish out of order.
    """

    def __init__(self, window):

        self.window = window
        self.events = queue.Queue()

        self._latest_revision = {}

        # Once an authoritative final translation is accepted for a turn,
        # late provisional chunk results must never overwrite it.
        self._finalized_turns = set()

        # Per-turn provisional chunk slots. A missing response is represented
        # by an empty string; later responses fill that exact slot without
        # waiting for earlier requests.
        self._chunk_slots = {}
        self._chunk_cutoff = {}
        self._incremental_base = {}

        self._active_translations = 0

        # Tkinter should stay responsive even when several workers
        # finish close together.
        self._max_events_per_tick = 100

        # Used by the UI to keep language selectors in sync.
        self.source_language = "en-US"
        self.target_language = "hi-IN"

    # =========================================================
    # SOURCE EVENTS
    # =========================================================

    def source_partial(
        self,
        text,
        turn_id=None,
    ):

        self.events.put(
            (
                "source_partial",
                {
                    "text": text,
                    "turn_id": turn_id,
                },
            )
        )

    def source_final(
        self,
        text,
        turn_id=None,
    ):

        self.events.put(
            (
                "source_final",
                {
                    "text": text,
                    "turn_id": turn_id,
                },
            )
        )

    # =========================================================
    # TRANSLATION START / COMPLETE
    # =========================================================

    def translation_started(self):

        self.events.put(
            (
                "translation_started",
                None,
            )
        )

    def translation_completed(self):

        self.events.put(
            (
                "translation_completed",
                None,
            )
        )

    # =========================================================
    # TRANSLATION RESULTS
    # =========================================================

    def translation_chunk(
        self,
        text,
        turn_id=None,
        sequence=None,
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
                    "sequence": sequence,
                    "revision": revision,
                    "api_ms": api_ms,
                    "total_ms": total_ms,
                },
            )
        )

    def translation_incremental(
        self,
        text,
        turn_id,
        revision=None,
        api_ms=0.0,
        total_ms=0.0,
        final=False,
        chunk_cutoff=-1,
    ):
        """
        Deliver an already ordered parallel-fragment result.

        The worker owns fragment ordering, therefore same-turn
        translations can arrive here only in committed source order.
        """

        self.events.put(
            (
                "translation_incremental",
                {
                    "text": text,
                    "turn_id": turn_id,
                    "revision": revision,
                    "api_ms": api_ms,
                    "total_ms": total_ms,
                    "final": final,
                    "chunk_cutoff": chunk_cutoff,
                },
            )
        )

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
    # STATUS / ERROR
    # =========================================================

    def status(self, text):
        self.events.put(
            (
                "status",
                text,
            )
        )

    def error(self, text):
        self.events.put(
            (
                "error",
                text,
            )
        )

    # =========================================================
    # REVISION GUARD
    # =========================================================

    def _is_newer_revision(
        self,
        turn_id,
        revision,
    ):

        if turn_id is None or revision is None:
            return True

        latest = self._latest_revision.get(
            turn_id,
            -1,
        )

        if revision <= latest:
            return False

        self._latest_revision[turn_id] = revision

        return True

    def _is_incremental_revision_valid(
        self,
        turn_id,
        revision,
    ):

        if turn_id is None or revision is None:
            return True

        latest = self._latest_revision.get(
            turn_id,
            -1,
        )

        if revision < latest:
            return False

        self._latest_revision[turn_id] = revision

        return True

    def clear_turn_revision(
        self,
        turn_id,
    ):

        if turn_id is not None:

            self._latest_revision.pop(
                turn_id,
                None,
            )
            self._finalized_turns.discard(turn_id)

    # =========================================================
    # EVENT PROCESSOR
    # =========================================================

    def process_events(self):

        processed = 0

        while processed < self._max_events_per_tick:

            try:

                event, data = (
                    self.events.get_nowait()
                )

            except queue.Empty:

                break

            processed += 1

            if event == "source_partial":

                self.window.set_source_text(
                    data["text"],
                    turn_id=data["turn_id"],
                    final=False,
                )

            elif event == "source_final":

                self.window.set_source_text(
                    data["text"],
                    turn_id=data["turn_id"],
                    final=True,
                )

                self.window.complete_turn(
                    data["turn_id"]
                )

            elif event == "translation_started":

                self._active_translations += 1

                self.window.set_status(
                    "TRANSLATING"
                )

            elif event == "translation_completed":

                self._translation_finished()

            elif event == "translation_incremental":

                turn_id = data["turn_id"]
                revision = data["revision"]

                if turn_id in self._finalized_turns:
                    continue

                if not self._is_incremental_revision_valid(
                    turn_id,
                    revision,
                ):
                    continue

                cutoff = int(data.get("chunk_cutoff", -1))
                self._chunk_cutoff[turn_id] = cutoff
                self._incremental_base[turn_id] = (data.get("text") or "").strip()

                slots = self._chunk_slots.get(turn_id)
                if slots is not None:
                    for seq in list(slots):
                        if seq <= cutoff:
                            slots.pop(seq, None)

                # This is the coherent incremental snapshot: replace the
                # entire visible line, then allow only newer chunk slots to
                # appear after it.
                self.window.update_turn_translation(
                    data["text"],
                    turn_id=turn_id,
                )

                self.window.set_metrics(
                    api_ms=data["api_ms"],
                    total_ms=data["total_ms"],
                )

            elif event == "translation_chunk":

                turn_id = data["turn_id"]
                sequence = data.get("sequence")

                if turn_id in self._finalized_turns:
                    continue

                if sequence is None:
                    continue

                sequence = int(sequence)
                cutoff = self._chunk_cutoff.get(turn_id, -1)

                # An incremental snapshot already contains this chunk.
                if sequence <= cutoff:
                    continue

                slots = self._chunk_slots.setdefault(turn_id, {})
                slots[sequence] = (data.get("text") or "").strip()

                max_sequence = max(slots) if slots else sequence
                rendered_slots = [
                    slots.get(index, " ")
                    for index in range(cutoff + 1, max_sequence + 1)
                ]

                # The bridge intentionally keeps a real gap for unfinished
                # requests. A later API response fills that slot.
                chunk_tail = " ".join(rendered_slots).rstrip()

                # Preserve the current incremental snapshot, if any.
                # When no snapshot exists, render from the beginning.
                # We cannot recover an earlier snapshot text from the event
                # itself, so before the first incremental response chunk
                # text is simply rendered from chunk slots.
                base_text = getattr(self, "_incremental_base", {}).get(
                    turn_id, ""
                ) if hasattr(self, "_incremental_base") else ""

                rendered = (
                    f"{base_text} {chunk_tail}".strip()
                    if base_text
                    else chunk_tail
                )

                self.window.update_turn_translation(
                    rendered,
                    turn_id=turn_id,
                )

                self.window.set_metrics(
                    api_ms=data["api_ms"],
                    total_ms=data["total_ms"],
                )

            elif event == "translation_final":

                turn_id = data["turn_id"]
                revision = data["revision"]

                if not self._is_newer_revision(
                    turn_id,
                    revision,
                ):
                    continue

                # Mark authoritative final BEFORE updating the window so
                # any subsequently queued chunk is ignored.
                self._finalized_turns.add(turn_id)
                self._chunk_slots.pop(turn_id, None)
                self._chunk_cutoff.pop(turn_id, None)
                self._incremental_base.pop(turn_id, None)

                self.window.update_turn_translation(
                    data["text"],
                    turn_id=turn_id,
                )

                self.window.set_metrics(
                    api_ms=data["api_ms"],
                    total_ms=data["total_ms"],
                )

            elif event == "translation_refined":

                turn_id = data["turn_id"]
                revision = data["revision"]

                # Refinement is still allowed only before the final.
                if turn_id in self._finalized_turns:
                    continue

                if not self._is_newer_revision(
                    turn_id,
                    revision,
                ):
                    continue

                self.window.update_turn_translation(
                    data["text"],
                    turn_id=turn_id,
                )

                self.window.set_metrics(
                    api_ms=data["api_ms"],
                    total_ms=data["total_ms"],
                )

            elif event == "status":

                self.window.set_status(
                    data
                )

            elif event == "error":

                self.window.set_status(
                    f"ERROR: {data}"
                )

        self.window.root.after(
            20,
            self.process_events,
        )

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
            20,
            self.process_events,
        )
