import json
import queue
import threading
import time

import requests

from config import OLLAMA_URL, OLLAMA_MODEL


class ChunkWorker:
    """
    Hidden background chunk prefetch worker.

    A stable Riva FINAL segment is fed into a small word buffer.
    Whenever the buffer contains enough words, one small chunk is
    removed from the buffer and dispatched immediately on its own
    background request thread.

    There is intentionally NO shared worker-pool queue between chunks.
    Chunk N+1 never waits for Chunk N in Python.

    Example with chunk_words=3:

        Riva FINAL: "I went to the"
                       ↓
        request 0:   "I went to"
        buffer:      "the"

    A later stable segment extends the buffer and another chunk is
    dispatched.

    Important finalization behavior:

        live chunk(s) may still be running
                    ↓
        utterance ends
                    ↓
        finalize_turn()
                    ↓
        already-running chunk requests are allowed to finish
                    ↓
        their responses fill their reserved UI slots
                    ↓
        FinalTranslationWorker starts immediately

    We intentionally do NOT wait for the last chunk.
    """

    def __init__(
        self,
        translator=None,
        conversation=None,
        bridge=None,
        max_workers=3,
        chunk_words=3,
    ):

        # Kept for constructor compatibility, but this worker does
        # NOT use the shared OllamaTranslator anymore.
        self.translator = translator
        self.conversation = conversation
        self.bridge = bridge

        self.ollama_url = OLLAMA_URL.rstrip("/")
        self.ollama_model = OLLAMA_MODEL
        self.keep_alive = "30m"
        self.temperature = 0.0
        self.num_predict = 40

        # One HTTP session per worker thread.
        self._http_local = threading.local()

        self.max_workers = max(
            1,
            int(max_workers),
        )

        self.chunk_words = max(
            1,
            int(chunk_words),
        )

        # Each chunk gets its own request thread. This removes the
        # Python-side max_workers bottleneck completely.
        self._chunk_threads = set()

        self._running = False
        self._lock = threading.RLock()

        # turn_id -> state
        #
        # {
        #     "generation": int,
        #     "buffer": [words],
        #     "next_sequence": int,
        #     "completed": {sequence: result},
        #     "finalized": bool,
        # }
        self._turns = {}

    # =========================================================
    # START
    # =========================================================

    def start(self):

        with self._lock:

            if self._running:
                return

            self._running = True

            self._chunk_threads.clear()
            self._turns.clear()

    # =========================================================
    # SUBMIT NEW STABLE SEGMENT
    # =========================================================

    def submit(
        self,
        text,
        source_language,
        target_language,
        turn_id,
    ):

        text = (text or "").strip()

        if not text or turn_id is None:
            return

        with self._lock:

            if not self._running:
                return

            state = self._turns.setdefault(
                turn_id,
                self._new_state(),
            )

            # A finalized turn must never accept another chunk.
            if state["finalized"]:
                return

            # Add ONLY the newly stable segment.
            state["buffer"].extend(
                text.split()
            )

            # Dispatch every complete chunk immediately.
            while len(state["buffer"]) >= self.chunk_words:

                words = state["buffer"][
                    :self.chunk_words
                ]

                del state["buffer"][
                    :self.chunk_words
                ]

                fragment = " ".join(words).strip()

                if not fragment:
                    continue

                self._dispatch_locked(
                    turn_id=turn_id,
                    state=state,
                    fragment=fragment,
                    source_language=source_language,
                    target_language=target_language,
                )

    # =========================================================
    # FINALIZE TURN
    # =========================================================

    def finalize_turn(
        self,
        turn_id,
    ):

        if turn_id is None:
            return

        with self._lock:

            state = self._turns.get(
                turn_id
            )

            if state is None:
                return

            if state["finalized"]:
                return

            # Mark the turn closed for NEW chunk submissions.
            #
            # IMPORTANT:
            # We do NOT invalidate already-running chunk requests here.
            # They are allowed to finish and reach the UI. The final
            # translation is authoritative and the UIBridge will ignore
            # any chunk event that arrives after the final event.
            state["finalized"] = True

            # The incomplete tail is provisional. Do not dispatch it now;
            # the FinalTranslationWorker will translate the complete
            # sentence.
            state["buffer"].clear()

    # =========================================================
    # RESET TURN
    # =========================================================

    def reset_turn(
        self,
        turn_id=None,
    ):

        with self._lock:

            if turn_id is None:
                self._turns.clear()
                return

            self._turns.pop(
                turn_id,
                None,
            )

    # =========================================================
    # STOP
    # =========================================================

    def stop(self):

        with self._lock:

            if not self._running:
                return

            self._running = False

            # Invalidate every active generation.
            for state in self._turns.values():
                state["generation"] += 1
                state["finalized"] = True
                state["buffer"].clear()

            # Existing per-chunk request threads are daemon threads.
            # Do not wait for them here. They will finish naturally and
            # their stale generation will prevent any post-stop UI update.
            self._turns.clear()
            self._chunk_threads.clear()

    # =========================================================
    # STATE FACTORY
    # =========================================================

    @staticmethod
    def _new_state():

        return {
            "generation": 0,
            "buffer": [],
            "next_sequence": 0,
            "completed": {},
            "finalized": False,
        }

    # =========================================================
    # DISPATCH
    # =========================================================

    def _dispatch_locked(
        self,
        turn_id,
        state,
        fragment,
        source_language,
        target_language,
    ):

        if not self._running:
            return

        sequence = state["next_sequence"]
        state["next_sequence"] += 1
        generation = state["generation"]

        # IMPORTANT:
        # Start this chunk immediately on its own thread.
        # There is NO waiting for another chunk to finish.
        worker_thread = threading.Thread(
            target=self._run_chunk_request,
            args=(
                turn_id,
                generation,
                sequence,
                fragment,
                source_language,
                target_language,
            ),
            daemon=True,
            name=f"chunk-{turn_id}-{sequence}",
        )

        self._chunk_threads.add(worker_thread)
        worker_thread.start()

        print(
            "[ChunkWorker] "
            f"dispatch turn={turn_id} "
            f"chunk={sequence} "
            f"generation={generation} "
            f"text={fragment!r}"
        )

    # =========================================================
    # RUN ONE CHUNK REQUEST
    # =========================================================

    def _run_chunk_request(
        self,
        turn_id,
        generation,
        sequence,
        fragment,
        source_language,
        target_language,
    ):
        current_thread = threading.current_thread()

        try:
            result = self._translate(
                turn_id=turn_id,
                generation=generation,
                sequence=sequence,
                fragment=fragment,
                source_language=source_language,
                target_language=target_language,
            )
        except Exception as exc:
            result = {
                "turn_id": turn_id,
                "generation": generation,
                "sequence": sequence,
                "fragment": fragment,
                "translation": "",
                "api_ms": 0.0,
                "error": str(exc),
            }

        self._finished(
            turn_id,
            generation,
            sequence,
            result,
        )

        with self._lock:
            self._chunk_threads.discard(current_thread)

    # =========================================================
    # TRANSLATE
    # =========================================================

    def _translate(
        self,
        turn_id,
        generation,
        sequence,
        fragment,
        source_language,
        target_language,
    ):
        """
        Perform one hidden chunk translation.

        The returned translation is deliberately kept inside the
        worker. It is NOT sent to the UI and does NOT update the
        ConversationManager. This prevents the hidden prefetch work
        from stealing translation revisions from FinalTranslationWorker.
        """

        try:

            translated_text, api_ms = self._translate_direct(
                fragment=fragment,
                source_language=source_language,
                target_language=target_language,
            )

            return {
                "turn_id": turn_id,
                "generation": generation,
                "sequence": sequence,
                "fragment": fragment,
                "translation": (
                    translated_text or ""
                ).strip(),
                "api_ms": api_ms,
                "error": None,
            }

        except Exception as exc:

            return {
                "turn_id": turn_id,
                "generation": generation,
                "sequence": sequence,
                "fragment": fragment,
                "translation": "",
                "api_ms": 0.0,
                "error": str(exc),
            }

    # =========================================================
    # DIRECT OLLAMA API
    # =========================================================

    def _get_http_session(self):
        session = getattr(
            self._http_local,
            "session",
            None,
        )

        if session is None:
            session = requests.Session()
            self._http_local.session = session

        return session

    def _translate_direct(
        self,
        fragment,
        source_language,
        target_language,
    ):
        """
        Send the hidden chunk directly to Ollama.

        This request path belongs exclusively to ChunkWorker.
        It does not call OllamaTranslator.
        """

        fragment = (fragment or "").strip()

        if not fragment:
            return "", 0.0

        prompt = f"""Translate {source_language} to {target_language}.
Return ONLY the translation of the text below.
Translate only what is provided.
Do not complete the sentence.
Do not explain, answer, or add words.

Text:
{fragment}

Translation:
"""

        started = time.perf_counter()

        response = self._get_http_session().post(
            f"{self.ollama_url}/api/generate",
            json={
                "model": self.ollama_model,
                "prompt": prompt,
                "stream": True,
                "keep_alive": self.keep_alive,
                "options": {
                    "temperature": self.temperature,
                    "num_predict": self.num_predict,
                },
            },
            timeout=60,
            stream=True,
        )

        try:
            response.raise_for_status()

            parts = []

            for raw_line in response.iter_lines(
                decode_unicode=True
            ):
                if not raw_line:
                    continue

                try:
                    data = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue

                piece = data.get("response", "")

                if piece:
                    parts.append(piece)

                if data.get("done"):
                    break

            text = "".join(parts).strip()

            api_ms = (
                time.perf_counter() - started
            ) * 1000

            print(
                "[ChunkWorker API] "
                f"turn-independent chunk request "
                f"HTTP={api_ms:.0f} ms"
            )

            return text, api_ms

        finally:
            response.close()

    # =========================================================
    # RESULT CALLBACK
    # =========================================================

    def _finished(
        self,
        turn_id,
        generation,
        sequence,
        result,
    ):

        with self._lock:

            if not self._running:
                return

            state = self._turns.get(turn_id)

            if state is None:
                return

            if state["generation"] != generation:
                print(
                    "[ChunkWorker] "
                    f"discard stale chunk={sequence} "
                    f"turn={turn_id}"
                )
                return

            # IMPORTANT:
            # Do NOT wait for earlier chunks here.
            # Every completed API request gets its own sequence slot.
            state["completed"][sequence] = result

            visible = result.get("translation") or ""
            api_ms = result.get("api_ms", 0.0)

        # The UI bridge owns the slots/order. This callback returns
        # immediately for each finished request; chunk 4 can appear
        # even when chunk 0 is still running.
        if self.bridge is not None:
            self.bridge.translation_chunk(
                text=visible.strip(),
                turn_id=turn_id,
                sequence=sequence,
                api_ms=api_ms,
                total_ms=api_ms,
            )

        if visible.strip():
            print(
                "[ChunkWorker] "
                f"visible chunk={sequence} "
                f"turn={turn_id} "
                f"text={visible.strip()!r}"
            )

        if result.get("error"):
            print(
                "[ChunkWorker] "
                f"chunk={sequence} "
                f"turn={turn_id} "
                f"error={result['error']}"
            )

    # =========================================================
    # SEQUENCE / SLOT INFO
    # =========================================================

    def get_dispatched_count(self, turn_id):
        """Return the highest chunk sequence dispatched for this turn."""
        with self._lock:
            state = self._turns.get(turn_id)
            if state is None:
                return -1
            return state["next_sequence"] - 1
