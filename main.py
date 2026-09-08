import threading
import time


from audio.microphone import Microphone
from riva.asr import RivaASR

from conversation.manager import ConversationManager
from conversation.utterance import UtteranceManager

from translation.ollama import OllamaTranslator
from translation.chunk_worker import ChunkWorker
from translation.final_worker import FinalTranslationWorker
from translation.refinement_worker import RefinementWorker

from config import (
    SOURCE_LANGUAGE,
    TARGET_LANGUAGE,
    SILENCE_TIMEOUT,
    CHUNK_MAX_WORKERS,
    REFINEMENT_MAX_WORKERS,
    CHUNK_INTERVAL,
    REFINEMENT_INTERVAL,
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

    translator = OllamaTranslator()

    # =========================================================
    # TRANSLATION WORKERS
    # =========================================================

    chunk_worker = ChunkWorker(
        translator=translator,
        conversation=conversation,
        bridge=bridge,
        max_workers=CHUNK_MAX_WORKERS,
        chunk_interval=CHUNK_INTERVAL,
    )

    # ---------------------------------------------------------
    # Refinement worker must be created BEFORE final worker
    # because FinalTranslationWorker receives its callback.
    # ---------------------------------------------------------

    refinement_worker = RefinementWorker(
        translator=translator,
        context_manager=conversation,
        bridge=bridge,
        refresh_interval=REFINEMENT_INTERVAL,
        max_workers=REFINEMENT_MAX_WORKERS,
    )

    final_worker = FinalTranslationWorker(
        translator=translator,
        conversation=conversation,
        bridge=bridge,
        refinement_callback=refinement_worker.submit,
        max_workers=2,
    )

    # =========================================================
    # APPLICATION STATE
    # =========================================================

    app_running = True

    # Current active ConversationTurn.
    #
    # This is created as soon as the first Riva FINAL
    # segment of an utterance arrives.
    active_turn = None

    active_turn_lock = threading.Lock()

    # =========================================================
    # UTTERANCE MONITOR
    # =========================================================

    def utterance_monitor():

        nonlocal active_turn

        while app_running:

            complete_text = (
                utterance.finalize_if_ready()
            )

            if complete_text:

                with active_turn_lock:

                    turn = active_turn
                    active_turn = None

                if turn is not None:

                    # -------------------------------------------------
                    # Make absolutely sure the completed source is
                    # stored in the same conversation turn.
                    # -------------------------------------------------

                    conversation.update_source_text(
                        turn_id=turn.id,
                        source_text=complete_text,
                    )

                    turn = conversation.get_turn(
                        turn.id
                    )

                    if turn is not None:

                        # -------------------------------------------------
                        # FINAL SOURCE TO UI
                        # -------------------------------------------------

                        if bridge is not None:

                            bridge.source_final(
                                complete_text
                            )

                        # -------------------------------------------------
                        # FINAL TRANSLATION
                        # -------------------------------------------------

                        final_worker.submit(
                            turn
                        )

                        # -------------------------------------------------
                        # IMPORTANT:
                        #
                        # Do NOT submit directly to RefinementWorker here.
                        #
                        # FinalTranslationWorker is now responsible for
                        # triggering refinement only after the final
                        # translation has been successfully accepted.
                        # -------------------------------------------------

                # -----------------------------------------------------
                # Prepare ChunkWorker for next utterance.
                # -----------------------------------------------------

                chunk_worker.reset_turn()

            time.sleep(0.05)

    # =========================================================
    # MONITOR THREAD
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

            bridge.status(
                "STARTING"
            )

        # =====================================================
        # MICROPHONE
        # =====================================================

        microphone.start()

        # =====================================================
        # START WORKERS
        # =====================================================

        chunk_worker.start()

        final_worker.start()

        refinement_worker.start()

        # =====================================================
        # START UTTERANCE MONITOR
        # =====================================================

        monitor_thread.start()

        if bridge is not None:

            bridge.status(
                "LISTENING"
            )

        # =====================================================
        # RIVA STREAMING
        # =====================================================

        for result in asr.transcribe(
            microphone.frames()
        ):

            # -------------------------------------------------
            # INTERIM RESULT
            # -------------------------------------------------

            if not result.is_final:

                stable_text = (
                    utterance.get_current_text()
                )

                interim_text = (
                    result.text.strip()
                )

                # Display stable FINAL text + current
                # interim hypothesis.
                if interim_text:

                    if stable_text:

                        display_text = (
                            f"{stable_text} "
                            f"{interim_text}"
                        )

                    else:

                        display_text = (
                            interim_text
                        )

                else:

                    display_text = stable_text

                if bridge is not None:

                    bridge.source_partial(
                        display_text.strip()
                    )

                continue

            # -------------------------------------------------
            # RIVA FINAL SEGMENT
            # -------------------------------------------------

            text = result.text.strip()

            if not text:
                continue

            # -------------------------------------------------
            # ADD STABLE SEGMENT
            # -------------------------------------------------

            utterance.add_final_segment(
                text
            )

            current_text = (
                utterance.get_current_text()
            )

            if not current_text:
                continue

            # -------------------------------------------------
            # CREATE TURN ON FIRST FINAL SEGMENT
            # -------------------------------------------------

            with active_turn_lock:

                if active_turn is None:

                    active_turn = (
                        conversation.add_turn(
                            source_text=current_text
                        )
                    )

                else:

                    conversation.update_source_text(
                        turn_id=active_turn.id,
                        source_text=current_text,
                    )

                    active_turn = (
                        conversation.get_turn(
                            active_turn.id
                        )
                    )

                turn = active_turn

            if turn is None:
                continue

            # -------------------------------------------------
            # GET ONLY NEW STABLE SEGMENT(S)
            # -------------------------------------------------

            new_stable_text = (
                utterance.get_new_stable_text()
            )

            if new_stable_text:

                chunk_worker.submit(
                    text=new_stable_text,
                    source_language=SOURCE_LANGUAGE,
                    target_language=TARGET_LANGUAGE,
                    turn_id=turn.id,
                )

            # -------------------------------------------------
            # DISPLAY ACCUMULATED STABLE SOURCE
            # -------------------------------------------------

            if bridge is not None:

                bridge.source_partial(
                    current_text
                )

    except Exception as exc:

        if bridge is not None:

            bridge.error(
                str(exc)
            )

        raise

    finally:

        app_running = False

        microphone.stop()

        chunk_worker.stop()

        final_worker.stop()

        refinement_worker.stop()


# =============================================================
# TERMINAL MODE
# =============================================================

if __name__ == "__main__":

    print("=" * 70)
    print("REAL-TIME TRANSLATOR")
    print("=" * 70)

    run_translator()