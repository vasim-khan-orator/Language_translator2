import tkinter as tk

from ui.styles import (
    WINDOW_TITLE,
    WINDOW_WIDTH,
    WINDOW_HEIGHT,
    BACKGROUND,
    PANEL_BACKGROUND,
    TEXT_BACKGROUND,
    TEXT_COLOR,
    SECONDARY_TEXT,
    ACCENT_COLOR,
    WARNING_COLOR,
    FONT_TITLE,
    FONT_SECTION,
    FONT_TEXT,
    FONT_SMALL,
    FONT_METRIC,
)


class TranslatorWindow:
    def __init__(self):
        self.root = tk.Tk()

        self.root.title(WINDOW_TITLE)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.configure(bg=BACKGROUND)

        self._create_header()
        self._create_translation_area()
        self._create_status_area()
        self._create_metrics_area()
        self._create_controls()

    # ---------------------------------------------------------
    # Header
    # ---------------------------------------------------------

    def _create_header(self):
        header = tk.Frame(
            self.root,
            bg=BACKGROUND
        )

        header.pack(
            fill="x",
            padx=25,
            pady=(20, 10)
        )

        title = tk.Label(
            header,
            text="REAL-TIME LANGUAGE TRANSLATOR",
            bg=BACKGROUND,
            fg=TEXT_COLOR,
            font=FONT_TITLE
        )

        title.pack(side="left")

    # ---------------------------------------------------------
    # Translation area
    # ---------------------------------------------------------

    def _create_translation_area(self):

        container = tk.Frame(
            self.root,
            bg=BACKGROUND
        )

        container.pack(
            fill="both",
            expand=True,
            padx=25,
            pady=10
        )

        # Source panel
        source_frame = tk.Frame(
            container,
            bg=PANEL_BACKGROUND
        )

        source_frame.pack(
            side="left",
            fill="both",
            expand=True,
            padx=(0, 8)
        )

        source_label = tk.Label(
            source_frame,
            text="SOURCE",
            bg=PANEL_BACKGROUND,
            fg=SECONDARY_TEXT,
            font=FONT_SECTION
        )

        source_label.pack(
            anchor="w",
            padx=15,
            pady=(15, 5)
        )

        self.source_text = tk.Text(
            source_frame,
            bg=TEXT_BACKGROUND,
            fg=TEXT_COLOR,
            insertbackground=TEXT_COLOR,
            font=FONT_TEXT,
            wrap="word",
            relief="flat",
            padx=15,
            pady=15
        )

        self.source_text.pack(
            fill="both",
            expand=True,
            padx=15,
            pady=(0, 15)
        )

        # Translation panel
        target_frame = tk.Frame(
            container,
            bg=PANEL_BACKGROUND
        )

        target_frame.pack(
            side="right",
            fill="both",
            expand=True,
            padx=(8, 0)
        )

        target_label = tk.Label(
            target_frame,
            text="TRANSLATION",
            bg=PANEL_BACKGROUND,
            fg=SECONDARY_TEXT,
            font=FONT_SECTION
        )

        target_label.pack(
            anchor="w",
            padx=15,
            pady=(15, 5)
        )

        self.translation_text = tk.Text(
            target_frame,
            bg=TEXT_BACKGROUND,
            fg=TEXT_COLOR,
            insertbackground=TEXT_COLOR,
            font=FONT_TEXT,
            wrap="word",
            relief="flat",
            padx=15,
            pady=15
        )

        self.translation_text.pack(
            fill="both",
            expand=True,
            padx=15,
            pady=(0, 15)
        )

    # ---------------------------------------------------------
    # Status
    # ---------------------------------------------------------

    def _create_status_area(self):

        status_frame = tk.Frame(
            self.root,
            bg=PANEL_BACKGROUND
        )

        status_frame.pack(
            fill="x",
            padx=25,
            pady=10
        )

        status_title = tk.Label(
            status_frame,
            text="STATUS",
            bg=PANEL_BACKGROUND,
            fg=SECONDARY_TEXT,
            font=FONT_SECTION
        )

        status_title.pack(
            side="left",
            padx=15,
            pady=12
        )

        self.status_label = tk.Label(
            status_frame,
            text="● READY",
            bg=PANEL_BACKGROUND,
            fg=ACCENT_COLOR,
            font=FONT_SECTION
        )

        self.status_label.pack(
            side="left",
            padx=10
        )

    # ---------------------------------------------------------
    # Performance metrics
    # ---------------------------------------------------------

    def _create_metrics_area(self):

        metrics_frame = tk.Frame(
            self.root,
            bg=PANEL_BACKGROUND
        )

        metrics_frame.pack(
            fill="x",
            padx=25,
            pady=10
        )

        title = tk.Label(
            metrics_frame,
            text="PERFORMANCE",
            bg=PANEL_BACKGROUND,
            fg=SECONDARY_TEXT,
            font=FONT_SECTION
        )

        title.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
            padx=15,
            pady=(12, 8)
        )

        # Silence wait
        tk.Label(
            metrics_frame,
            text="Silence wait:",
            bg=PANEL_BACKGROUND,
            fg=TEXT_COLOR,
            font=FONT_METRIC
        ).grid(
            row=1,
            column=0,
            sticky="w",
            padx=15,
            pady=3
        )

        self.silence_metric = tk.Label(
            metrics_frame,
            text="-- ms",
            bg=PANEL_BACKGROUND,
            fg=TEXT_COLOR,
            font=FONT_METRIC
        )

        self.silence_metric.grid(
            row=1,
            column=1,
            sticky="w"
        )

        # API latency
        tk.Label(
            metrics_frame,
            text="Translation/API:",
            bg=PANEL_BACKGROUND,
            fg=TEXT_COLOR,
            font=FONT_METRIC
        ).grid(
            row=2,
            column=0,
            sticky="w",
            padx=15,
            pady=3
        )

        self.api_metric = tk.Label(
            metrics_frame,
            text="-- ms",
            bg=PANEL_BACKGROUND,
            fg=TEXT_COLOR,
            font=FONT_METRIC
        )

        self.api_metric.grid(
            row=2,
            column=1,
            sticky="w"
        )

        # Total latency
        tk.Label(
            metrics_frame,
            text="Total translation delay:",
            bg=PANEL_BACKGROUND,
            fg=TEXT_COLOR,
            font=FONT_METRIC
        ).grid(
            row=3,
            column=0,
            sticky="w",
            padx=15,
            pady=(3, 12)
        )

        self.total_metric = tk.Label(
            metrics_frame,
            text="-- ms",
            bg=PANEL_BACKGROUND,
            fg=WARNING_COLOR,
            font=FONT_METRIC
        )

        self.total_metric.grid(
            row=3,
            column=1,
            sticky="w"
        )

    # ---------------------------------------------------------
    # Controls
    # ---------------------------------------------------------

    def _create_controls(self):

        controls = tk.Frame(
            self.root,
            bg=BACKGROUND
        )

        controls.pack(
            fill="x",
            padx=25,
            pady=(5, 20)
        )

        self.start_button = tk.Button(
            controls,
            text="START",
            command=self.start,
            bg=ACCENT_COLOR,
            fg="white",
            font=FONT_SECTION,
            relief="flat",
            padx=30,
            pady=8
        )

        self.start_button.pack(
            side="left"
        )

        self.stop_button = tk.Button(
            controls,
            text="STOP",
            command=self.stop,
            bg="#555555",
            fg="white",
            font=FONT_SECTION,
            relief="flat",
            padx=30,
            pady=8
        )

        self.stop_button.pack(
            side="left",
            padx=10
        )

    # ---------------------------------------------------------
    # Public UI functions
    # ---------------------------------------------------------

    def set_source_text(self, text):
        self.source_text.delete("1.0", tk.END)
        self.source_text.insert(tk.END, text)

    def set_translation(self, text):
        self.translation_text.delete("1.0", tk.END)
        self.translation_text.insert(tk.END, text)

    def set_status(self, status):
        self.status_label.config(text=f"● {status}")

    def set_bridge(self, bridge):
        self.bridge = bridge


    def set_metrics(
        self,
        silence_ms=None,
        api_ms=None,
        total_ms=None
    ):
        if silence_ms is not None:
            self.silence_metric.config(
                text=f"{silence_ms:.0f} ms"
            )

        if api_ms is not None:
            self.api_metric.config(
                text=f"{api_ms:.0f} ms"
            )

        if total_ms is not None:
            self.total_metric.config(
                text=f"{total_ms:.0f} ms"
            )

    def start(self):

        self.set_status("LISTENING")

        if hasattr(self, "bridge"):
            self.bridge.status("LISTENING")


    def stop(self):

        self.set_status("STOPPED")

        if hasattr(self, "bridge"):
            self.bridge.status("STOPPED")
    def run(self):
        self.root.mainloop()    

    