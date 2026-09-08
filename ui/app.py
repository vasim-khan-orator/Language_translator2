import threading

from ui.window import TranslatorWindow
from ui.bridge import UIBridge

import main


def main_app():

    # =========================================================
    # CREATE UI
    # =========================================================

    window = TranslatorWindow()

    bridge = UIBridge(window)

    # =========================================================
    # CONNECT UI TO TRANSLATOR
    # =========================================================

    window.set_bridge(bridge)

    # =========================================================
    # START TRANSLATOR IN BACKGROUND
    # =========================================================

    translator_thread = threading.Thread(
        target=main.run_translator,
        args=(bridge,),
        daemon=True,
    )

    translator_thread.start()

    # =========================================================
    # START UI
    # =========================================================

    bridge.start()

    window.run()


if __name__ == "__main__":
    main_app()