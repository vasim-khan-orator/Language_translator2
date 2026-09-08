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
    # INTERNAL OLLAMA REQUEST
    # =========================================================

    def _generate(
        self,
        prompt,
        stream=False,
    ):
        """
        Send a prompt to Ollama and return
        the generated text + request timing.
        """

        request_start = time.perf_counter()

        response = requests.post(
            f"{self.url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": stream,
            },
            timeout=60,
        )

        request_end = time.perf_counter()

        request_ms = (
            request_end - request_start
        ) * 1000

        response.raise_for_status()

        data = response.json()

        text = data.get(
            "response",
            "",
        ).strip()

        return text, request_ms

    # =========================================================
    # CHUNK TRANSLATION
    # =========================================================

    def translate_chunk(
        self,
        text,
        source_language,
        target_language,
    ):
        """
        Translate a short piece of speech
        while the speaker is still talking.
        """

        text = text.strip()

        if not text:
            return "", 0.0

        prompt = f"""
You are a professional real-time translator.

Translate this short speech fragment from
{source_language} to {target_language}.

Rules:
- Return ONLY the translation.
- Do not explain anything.
- Do not add information.
- Preserve names.
- Preserve numbers.
- Preserve technical terms when appropriate.
- Keep the meaning and intent.
- Keep the translation concise.
- Do not repeat the source text.

Source:
{text}

Translation:
"""

        return self._generate(
            prompt=prompt,
            stream=False,
        )

    # =========================================================
    # FINAL TRANSLATION
    # =========================================================

    def translate_final(
        self,
        text,
        source_language,
        target_language,
    ):
        """
        Translate the complete finalized utterance.
        """

        text = text.strip()

        if not text:
            return "", 0.0

        prompt = f"""
You are a professional translator.

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
- Do not add information.
- Preserve the speaker's tone and intent.
- Produce natural, grammatically correct translation.

Source:
{text}

Translation:
"""

        return self._generate(
            prompt=prompt,
            stream=False,
        )

    # =========================================================
    # CONTEXT REFINEMENT
    # =========================================================

    def refine(
        self,
        source_text,
        current_translation,
        context,
        source_language,
        target_language,
    ):
        """
        Improve an existing translation using
        previous conversation context.
        """

        source_text = source_text.strip()
        current_translation = current_translation.strip()

        if not source_text:
            return "", 0.0

        if not current_translation:
            return self.translate_final(
                source_text,
                source_language,
                target_language,
            )

        prompt = f"""
You are a professional real-time translation editor.

The goal is to verify and, only when necessary,
improve the current translation using the
conversation context.

Source language:
{source_language}

Target language:
{target_language}

Conversation context:
{context}

Current source:
{source_text}

Current translation:
{current_translation}

Rules:
- Return ONLY the final translation.
- Do not explain your changes.
- Do not add information.
- Preserve the exact meaning of the source.
- Use conversation context to resolve ambiguous
  words or references.
- Preserve names and numbers.
- Preserve technical terms when appropriate.
- Do not change correct wording unnecessarily.
- Keep the speaker's tone and intent.
- Make the translation natural and grammatically correct.

Final translation:
"""

        return self._generate(
            prompt=prompt,
            stream=False,
        )

    # =========================================================
    # BACKWARD-COMPATIBLE TRANSLATE
    # =========================================================

    def translate(
        self,
        text,
        source_language,
        target_language,
    ):
        """
        Default translation method.

        Kept for compatibility with the existing
        TranslationWorker.
        """

        translation, request_ms = self.translate_final(
            text=text,
            source_language=source_language,
            target_language=target_language,
        )

        return translation