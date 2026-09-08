import os


# Riva server
RIVA_SERVER = os.getenv(
    "RIVA_SERVER",
    "172.16.155.14:50051"
)


# Audio
SAMPLE_RATE = 16000
CHANNELS = 1

# Real-time audio frame
FRAME_MS = 20
FRAME_SIZE = int(
    SAMPLE_RATE * FRAME_MS / 1000
)


# Languages
SOURCE_LANGUAGE = os.getenv(
    "SOURCE_LANGUAGE",
    "en-US"
)

TARGET_LANGUAGE = os.getenv(
    "TARGET_LANGUAGE",
    "hi-IN"
)


# Ollama
OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "http://172.16.155.14:11434"
)

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "llama3.2:3b"
)


# Conversation
MAX_HISTORY_LINES = 5


# Utterance detection
SILENCE_TIMEOUT = float(
    os.getenv(
        "SILENCE_TIMEOUT",
        "1.2"
    )
)