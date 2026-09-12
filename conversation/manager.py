from typing import List, Optional
import threading

from conversation.models import ConversationTurn

from config import MAX_HISTORY_LINES


class ConversationManager:
    """
    Thread-safe conversation state manager.

    Responsibilities:
        - Store conversation turns.
        - Generate unique turn IDs.
        - Track the latest translation revision for each turn.
        - Prevent stale asynchronous translation results from
          overwriting newer results.
        - Provide a stable conversation-context snapshot.
    """

    def __init__(
        self,
        source_language: str,
        target_language: str,
    ):
        self.source_language = source_language
        self.target_language = target_language

        self.history: List[ConversationTurn] = []

        # O(1) turn lookup for concurrent workers.
        # The ConversationTurn objects remain the same objects stored in
        # ``history`` so existing callers keep their current behavior.
        self._turns_by_id = {}

        self._next_id = 1

        # Multiple workers can access the conversation simultaneously.
        self._lock = threading.RLock()

    # =========================================================
    # ADD TURN
    # =========================================================

    def add_turn(
        self,
        source_text: str,
    ) -> Optional[ConversationTurn]:
        """
        Create and store a new completed conversation turn.
        """

        source_text = source_text.strip()

        if not source_text:
            return None

        with self._lock:

            turn = ConversationTurn(
                id=self._next_id,
                source_language=self.source_language,
                target_language=self.target_language,
                source_text=source_text,
            )

            self.history.append(turn)
            self._turns_by_id[turn.id] = turn

            self._next_id += 1

            return turn

    # =========================================================
    # GET HISTORY
    # =========================================================

    def get_history(self) -> List[ConversationTurn]:
        """
        Return a snapshot of the conversation history.

        The list itself is copied so another thread cannot
        modify the manager's list structure while it is being used.
        """

        with self._lock:

            return list(self.history)

    # =========================================================
    # GET TURN
    # =========================================================

    def get_turn(
        self,
        turn_id: int,
    ) -> Optional[ConversationTurn]:
        """
        Find a conversation turn by ID.
        """

        with self._lock:
            return self._turns_by_id.get(turn_id)

    # =========================================================
    # UPDATE SOURCE TEXT
    # =========================================================

    def update_source_text(
        self,
        turn_id: int,
        source_text: str,
    ) -> bool:
        """
        Update the source text of an active conversation turn.

        During streaming speech, the same turn is updated as newer ASR
        snapshots arrive.
        """

        source_text = source_text.strip()

        if not source_text:
            return False

        with self._lock:

            turn = self._find_turn_unlocked(turn_id)

            if turn is None:
                return False

            turn.source_text = source_text

            return True

    # =========================================================
    # RESERVE REVISION
    # =========================================================

    def reserve_revision(
        self,
        turn_id: int,
    ) -> Optional[int]:
        """
        Reserve a new translation revision for a turn.

        Every asynchronous translation request should reserve
        a revision before sending its request to Ollama.

        Example:

            chunk request  -> revision 1
            newer chunk    -> revision 2
            final request  -> revision 3
            refinement     -> revision 4

        If responses arrive out of order, only the latest
        reserved revision is allowed to update the turn.
        """

        with self._lock:

            turn = self._find_turn_unlocked(turn_id)

            if turn is None:
                return None

            turn.revision += 1

            return turn.revision

    # =========================================================
    # APPLY TRANSLATION RESULT
    # =========================================================

    def apply_translation(
        self,
        turn_id: int,
        translated_text: str,
        revision: int,
    ) -> bool:
        """
        Apply a translation only when its revision is still
        the latest revision for the turn.

        Returns:
            True  -> result accepted
            False -> result was stale or turn does not exist
        """

        translated_text = translated_text.strip()

        if not translated_text:
            return False

        with self._lock:

            turn = self._find_turn_unlocked(turn_id)

            if turn is None:
                return False

            # A newer request has already been reserved.
            # Therefore this response is stale.
            if revision != turn.revision:
                return False

            turn.translated_text = translated_text

            return True

    # =========================================================
    # BACKWARD-COMPATIBLE TRANSLATION UPDATE
    # =========================================================

    def update_translation(
        self,
        turn_id: int,
        translated_text: str,
    ) -> bool:
        """
        Backward-compatible synchronous translation update.

        This method reserves a new revision and immediately
        applies the result.

        New asynchronous workers should use:

            reserve_revision()
            ...
            apply_translation()
        """

        revision = self.reserve_revision(turn_id)

        if revision is None:
            return False

        return self.apply_translation(
            turn_id=turn_id,
            translated_text=translated_text,
            revision=revision,
        )

    # =========================================================
    # GET CURRENT TRANSLATION
    # =========================================================

    def get_current_translation(
        self,
        turn_id: int,
    ) -> Optional[str]:
        """
        Return the latest accepted translation for a turn.
        """

        with self._lock:

            turn = self._find_turn_unlocked(turn_id)

            if turn is None:
                return None

            return turn.translated_text

    # =========================================================
    # GET CURRENT REVISION
    # =========================================================

    def get_revision(
        self,
        turn_id: int,
    ) -> Optional[int]:
        """
        Return the latest reserved revision for a turn.
        """

        with self._lock:

            turn = self._find_turn_unlocked(turn_id)

            if turn is None:
                return None

            return turn.revision

    # =========================================================
    # GET CONVERSATION CONTEXT
    # =========================================================

    def get_context(
        self,
        exclude_turn_id: Optional[int] = None,
        max_lines: Optional[int] = None,
    ) -> str:
        """
        Build a stable text snapshot of recent conversation context.

        This method does NOT call Ollama.

        It only prepares context for RefinementWorker. The returned
        context is bounded by ``MAX_HISTORY_LINES`` so this method
        does not grow with the full lifetime of the application.
        """

        if max_lines is None:
            max_lines = MAX_HISTORY_LINES

        with self._lock:

            turns = []

            for turn in reversed(self.history):

                if (
                    exclude_turn_id is not None
                    and turn.id == exclude_turn_id
                ):
                    continue

                # Only use turns that already have a translation.
                if not turn.translated_text.strip():
                    continue

                turns.append(turn)

                if len(turns) >= max_lines:
                    break

            turns.reverse()

            if not turns:
                return ""

            context_lines = []

            for turn in turns:

                context_lines.append(
                    f"Source: {turn.source_text}"
                )

                context_lines.append(
                    f"Translation: {turn.translated_text}"
                )

            return "\n".join(context_lines)

    # =========================================================
    # CLEAR
    # =========================================================

    def clear(self):
        """
        Clear the entire conversation history.
        """

        with self._lock:

            self.history.clear()
            self._turns_by_id.clear()

            self._next_id = 1

    # =========================================================
    # COUNT
    # =========================================================

    def count(self) -> int:
        """
        Return number of conversation turns.
        """

        with self._lock:

            return len(self.history)

    # =========================================================
    # INTERNAL FIND
    # =========================================================

    def _find_turn_unlocked(
        self,
        turn_id: int,
    ) -> Optional[ConversationTurn]:
        """
        Find a turn while the caller already holds the lock.

        This method must not be called directly from outside
        the manager.
        """

        for turn in self.history:

            if turn.id == turn_id:
                return turn

        return None