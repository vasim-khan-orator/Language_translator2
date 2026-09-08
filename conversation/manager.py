from typing import List

from conversation.models import ConversationTurn


class ConversationManager:
    """
    Maintains the conversation history.
    """

    def __init__(
        self,
        source_language: str,
        target_language: str,
    ):
        self.source_language = source_language
        self.target_language = target_language

        self.history: List[ConversationTurn] = []

        self._next_id = 1

    def add_turn(self, source_text: str) -> ConversationTurn:
        """
        Create and store a new completed conversation turn.
        """

        source_text = source_text.strip()

        if not source_text:
            return None

        turn = ConversationTurn(
            id=self._next_id,
            source_language=self.source_language,
            target_language=self.target_language,
            source_text=source_text,
        )

        self.history.append(turn)

        self._next_id += 1

        return turn

    def get_history(self) -> List[ConversationTurn]:
        """
        Return all conversation turns.
        """

        return self.history

    def get_turn(self, turn_id: int) -> ConversationTurn:
        """
        Find a conversation turn by ID.
        """

        for turn in self.history:

            if turn.id == turn_id:
                return turn

        return None

    def update_translation(
        self,
        turn_id: int,
        translated_text: str,
    ) -> bool:
        """
        Update the translation of an existing turn.

        This will be used when Ollama is added.
        """

        turn = self.get_turn(turn_id)

        if turn is None:
            return False

        turn.translated_text = translated_text.strip()

        return True

    def clear(self):
        """
        Clear the entire conversation history.
        """

        self.history.clear()

        self._next_id = 1

    def count(self) -> int:
        """
        Return number of conversation turns.
        """

        return len(self.history)