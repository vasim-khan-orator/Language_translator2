import threading
import time


from audio.microphone import Microphone
from riva.asr import RivaASR

from conversation.manager import ConversationManager
from conversation.utterance import UtteranceManager

from translation.chunk_worker import ChunkWorker
from translation.final_worker import FinalTranslationWorker

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

    # The ChunkWorker and FinalTranslationWorker each own their
    # own Ollama HTTP request path. There is no shared translator
    # sender between them.

    # =========================================================
    # TRANSLATION WORKERS
    # =========================================================
    #
    # ChunkWorker:
    #   - receives NEW stable Riva FINAL segments
    #   - accumulates only a few new words
    #   - dispatches fixed-size chunks in parallel
    #   - produces provisional/live translation
    #
    # FinalTranslationWorker:
    #   - starts immediately when the utterance ends
    #   - NEVER waits for the last live chunk
    #   - replaces the provisional translation with the
    #     authoritative full-sentence translation
    # =========================================================

    chunk_worker = ChunkWorker(
        conversation=conversation,
        bridge=bridge,
        max_workers=3,
        chunk_words=3,
    )

    final_worker = FinalTranslationWorker(
        conversation=conversation,
        bridge=bridge,
        max_workers=1,
        incremental_interval=0.15,
        min_fragment_words=2,
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

            with active_turn_lock:

                complete_text = utterance.finalize_if_ready()

                if complete_text:

                    turn = active_turn
                    active_turn = None
                
                else:
                    turn = None

            if complete_text and turn is not None:

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
                            complete_text,
                            turn_id=turn.id,
                        )

                    # -------------------------------------------------
                    # INVALIDATE LIVE CHUNKS
                    # -------------------------------------------------
                    #
                    # Do not wait for any chunk currently running in
                    # Ollama. Their late results become stale and are
                    # discarded.
                    # -------------------------------------------------

                    chunk_worker.finalize_turn(
                        turn.id
                    )

                    # -------------------------------------------------
                    # FINAL TRANSLATION
                    # -------------------------------------------------
                    #
                    # Starts immediately and independently of the
                    # chunk worker.
                    # -------------------------------------------------

                    final_worker.submit_final(turn)

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

                stable_text = utterance.get_current_text()
                interim_text = result.text.strip()

                if interim_text:
                    if stable_text:
                        display_text = (
                            f"{stable_text} {interim_text}"
                        )
                    else:
                        display_text = interim_text
                else:
                    display_text = stable_text

                display_text = display_text.strip()

                if display_text:
                    with active_turn_lock:
                        if active_turn is None:
                            active_turn = conversation.add_turn(
                                source_text=display_text
                            )
                        else:
                            conversation.update_source_text(
                                turn_id=active_turn.id,
                                source_text=display_text,
                            )

                        current_turn_id = (
                            active_turn.id
                            if active_turn is not None
                            else None
                        )

                    if bridge is not None:
                        bridge.source_partial(
                            display_text,
                            turn_id=current_turn_id,
                        )

                    # Interim ASR is display-only.
                    #
                    # Chunk translation is triggered from stable
                    # Riva FINAL segments below. This prevents the
                    # same rewritten interim hypothesis from being
                    # submitted repeatedly to Ollama.


                continue

            # -------------------------------------------------
            # RIVA FINAL SEGMENT
            # -------------------------------------------------

            text = result.text.strip()

            if not text:
                continue

            # -------------------------------------------------
            # ATOMIC FINAL-SEGMENT HANDLING
            # -------------------------------------------------
            # Keep utterance state and active_turn synchronized with
            # utterance_monitor() so a silence finalization cannot race
            # with a new Riva FINAL segment.

            with active_turn_lock:

                utterance.add_final_segment(text)

                current_text = (
                    utterance.get_current_text()
                )

                if not current_text:
                    continue

                # -------------------------------------------------
                # CREATE TURN ON FIRST FINAL SEGMENT
                # -------------------------------------------------

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

                current_turn_id = turn.id

            # -------------------------------------------------
            # DISPLAY ACCUMULATED STABLE SOURCE
            # -------------------------------------------------

            if bridge is not None:
                bridge.source_partial(
                    current_text,
                    turn_id=current_turn_id,
                )

            # -------------------------------------------------
            # PARALLEL BACKEND WORK
            # -------------------------------------------------
            #
            # 1. FinalTranslationWorker receives the accumulated
            #    stable source snapshot. Its incremental requests run
            #    independently as backend work.
            #
            # 2. ChunkWorker receives only the NEW stable segment.
            #    It translates 3-word chunks in parallel and sends
            #    completed chunks to the UI immediately, in source order.
            #
            # 3. When the utterance ends, ChunkWorker invalidates all
            #    unfinished provisional chunks and FinalTranslationWorker
            #    sends the complete sentence on its own final executor.
            #
            # The final result is authoritative and replaces the visible
            # provisional chunk translation.
            # -------------------------------------------------

            chunk_worker.submit(
                text,
                source_language=SOURCE_LANGUAGE,
                target_language=TARGET_LANGUAGE,
                turn_id=current_turn_id,
            )

            # Capture which chunks are covered by this incremental snapshot.
            # Any later chunk gets a higher sequence number and may appear
            # live after the snapshot.
            chunk_cutoff = chunk_worker.get_dispatched_count(
                current_turn_id
            )

            final_worker.submit_incremental(
                current_turn_id,
                current_text,
                chunk_cutoff=chunk_cutoff,
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

        # Chunk requests are provisional. They are stopped without
        # waiting for unfinished Ollama requests.
        chunk_worker.stop()

        final_worker.stop()



# =============================================================
# TERMINAL MODE
# =============================================================

if __name__ == "__main__":

    print("=" * 70)
    print("REAL-TIME TRANSLATOR")
    print("=" * 70)

    run_translator()