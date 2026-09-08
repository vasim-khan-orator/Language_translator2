from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ConversationTurn:
    """
    Represents one completed speech/translation turn.

    A turn can receive multiple translation revisions:
        - progressive chunk translation
        - final translation
        - context-aware refinement

    The ConversationManager is responsible for
    validating and applying revisions safely.
    """

    id: int

    source_language: str

    target_language: str

    source_text: str

    translated_text: str = ""

    # Latest accepted translation revision.
    revision: int = 0

    timestamp: Optional[datetime] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()