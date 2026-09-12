import tkinter as tk

from ui.styles import (
    WINDOW_TITLE,
    WINDOW_WIDTH,
    WINDOW_HEIGHT,
    BACKGROUND,
    PANEL_BACKGROUND,
    TEXT_BACKGROUND,
    TEXT_COLOR,
    SOURCE_TEXT_COLOR,
    SECONDARY_TEXT,
    ACCENT_COLOR,
    WARNING_COLOR,
    BORDER_COLOR,
    BUTTON_BACKGROUND,
    FONT_TITLE,
    FONT_LANGUAGE,
    FONT_SOURCE,
    FONT_TRANSLATION,
    FONT_SMALL,
    FONT_METRIC,
    FONT_STATUS,
)


class TranslatorWindow:
    """
    Reference-style conversation UI.

    Each speech turn is represented by one history card:

        source text
        translation

    The current turn is updated in place while speech continues.
    Once silence finalizes the turn, the card remains in history and
    the next speech creates a new card.
    """

    def __init__(self):
        self.root = tk.Tk()
        self.root.title(WINDOW_TITLE)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.minsize(850, 620)
        self.root.configure(bg=BACKGROUND)

        self.bridge = None
        self.turn_cards = {}
        self.current_turn_id = None
        self.live_source = ""
        self.live_card = None

        self._create_header()
        self._create_history_area()
        self._create_footer()

    # ---------------------------------------------------------
    # Header
    # ---------------------------------------------------------

    def _create_header(self):
        header = tk.Frame(self.root, bg=BACKGROUND)
        header.pack(fill="x", padx=28, pady=(22, 10))

        title = tk.Label(
            header,
            text="REAL-TIME LANGUAGE TRANSLATOR",
            bg=BACKGROUND,
            fg=TEXT_COLOR,
            font=FONT_TITLE,
        )
        title.pack(side="left")

        self.language_frame = tk.Frame(header, bg=BACKGROUND)
        self.language_frame.pack(side="right")

        self.source_language_label = tk.Label(
            self.language_frame,
            text="English",
            bg=BUTTON_BACKGROUND,
            fg=TEXT_COLOR,
            font=FONT_LANGUAGE,
            padx=16,
            pady=8,
        )
        self.source_language_label.pack(side="left")

        arrow = tk.Label(
            self.language_frame,
            text="⇄",
            bg=BACKGROUND,
            fg=TEXT_COLOR,
            font=("Arial", 18, "bold"),
            padx=10,
        )
        arrow.pack(side="left")

        self.target_language_label = tk.Label(
            self.language_frame,
            text="Hindi",
            bg=BUTTON_BACKGROUND,
            fg=TEXT_COLOR,
            font=FONT_LANGUAGE,
            padx=16,
            pady=8,
        )
        self.target_language_label.pack(side="left")

    # ---------------------------------------------------------
    # Scrollable history
    # ---------------------------------------------------------

    def _create_history_area(self):
        outer = tk.Frame(self.root, bg=BACKGROUND)
        outer.pack(fill="both", expand=True, padx=18, pady=(4, 10))

        self.canvas = tk.Canvas(
            outer,
            bg=TEXT_BACKGROUND,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(
            outer,
            orient="vertical",
            command=self.canvas.yview,
            troughcolor=BACKGROUND,
            bg=BUTTON_BACKGROUND,
            activebackground=BUTTON_BACKGROUND,
            relief="flat",
        )
        scrollbar.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.history_frame = tk.Frame(self.canvas, bg=TEXT_BACKGROUND)
        self.canvas_window = self.canvas.create_window(
            (0, 0),
            window=self.history_frame,
            anchor="nw",
        )

        self.history_frame.bind(
            "<Configure>",
            self._on_history_configure,
        )
        self.canvas.bind(
            "<Configure>",
            self._on_canvas_configure,
        )

        # Mouse wheel scrolling.
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        empty = tk.Label(
            self.history_frame,
            text="Speak naturally. Your conversation will appear here.",
            bg=TEXT_BACKGROUND,
            fg=SECONDARY_TEXT,
            font=("Arial", 15),
            pady=50,
        )
        empty.pack()
        self.empty_label = empty

    def _on_history_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(
            self.canvas_window,
            width=event.width,
        )

    def _on_mousewheel(self, event):
        if event.delta:
            self.canvas.yview_scroll(
                int(-1 * (event.delta / 120)),
                "units",
            )

    def _scroll_to_bottom(self):
        self.root.after(
            10,
            lambda: self.canvas.yview_moveto(1.0),
        )

    # ---------------------------------------------------------
    # Turn cards
    # ---------------------------------------------------------

    def _remove_empty_message(self):
        if self.empty_label is not None:
            self.empty_label.destroy()
            self.empty_label = None

    def _create_turn_card(self, turn_id, source_text=""):
        self._remove_empty_message()

        card = tk.Frame(
            self.history_frame,
            bg=TEXT_BACKGROUND,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            padx=18,
            pady=16,
        )
        card.pack(
            fill="x",
            padx=16,
            pady=(12, 0),
        )

        source_label = tk.Label(
            card,
            text=source_text,
            bg=TEXT_BACKGROUND,
            fg=SOURCE_TEXT_COLOR,
            font=FONT_SOURCE,
            justify="left",
            anchor="w",
            wraplength=900,
        )
        source_label.pack(fill="x")

        translation_label = tk.Label(
            card,
            text="",
            bg=TEXT_BACKGROUND,
            fg=TEXT_COLOR,
            font=FONT_TRANSLATION,
            justify="left",
            anchor="w",
            wraplength=900,
        )
        translation_label.pack(
            fill="x",
            pady=(8, 0),
        )

        self.turn_cards[turn_id] = {
            "frame": card,
            "source": source_label,
            "translation": translation_label,
            "completed": False,
        }
        self.current_turn_id = turn_id

        self._refresh_wraplengths()
        self._scroll_to_bottom()

    def _refresh_wraplengths(self):
        width = max(self.canvas.winfo_width() - 85, 450)
        for card in self.turn_cards.values():
            card["source"].configure(wraplength=width)
            card["translation"].configure(wraplength=width)

    def _create_live_card(self, source_text=""):
        self._remove_empty_message()

        card = tk.Frame(
            self.history_frame,
            bg=TEXT_BACKGROUND,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            padx=18,
            pady=16,
        )
        card.pack(
            fill="x",
            padx=16,
            pady=(12, 0),
        )

        source_label = tk.Label(
            card,
            text=source_text,
            bg=TEXT_BACKGROUND,
            fg=SOURCE_TEXT_COLOR,
            font=FONT_SOURCE,
            justify="left",
            anchor="w",
            wraplength=900,
        )
        source_label.pack(fill="x")

        translation_label = tk.Label(
            card,
            text="",
            bg=TEXT_BACKGROUND,
            fg=TEXT_COLOR,
            font=FONT_TRANSLATION,
            justify="left",
            anchor="w",
            wraplength=900,
        )
        translation_label.pack(
            fill="x",
            pady=(8, 0),
        )

        self.live_card = {
            "frame": card,
            "source": source_label,
            "translation": translation_label,
            "completed": False,
        }
        self.current_turn_id = None
        self._refresh_wraplengths()
        self._scroll_to_bottom()

    def _promote_live_card(self, turn_id):
        if self.live_card is None:
            return False

        self.turn_cards[turn_id] = self.live_card
        self.live_card["completed"] = False
        self.live_card = None
        self.current_turn_id = turn_id
        return True

    def ensure_turn(self, turn_id, source_text=""):
        if turn_id is None:
            return

        if turn_id not in self.turn_cards:
            if not self._promote_live_card(turn_id):
                self._create_turn_card(turn_id, source_text)

        self.current_turn_id = turn_id

        if source_text:
            card = self.turn_cards[turn_id]
            card["source"].configure(text=source_text)
            self._refresh_wraplengths()
            self._scroll_to_bottom()

    def set_source_text(self, text, turn_id=None, final=False):
        text = (text or "").strip()

        if turn_id is None:
            self.live_source = text
            if self.live_card is None:
                self._create_live_card(text)
            else:
                self.live_card["source"].configure(text=text)
                self._refresh_wraplengths()
                self._scroll_to_bottom()
            return

        self.ensure_turn(turn_id)
        card = self.turn_cards[turn_id]
        card["source"].configure(text=text)
        self.current_turn_id = turn_id

        if final:
            card["completed"] = True

        self._refresh_wraplengths()
        self._scroll_to_bottom()

    def update_turn_translation(self, text, turn_id=None):
        # Keep leading spaces because the chunk bridge uses them as
        # placeholders for API requests that have not returned yet.
        text = (text or "").rstrip()

        if turn_id is None:
            turn_id = self.current_turn_id

        if turn_id is None:
            return

        self.ensure_turn(turn_id)
        card = self.turn_cards[turn_id]
        card["translation"].configure(text=text)
        self.current_turn_id = turn_id

        self._refresh_wraplengths()
        self._scroll_to_bottom()

    def complete_turn(self, turn_id):
        if turn_id is None:
            return

        card = self.turn_cards.get(turn_id)
        if card is None:
            return

        card["completed"] = True
        card["frame"].configure(
            highlightbackground=BORDER_COLOR,
        )

        if self.current_turn_id == turn_id:
            self.current_turn_id = None

    # ---------------------------------------------------------
    # Footer
    # ---------------------------------------------------------

    def _create_footer(self):
        footer = tk.Frame(
            self.root,
            bg=PANEL_BACKGROUND,
            padx=18,
            pady=10,
        )
        footer.pack(fill="x", padx=18, pady=(0, 18))

        left = tk.Frame(footer, bg=PANEL_BACKGROUND)
        left.pack(side="left", fill="x", expand=True)

        self.status_dot = tk.Label(
            left,
            text="●",
            bg=PANEL_BACKGROUND,
            fg=ACCENT_COLOR,
            font=("Arial", 13, "bold"),
        )
        self.status_dot.pack(side="left")

        self.status_label = tk.Label(
            left,
            text="LISTENING",
            bg=PANEL_BACKGROUND,
            fg=TEXT_COLOR,
            font=FONT_STATUS,
        )
        self.status_label.pack(side="left", padx=(5, 18))

        self.api_metric = tk.Label(
            left,
            text="API -- ms",
            bg=PANEL_BACKGROUND,
            fg=SECONDARY_TEXT,
            font=FONT_METRIC,
        )
        self.api_metric.pack(side="left", padx=6)

        self.total_metric = tk.Label(
            left,
            text="Total -- ms",
            bg=PANEL_BACKGROUND,
            fg=WARNING_COLOR,
            font=FONT_METRIC,
        )
        self.total_metric.pack(side="left", padx=6)

        controls = tk.Frame(footer, bg=PANEL_BACKGROUND)
        controls.pack(side="right")

        self.start_button = tk.Button(
            controls,
            text="START",
            command=self.start,
            bg=ACCENT_COLOR,
            fg="white",
            activebackground=ACCENT_COLOR,
            activeforeground="white",
            font=FONT_STATUS,
            relief="flat",
            padx=18,
            pady=6,
            bd=0,
        )
        self.start_button.pack(side="left")

        self.stop_button = tk.Button(
            controls,
            text="STOP",
            command=self.stop,
            bg=BUTTON_BACKGROUND,
            fg="white",
            activebackground=BUTTON_BACKGROUND,
            activeforeground="white",
            font=FONT_STATUS,
            relief="flat",
            padx=18,
            pady=6,
            bd=0,
        )
        self.stop_button.pack(side="left", padx=(8, 0))

    # ---------------------------------------------------------
    # Public UI functions
    # ---------------------------------------------------------

    def set_status(self, status):
        status = str(status).upper()
        self.status_label.config(text=status)

        if status.startswith("ERROR"):
            self.status_dot.config(fg="#E74C3C")
        elif status in {"LISTENING", "READY", "STARTING"}:
            self.status_dot.config(fg=ACCENT_COLOR)
        else:
            self.status_dot.config(fg=WARNING_COLOR)

    # Backward-compatible aliases.
    def set_translation(self, text, turn_id=None):
        self.update_turn_translation(text, turn_id=turn_id)

    def set_metrics(self, silence_ms=None, api_ms=None, total_ms=None):
        # Silence is intentionally not displayed in the reference-style footer.
        if api_ms is not None:
            self.api_metric.config(text=f"API {api_ms:.0f} ms")
        if total_ms is not None:
            self.total_metric.config(text=f"Total {total_ms:.0f} ms")

    def set_language_labels(self, source_language, target_language):
        self.source_language_label.config(
            text=self._language_name(source_language)
        )
        self.target_language_label.config(
            text=self._language_name(target_language)
        )

    @staticmethod
    def _language_name(code):
        names = {
            "en-US": "English",
            "en-IN": "English",
            "hi-IN": "Hindi",
            "hi": "Hindi",
        }
        return names.get(code, code)

    def set_bridge(self, bridge):
        self.bridge = bridge

        try:
            self.set_language_labels(
                bridge.source_language,
                bridge.target_language,
            )
        except AttributeError:
            pass

    def start(self):
        self.set_status("LISTENING")
        if self.bridge is not None:
            self.bridge.status("LISTENING")

    def stop(self):
        self.set_status("STOPPED")
        if self.bridge is not None:
            self.bridge.status("STOPPED")

    def run(self):
        self.root.mainloop()
