from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ConversationTurn:
    """
    Represents one completed speech/translation turn.
    """

    id: int

    source_language: str

    target_language: str

    source_text: str

    translated_text: str = ""

    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()