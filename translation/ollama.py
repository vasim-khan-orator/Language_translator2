import requests
import time

from config import (
    OLLAMA_URL,
    OLLAMA_MODEL,
)


class OllamaTranslator:

    def __init__(
        self,
        url=OLLAMA_URL,
        model=OLLAMA_MODEL,
    ):
        self.url = url.rstrip("/")
        self.model = model

    # =========================================================
    # TRANSLATE TEXT
    # =========================================================

    def translate(
        self,
        text,
        source_language,
        target_language,
    ):

        text = text.strip()

        if not text:
            return ""

        prompt = f"""
You are a professional real-time translator.

Translate the following text from {source_language}
to {target_language}.

Rules:
- Return ONLY the translation.
- Do not explain anything.
- Do not add comments.
- Do not repeat the original text.
- Preserve the exact meaning.
- Preserve names.
- Preserve numbers.
- Preserve technical terms when appropriate.
- Do not add information.
- Keep the same tone and intent as the speaker.

Source text:
{text}

Translation:
"""

        request_start = time.perf_counter()

        response = requests.post(
            f"{self.url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
            },
            timeout=60,
        )

        request_end = time.perf_counter()

        request_ms = (
            request_end - request_start
        ) * 1000

        # Raise an error if Ollama returns HTTP error
        response.raise_for_status()

        data = response.json()

        translation = data.get("response", "")

        return translation.strip()