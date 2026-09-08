import threading
import time

from audio.microphone import Microphone
from riva.asr import RivaASR

from conversation.manager import ConversationManager
from conversation.utterance import UtteranceManager

from translation.ollama import OllamaTranslator
from translation.worker import TranslationWorker

from config import (
    SOURCE_LANGUAGE,
    TARGET_LANGUAGE,
    SILENCE_TIMEOUT,
)


def run_translator(bridge=None):

    # =========================================================
    # COMPONENTS
    # =========================================================

    microphone = Microphone()

    asr = RivaASR()

    conversation = ConversationManager(
        source_language=SOURCE_LANGUAGE,
        target_language=TARGET_LANGUAGE,
    )

    utterance = UtteranceManager(
        silence_timeout=SILENCE_TIMEOUT
    )

    # =========================================================
    # OLLAMA
    # =========================================================

    translator = OllamaTranslator()

    translation_worker = TranslationWorker(
        translator=translator,
        conversation=conversation,
        renderer=None,
        bridge=bridge,
    )

    # =========================================================
    # APPLICATION STATE
    # =========================================================

    app_running = True

    # =========================================================
    # UTTERANCE MONITOR
    # =========================================================

    def utterance_monitor():

        while app_running:

            complete_text = (
                utterance.finalize_if_ready()
            )

            if complete_text:

                # -------------------------------------------------
                # CREATE CONVERSATION TURN
                # -------------------------------------------------

                turn = conversation.add_turn(
                    source_text=complete_text
                )

                if turn:

                    # -------------------------------------------------
                    # SEND FINAL SOURCE TO UI
                    # -------------------------------------------------

                    if bridge is not None:

                        bridge.source_final(
                            complete_text
                        )

                    # -------------------------------------------------
                    # SEND TO TRANSLATION WORKER
                    # -------------------------------------------------

                    translation_worker.submit(
                        turn
                    )

            time.sleep(0.05)

    # =========================================================
    # START MONITOR THREAD
    # =========================================================

    monitor_thread = threading.Thread(
        target=utterance_monitor,
        daemon=True,
    )

    try:

        # =====================================================
        # STATUS
        # =====================================================

        if bridge is not None:
            bridge.status("STARTING")

        # =====================================================
        # START MICROPHONE
        # =====================================================

        microphone.start()

        # =====================================================
        # START TRANSLATION WORKER
        # =====================================================

        translation_worker.start()

        # =====================================================
        # START UTTERANCE MONITOR
        # =====================================================

        monitor_thread.start()

        if bridge is not None:
            bridge.status("LISTENING")

        # =====================================================
        # RIVA STREAMING
        # =====================================================

        for result in asr.transcribe(
            microphone.frames()
        ):

            # -------------------------------------------------
            # INTERIM
            # -------------------------------------------------

            if not result.is_final:

                current_text = (
                    utterance.get_current_text()
                )

                if bridge is not None:

                    bridge.source_partial(
                        current_text
                    )

                continue

            # -------------------------------------------------
            # FINAL RIVA SEGMENT
            # -------------------------------------------------

            text = result.text.strip()

            if not text:
                continue

            # -------------------------------------------------
            # ADD STABLE RIVA SEGMENT
            # -------------------------------------------------

            utterance.add_final_segment(
                text
            )

            # -------------------------------------------------
            # DISPLAY ACCUMULATED SPEECH
            # -------------------------------------------------

            if bridge is not None:

                bridge.source_partial(
                    utterance.get_current_text()
                )

    except Exception as exc:

        if bridge is not None:
            bridge.error(str(exc))

        raise

    finally:

        app_running = False

        microphone.stop()

        translation_worker.stop()


# =============================================================
# TERMINAL MODE
# =============================================================

if __name__ == "__main__":

    print("=" * 70)
    print("REAL-TIME TRANSLATOR")
    print("=" * 70)

    run_translator()