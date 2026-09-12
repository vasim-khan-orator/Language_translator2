import threading

from ui.window import TranslatorWindow
from ui.bridge import UIBridge

import main


def main_app():
    window = TranslatorWindow()
    bridge = UIBridge(window)

    window.set_bridge(bridge)

    translator_thread = threading.Thread(
        target=main.run_translator,
        args=(bridge,),
        daemon=True,
    )
    translator_thread.start()

    bridge.start()
    window.run()


if __name__ == "__main__":
    main_app()
