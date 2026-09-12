# import json
# import requests
# import time

# from config import (
#     OLLAMA_URL,
#     OLLAMA_MODEL,
# )


# class OllamaTranslator:

#     def __init__(
#         self,
#         url=OLLAMA_URL,
#         model=OLLAMA_MODEL,
#     ):
#         self.url = url.rstrip("/")
#         self.model = model

#         # Reuse the HTTP connection between translation requests.
#         # This avoids repeatedly creating a new TCP connection.
#         self.session = requests.Session()

#         # Keep the model resident on the Ollama server so short idle
#         # gaps do not cause an unnecessary model reload.
#         self.keep_alive = "30m"

#         # Deterministic translation reduces unnecessary generation.
#         self.temperature = 0.0

#         # Keep generated output bounded. Individual operations can
#         # override this through _generate().
#         self.chunk_num_predict = 64
#         self.final_num_predict = 128
#         self.refinement_num_predict = 128

#     # =========================================================
#     # INTERNAL OLLAMA REQUEST
#     # =========================================================

#     def _generate(
#         self,
#         prompt,
#         stream=False,
#         num_predict=None,
#     ):
#         """
#         Send a prompt to Ollama and return:
#             generated_text, request_time_ms

#         request_time_ms is the complete HTTP request round-trip.
#         Ollama's internal timing metrics are printed for diagnostics
#         when they are present in the response.
#         """

#         request_start = time.perf_counter()

#         options = {
#             "temperature": self.temperature,
#         }

#         if num_predict is not None:
#             options["num_predict"] = num_predict

#         response = self.session.post(
#             f"{self.url}/api/generate",
#             json={
#                 "model": self.model,
#                 "prompt": prompt,
#                 "stream": stream,
#                 "keep_alive": self.keep_alive,
#                 "options": options,
#             },
#             timeout=60,
#         )

#         request_end = time.perf_counter()

#         request_ms = (
#             request_end - request_start
#         ) * 1000

#         response.raise_for_status()

#         data = response.json()

#         # Ollama exposes useful server-side timing information.
#         # Keep the normal return interface unchanged while making
#         # latency diagnosis visible in the terminal.
#         total_duration_ms = (
#             data.get("total_duration", 0) / 1_000_000
#         )
#         load_duration_ms = (
#             data.get("load_duration", 0) / 1_000_000
#         )
#         prompt_eval_duration_ms = (
#             data.get("prompt_eval_duration", 0) / 1_000_000
#         )
#         eval_duration_ms = (
#             data.get("eval_duration", 0) / 1_000_000
#         )

#         if any(
#             (
#                 total_duration_ms,
#                 load_duration_ms,
#                 prompt_eval_duration_ms,
#                 eval_duration_ms,
#             )
#         ):
#             print(
#                 "[Ollama] "
#                 f"HTTP={request_ms:.0f} ms | "
#                 f"server={total_duration_ms:.0f} ms | "
#                 f"load={load_duration_ms:.0f} ms | "
#                 f"prompt_eval={prompt_eval_duration_ms:.0f} ms | "
#                 f"generation={eval_duration_ms:.0f} ms"
#             )

#         text = data.get(
#             "response",
#             "",
#         ).strip()

#         return text, request_ms

#     # =========================================================
#     # CHUNK TRANSLATION
#     # =========================================================

#     def translate_chunk(
#         self,
#         text,
#         source_language,
#         target_language,
#     ):
#         """
#         Translate a short piece of speech
#         while the speaker is still talking.
#         """

#         text = text.strip()

#         if not text:
#             return "", 0.0

#         prompt = f"""
# You are a professional real-time translator.

# Translate this short speech fragment from
# {source_language} to {target_language}.

# Rules:
# - Return ONLY the translation.
# - Do not explain anything.
# - Do not add information.
# - Preserve names.
# - Preserve numbers.
# - Preserve technical terms when appropriate.
# - Keep the meaning and intent.
# - Keep the translation concise.
# - Do not repeat the source text.

# Source:
# {text}

# Translation:
# """

#         return self._generate(
#             prompt=prompt,
#             stream=False,
#             num_predict=self.chunk_num_predict,
#         )

#     # =========================================================
#     # INCREMENTAL TRANSLATION
#     # =========================================================

#     def translate_incremental(
#         self,
#         text,
#         source_language,
#         target_language,
#     ):
#         """
#         Translate one small newly-heard fragment.

#         This compatibility path is deliberately compact and non-streaming.
#         The real-time worker uses translate_incremental_stream().
#         """
#         text = (text or "").strip()

#         if not text:
#             return "", 0.0

#         prompt = f"""Translate {source_language} to {target_language}.
# Return only the translation of the words below.
# Do not complete the sentence. Do not add or explain.

# Text:
# {text}

# Translation:
# """

#         return self._generate(
#             prompt=prompt,
#             stream=False,
#             num_predict=32,
#         )

#     # =========================================================
#     # INCREMENTAL STREAMING TRANSLATION
#     # =========================================================

#     def translate_incremental_stream(
#         self,
#         text,
#         source_language,
#         target_language,
#         on_text=None,
#         flush_interval=0.04,
#     ):
#         """
#         Stream a small live fragment from Ollama.

#         The caller receives the accumulated fragment translation through
#         on_text(). A full request is still only one small translation unit.
#         """

#         text = (text or "").strip()

#         if not text:
#             return "", 0.0

#         prompt = f"""Translate {source_language} to {target_language}.
# Return ONLY the translation.
# Translate only the text provided.
# Do not guess, complete, explain, answer, or add words.

# Text:
# {text}

# Translation:
# """

#         request_start = time.perf_counter()

#         response = self.session.post(
#             f"{self.url}/api/generate",
#             json={
#                 "model": self.model,
#                 "prompt": prompt,
#                 "stream": True,
#                 "keep_alive": self.keep_alive,
#                 "options": {
#                     "temperature": self.temperature,
#                     "num_predict": 40,
#                 },
#             },
#             timeout=60,
#             stream=True,
#         )

#         try:
#             response.raise_for_status()

#             parts = []
#             last_emit = 0.0
#             emitted = ""

#             for raw_line in response.iter_lines(decode_unicode=True):
#                 if not raw_line:
#                     continue

#                 try:
#                     data = json.loads(raw_line)
#                 except json.JSONDecodeError:
#                     continue

#                 piece = data.get("response", "")

#                 if piece:
#                     parts.append(piece)
#                     current = "".join(parts)
#                     now = time.perf_counter()

#                     if (
#                         not emitted
#                         or now - last_emit >= flush_interval
#                     ):
#                         emitted = current
#                         last_emit = now

#                         if on_text is not None:
#                             on_text(current)

#                 if data.get("done"):
#                     total_duration_ms = (
#                         data.get("total_duration", 0)
#                         / 1_000_000
#                     )
#                     load_duration_ms = (
#                         data.get("load_duration", 0)
#                         / 1_000_000
#                     )
#                     prompt_eval_duration_ms = (
#                         data.get("prompt_eval_duration", 0)
#                         / 1_000_000
#                     )
#                     eval_duration_ms = (
#                         data.get("eval_duration", 0)
#                         / 1_000_000
#                     )

#                     request_ms = (
#                         time.perf_counter()
#                         - request_start
#                     ) * 1000

#                     if any(
#                         (
#                             total_duration_ms,
#                             load_duration_ms,
#                             prompt_eval_duration_ms,
#                             eval_duration_ms,
#                         )
#                     ):
#                         print(
#                             "[Ollama LIVE] "
#                             f"HTTP={request_ms:.0f} ms | "
#                             f"server={total_duration_ms:.0f} ms | "
#                             f"load={load_duration_ms:.0f} ms | "
#                             f"prompt={prompt_eval_duration_ms:.0f} ms | "
#                             f"generation={eval_duration_ms:.0f} ms"
#                         )

#                     break

#             final_text = "".join(parts).strip()

#             if (
#                 final_text
#                 and on_text is not None
#                 and final_text != emitted
#             ):
#                 on_text(final_text)

#             return (
#                 final_text,
#                 (time.perf_counter() - request_start) * 1000,
#             )

#         finally:
#             response.close()

#     # =========================================================
#     # FINAL TRANSLATION
#     # =========================================================

#     def translate_final(
#         self,
#         text,
#         source_language,
#         target_language,
#     ):
#         """
#         Translate the complete finalized utterance.
#         """

#         text = text.strip()

#         if not text:
#             return "", 0.0

#         prompt = f"""
# You are a professional translator.

# Translate the complete speech below from
# {source_language} to {target_language}.

# Rules:
# - Return ONLY the translation.
# - Do not explain anything.
# - Do not add comments.
# - Do not repeat the original text.
# - Preserve the exact meaning.
# - Preserve names.
# - Preserve numbers.
# - Preserve technical terms when appropriate.
# - Do not add information.
# - Preserve the speaker's tone and intent.
# - Produce natural, grammatically correct translation.

# Source:
# {text}

# Translation:
# """

#         return self._generate(
#             prompt=prompt,
#             stream=False,
#             num_predict=self.final_num_predict,
#         )

#     # =========================================================
#     # CONTEXT REFINEMENT
#     # =========================================================

#     def refine(
#         self,
#         source_text,
#         current_translation,
#         context,
#         source_language,
#         target_language,
#     ):
#         """
#         Improve an existing translation using
#         previous conversation context.
#         """

#         source_text = source_text.strip()
#         current_translation = current_translation.strip()

#         if not source_text:
#             return "", 0.0

#         if not current_translation:
#             return self.translate_final(
#                 source_text,
#                 source_language,
#                 target_language,
#             )

#         prompt = f"""
# You are a professional real-time translation editor.

# The goal is to verify and, only when necessary,
# improve the current translation using the
# conversation context.

# Source language:
# {source_language}

# Target language:
# {target_language}

# Conversation context:
# {context}

# Current source:
# {source_text}

# Current translation:
# {current_translation}

# Rules:
# - Return ONLY the final translation.
# - Do not explain your changes.
# - Do not add information.
# - Preserve the exact meaning of the source.
# - Use conversation context to resolve ambiguous
#   words or references.
# - Preserve names and numbers.
# - Preserve technical terms when appropriate.
# - Do not change correct wording unnecessarily.
# - Keep the speaker's tone and intent.
# - Make the translation natural and grammatically correct.

# Final translation:
# """

#         return self._generate(
#             prompt=prompt,
#             stream=False,
#             num_predict=self.refinement_num_predict,
#         )

#     # =========================================================
#     # BACKWARD-COMPATIBLE TRANSLATE
#     # =========================================================

#     def translate(
#         self,
#         text,
#         source_language,
#         target_language,
#     ):
#         """
#         Default translation method.

#         Kept for compatibility with the existing
#         TranslationWorker.
#         """

#         translation, request_ms = self.translate_final(
#             text=text,
#             source_language=source_language,
#             target_language=target_language,
#         )

#         return translation