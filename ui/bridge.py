import queue


class UIBridge:
    """
    Safely transfers events from the translator/background threads
    to the Tkinter UI thread.
    """

    def __init__(self, window):
        self.window = window
        self.events = queue.Queue()

    # =========================================================
    # EVENTS FROM TRANSLATOR
    # =========================================================

    def source_partial(self, text):
        self.events.put(("source_partial", text))

    def source_final(self, text):
        self.events.put(("source_final", text))

    def translation_started(self):
        self.events.put(("translation_started", None))

    def translation_finished(
        self,
        text,
        api_ms,
        total_ms,
    ):
        self.events.put(
            (
                "translation_finished",
                {
                    "text": text,
                    "api_ms": api_ms,
                    "total_ms": total_ms,
                },
            )
        )

    def status(self, text):
        self.events.put(("status", text))

    def error(self, text):
        self.events.put(("error", text))

    # =========================================================
    # PROCESS EVENTS
    # =========================================================

    def process_events(self):
        """
        Called periodically by Tkinter's main thread.
        """

        while True:

            try:
                event, data = self.events.get_nowait()

            except queue.Empty:
                break

            if event == "source_partial":

                self.window.set_source_text(data)

            elif event == "source_final":

                self.window.set_source_text(data)

            elif event == "translation_started":

                self.window.set_status("TRANSLATING")

            elif event == "translation_finished":

                self.window.set_translation(
                    data["text"]
                )

                self.window.set_metrics(
                    api_ms=data["api_ms"],
                    total_ms=data["total_ms"],
                )

                self.window.set_status("LISTENING")

            elif event == "status":

                self.window.set_status(data)

            elif event == "error":

                self.window.set_status(
                    f"ERROR: {data}"
                )

        # Check again after 50 ms.
        self.window.root.after(
            50,
            self.process_events
        )

    # =========================================================
    # START
    # =========================================================

    def start(self):
        self.window.root.after(
            50,
            self.process_events
        )