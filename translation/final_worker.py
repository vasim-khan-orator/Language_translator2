import json
import queue
import threading
import time

import requests
from concurrent.futures import ThreadPoolExecutor

from config import OLLAMA_URL, OLLAMA_MODEL


class FinalTranslationWorker:
    """
    Single-flight real-time translation worker.

    Live mode:
        - receives the newest ASR snapshot
        - extracts only the newly added source suffix
        - ignores ASR rewrites until the text becomes an extension again
        - translates the small suffix
        - streams that suffix into the same UI turn

    Final mode:
        - sends the complete finalized utterance once
        - final work has priority over pending live work
        - the final result becomes authoritative
    """

    def __init__(
        self,
        translator=None,
        conversation=None,
        bridge=None,
        max_workers=1,
        incremental_interval=0.15,
        min_fragment_words=2,
    ):
        # Kept for constructor compatibility, but the final worker
        # now owns its own direct Ollama HTTP path.
        self.translator = translator
        self.conversation = conversation
        self.bridge = bridge

        self.ollama_url = OLLAMA_URL.rstrip("/")
        self.ollama_model = OLLAMA_MODEL
        self.keep_alive = "30m"
        self.temperature = 0.0
        self.final_num_predict = 128
        self.incremental_num_predict = 40
        self._http_local = threading.local()

        self.max_workers = 1
        self.incremental_interval = max(
            0.05,
            float(incremental_interval),
        )
        self.min_fragment_words = max(
            1,
            int(min_fragment_words),
        )

        self._thread = None
        self._final_executor = None
        self._running = False
        self._stop_event = threading.Event()
        self._condition = threading.Condition()

        # Once finalization is requested for a turn, its live incremental
        # results are backend-only and can no longer update the turn.
        self._final_requested = set()

        # turn_id -> {"source_text": str, "final": bool}
        self._pending = {}

        # Source suffix already sent successfully to live translation.
        self._translated_source = {}

        # Accumulated live translation displayed for each turn.
        self._live_translation = {}

        self._last_request_time = 0.0

    # =========================================================
    # START
    # =========================================================

    def start(self):
        with self._condition:
            if self._running:
                return

            self._running = True
            self._stop_event.clear()
            self._pending.clear()
            self._translated_source.clear()
            self._live_translation.clear()
            self._final_requested.clear()

            self._final_executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="final",
            )

            self._thread = threading.Thread(
                target=self._run,
                daemon=True,
            )
            self._thread.start()

    # =========================================================
    # LIVE SUBMIT
    # =========================================================

    def submit_incremental(self, turn_id, source_text, chunk_cutoff=-1):
        source_text = (source_text or "").strip()

        if turn_id is None or not source_text:
            return

        with self._condition:
            if not self._running:
                return

            pending = self._pending.get(turn_id)

            if pending is not None and pending["final"]:
                return

            self._pending[turn_id] = {
                "source_text": source_text,
                "final": False,
                "chunk_cutoff": int(chunk_cutoff),
            }
            self._condition.notify()

    # =========================================================
    # FINAL SUBMIT
    # =========================================================

    def submit_final(self, turn):
        if turn is None:
            return

        source_text = (turn.source_text or "").strip()

        if not source_text:
            return

        with self._condition:
            if not self._running:
                return

            # Only one authoritative final request per turn.
            if turn.id in self._final_requested:
                return

            self._final_requested.add(turn.id)
            self._pending.pop(turn.id, None)

            executor = self._final_executor

        if executor is None:
            return

        # IMPORTANT:
        # This is a separate executor from the live incremental loop.
        # Therefore a slow live incremental request cannot delay the final
        # full-sentence request.
        executor.submit(
            self._translate_final,
            turn.id,
            source_text,
        )

    def submit(self, turn):
        self.submit_final(turn)

    # =========================================================
    # STOP
    # =========================================================

    def stop(self):
        with self._condition:
            if not self._running:
                return

            self._running = False
            self._stop_event.set()
            self._pending.clear()
            self._condition.notify_all()

            thread = self._thread
            self._thread = None

        if thread is not None:
            thread.join(timeout=2)

        with self._condition:
            final_executor = self._final_executor
            self._final_executor = None
            self._final_requested.clear()

        if final_executor is not None:
            final_executor.shutdown(
                wait=False,
                cancel_futures=True,
            )

    # =========================================================
    # PICK NEXT
    # =========================================================

    def _next_item(self):
        with self._condition:
            while self._running and not self._pending:
                self._condition.wait(timeout=0.10)

            if not self._running:
                return None

            selected_turn_id = None
            selected = None

            # Final requests always win.
            for turn_id, candidate in self._pending.items():
                if candidate["final"]:
                    selected_turn_id = turn_id
                    selected = candidate
                    break

            if selected_turn_id is None:
                selected_turn_id, selected = next(
                    iter(self._pending.items())
                )

            self._pending.pop(selected_turn_id, None)

            if not selected["final"]:
                wait_for = (
                    self.incremental_interval
                    - (
                        time.monotonic()
                        - self._last_request_time
                    )
                )

                if wait_for > 0:
                    self._pending[selected_turn_id] = selected
                    self._condition.wait(timeout=wait_for)
                    return "__RETRY__"

            return (
                selected_turn_id,
                selected["source_text"],
                selected["final"],
                int(selected.get("chunk_cutoff", -1)),
            )

    # =========================================================
    # WORKER LOOP
    # =========================================================

    def _run(self):
        while not self._stop_event.is_set():
            item = self._next_item()

            if item is None:
                return

            if item == "__RETRY__":
                continue

            turn_id, source_text, is_final, chunk_cutoff = item

            if is_final:
                self._translate_final(turn_id, source_text)
            else:
                self._translate_incremental(
                    turn_id,
                    source_text,
                    chunk_cutoff=chunk_cutoff,
                )

    # =========================================================
    # GET NEW SUFFIX
    # =========================================================

    @staticmethod
    def _word_count(text):
        return len(text.split())

    def _get_new_suffix(self, turn_id, source_text):
        previous = self._translated_source.get(
            turn_id,
            "",
        )

        if not previous:
            return source_text

        # Normal ASR growth: translate only newly added words.
        if source_text.startswith(previous):
            return source_text[len(previous):].strip()

        # ASR revised earlier words. Do not translate unstable text.
        return ""

    # =========================================================
    # INCREMENTAL TRANSLATION
    # =========================================================

    def _translate_incremental(
        self,
        turn_id,
        source_text,
        chunk_cutoff=-1,
    ):
        try:
            with self._condition:
                if turn_id in self._final_requested:
                    return

            turn = self.conversation.get_turn(turn_id)

            if turn is None:
                return

            fragment = self._get_new_suffix(
                turn_id,
                source_text,
            )

            if not fragment:
                return

            # Avoid firing an LLM request for tiny one-word changes.
            # The next ASR update can extend this fragment.
            if self._word_count(fragment) < self.min_fragment_words:
                with self._condition:
                    pending = self._pending.get(turn_id)

                    if pending is None or not pending["final"]:
                        self._pending[turn_id] = {
                            "source_text": source_text,
                            "final": False,
                            "chunk_cutoff": int(chunk_cutoff),
                        }
                return

            revision = self.conversation.reserve_revision(
                turn_id
            )

            if revision is None:
                return

            if self.bridge is not None:
                self.bridge.translation_started()

            request_start = time.perf_counter()
            translated_fragment, api_ms = (
                self._translate_incremental_direct(
                    fragment=fragment,
                    source_language=turn.source_language,
                    target_language=turn.target_language,
                )
            )

            total_ms = (
                time.perf_counter()
                - request_start
            ) * 1000

            translated_fragment = (
                translated_fragment or ""
            ).strip()

            if not translated_fragment:
                return

            # A final request may have been submitted while this live
            # request was inside Ollama. Never let this late response
            # overwrite the authoritative final result.
            with self._condition:
                if turn_id in self._final_requested:
                    return

            with self._condition:
                previous_translation = self._live_translation.get(
                    turn_id,
                    "",
                )

            combined_translation = (
                f"{previous_translation} {translated_fragment}"
            ).strip()

            accepted = self.conversation.apply_translation(
                turn_id=turn_id,
                translated_text=combined_translation,
                revision=revision,
            )

            if not accepted:
                return

            with self._condition:
                # Commit the source suffix only after a completed
                # translation response was accepted.
                self._translated_source[turn_id] = source_text
                self._live_translation[turn_id] = combined_translation

            # Replace the entire currently rendered chunk line with the
            # coherent incremental snapshot. The bridge remembers that
            # this snapshot covers all chunks through chunk_cutoff and
            # will only display newer chunk slots after it.
            if self.bridge is not None:
                self.bridge.translation_incremental(
                    text=combined_translation,
                    turn_id=turn_id,
                    revision=revision,
                    api_ms=api_ms,
                    total_ms=total_ms,
                    final=False,
                    chunk_cutoff=chunk_cutoff,
                )

        except Exception as exc:
            print(
                f"[FinalTranslationWorker] "
                f"incremental: {exc}"
            )

            if self.bridge is not None:
                self.bridge.error(str(exc))

        finally:
            if self.bridge is not None:
                self.bridge.translation_completed()

            self._last_request_time = time.monotonic()

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

    def _post_streaming_translation(
        self,
        prompt,
        num_predict,
    ):
        """
        FinalTranslationWorker's own Ollama HTTP sender.

        The worker owns this request directly; ChunkWorker has a
        separate sender and separate HTTP thread-local session.
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
                    "num_predict": num_predict,
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
                "[FinalWorker API] "
                f"HTTP={api_ms:.0f} ms"
            )

            return text, api_ms

        finally:
            response.close()

    def _translate_incremental_direct(
        self,
        fragment,
        source_language,
        target_language,
    ):
        fragment = (fragment or "").strip()

        if not fragment:
            return "", 0.0

        prompt = f"""Translate {source_language} to {target_language}.
Return ONLY the translation.
Translate only the newly provided text.
Do not complete, explain, answer, or add words.

Text:
{fragment}

Translation:
"""

        return self._post_streaming_translation(
            prompt,
            self.incremental_num_predict,
        )

    def _translate_final_direct(
        self,
        source_text,
        source_language,
        target_language,
    ):
        source_text = (source_text or "").strip()

        if not source_text:
            return "", 0.0

        prompt = f"""You are a professional translator.

Translate the complete speech below from
{source_language} to {target_language}.

Rules:
- Return ONLY the translation.
- Do not explain anything.
- Do not add comments.
- Do not repeat the original text.
- Preserve the exact meaning.
- Preserve names.
- Preserve numbers.
- Preserve technical terms when appropriate.
- Preserve the speaker's tone and intent.
- Produce natural, grammatically correct translation.

Source:
{source_text}

Translation:
"""

        return self._post_streaming_translation(
            prompt,
            self.final_num_predict,
        )

    # =========================================================
    # FINAL TRANSLATION
    # =========================================================

    def _translate_final(
        self,
        turn_id,
        source_text,
    ):
        try:
            turn = self.conversation.get_turn(turn_id)

            if turn is None:
                return

            revision = self.conversation.reserve_revision(
                turn_id
            )

            if revision is None:
                return

            if self.bridge is not None:
                self.bridge.translation_started()

            started = time.perf_counter()

            translated_text, api_ms = (
                self._translate_final_direct(
                    source_text=source_text,
                    source_language=turn.source_language,
                    target_language=turn.target_language,
                )
            )

            total_ms = (
                time.perf_counter()
                - started
            ) * 1000

            translated_text = (
                translated_text or ""
            ).strip()

            if not translated_text:
                return

            accepted = self.conversation.apply_translation(
                turn_id=turn_id,
                translated_text=translated_text,
                revision=revision,
            )

            if not accepted:
                return

            with self._condition:
                self._translated_source[turn_id] = source_text
                self._live_translation[turn_id] = translated_text

            if self.bridge is not None:
                self.bridge.translation_final(
                    text=translated_text,
                    turn_id=turn_id,
                    revision=revision,
                    api_ms=api_ms,
                    total_ms=total_ms,
                )

        except Exception as exc:
            print(
                f"[FinalTranslationWorker] "
                f"final: {exc}"
            )

            if self.bridge is not None:
                self.bridge.error(str(exc))

        finally:
            if self.bridge is not None:
                self.bridge.translation_completed()

            self._last_request_time = time.monotonic()

            # Release per-turn live state after the final result.
            with self._condition:
                self._translated_source.pop(
                    turn_id,
                    None,
                )
                self._live_translation.pop(
                    turn_id,
                    None,
                )