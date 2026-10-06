from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.reactive import reactive
from textual.widgets import Header, Footer, Static, Input
from textual.containers import Horizontal
from textual.events import Key
from textual.markup import escape
from transcript.model import Transcript
from transcript.sanitize import sanitize_transcript
from transcript.tui.widgets import (
    ConversationPanel, DetailPanel, ToolCallWidget, ThinkingWidget,
)

# All focusable block types in the conversation panel
_BLOCK_SELECTOR = "GutterRow"


class TranscriptApp(App):
    CSS = """
    #main-split { height: 1fr; }
    ConversationPanel { width: 2fr; overflow-y: auto; border: solid dimgray; }
    ConversationPanel.active { border: solid dodgerblue; }
    DetailPanel { width: 1fr; overflow-y: auto; border: solid dimgray; }
    DetailPanel.active { border: solid dodgerblue; }
    #search-bar { dock: bottom; display: none; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+c", "quit", show=False),
        Binding("t", "toggle_thinking", "Thinking"),
        Binding("h", "cycle_visibility", "Show: all"),
        Binding("up", "prev_block", "Up", show=False, priority=True),
        Binding("down", "next_block", "Down", show=False, priority=True),
        Binding("k", "prev_block", show=False),
        Binding("j", "next_block", show=False),
        Binding("tab", "switch_panel_right", "Panel: right", priority=True),
        Binding("tab", "switch_panel_left", "Panel: left", priority=True),
        Binding("slash", "open_search", "Search"),
        Binding("n", "next_match", show=False),
        Binding("N", "prev_match", show=False),
        Binding("question_mark", "show_help", "Help"),
    ]

    _VISIBILITY_LABELS = ["all", "messages only", "user + tools"]

    _detail_active = reactive(False, bindings=True)

    def __init__(self, transcript: Transcript):
        super().__init__()
        # Sanitize once so no widget can emit raw control characters from the log.
        self.transcript = sanitize_transcript(transcript)
        self._search_visible = False
        self._visibility_index = 0
        self._last_conv_focus = None
        self._last_query: str | None = None
        self._last_match_index: int = -1

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-split"):
            yield ConversationPanel(self.transcript)
            yield DetailPanel()
        yield Input(placeholder="Search...", id="search-bar")
        yield Footer()

    def on_mount(self):
        self.query_one(ConversationPanel).add_class("active")
        self._focus_first_block()

    def _focus_first_block(self) -> bool:
        try:
            first = self.query_one(ConversationPanel).query(_BLOCK_SELECTOR).first()
            first.focus()
            return True
        except Exception:
            return False

    def _get_blocks(self):
        return list(self.query_one(ConversationPanel).query(_BLOCK_SELECTOR))

    def action_next_block(self):
        if self._detail_active:
            self.query_one(DetailPanel).scroll_down(animate=False)
            return
        blocks = self._get_blocks()
        if not blocks:
            return
        focused = self.focused
        if focused in blocks:
            idx = blocks.index(focused)
            if idx < len(blocks) - 1:
                blocks[idx + 1].focus()
                blocks[idx + 1].scroll_visible()
        else:
            blocks[0].focus()
            blocks[0].scroll_visible()

    def action_prev_block(self):
        if self._detail_active:
            self.query_one(DetailPanel).scroll_up(animate=False)
            return
        blocks = self._get_blocks()
        if not blocks:
            return
        focused = self.focused
        if focused in blocks:
            idx = blocks.index(focused)
            if idx > 0:
                blocks[idx - 1].focus()
                blocks[idx - 1].scroll_visible()
        else:
            blocks[-1].focus()
            blocks[-1].scroll_visible()

    def on_key(self, event: Key):
        if event.key == "enter":
            focused = self.focused
            if isinstance(focused, ToolCallWidget):
                self.query_one(DetailPanel).show_tool_call(focused.tool_call)
            elif isinstance(focused, ThinkingWidget):
                if focused.collapsed:
                    focused.toggle()
                else:
                    self.query_one(DetailPanel).show_thinking(focused._full_text)
        elif event.key == "escape":
            if self._search_visible:
                self._hide_search()
            else:
                self.query_one(DetailPanel).clear_detail()

    def action_toggle_thinking(self):
        self.query_one(ConversationPanel).toggle_thinking()

    def action_cycle_visibility(self):
        self._visibility_index = (self._visibility_index + 1) % 3
        label = self._VISIBILITY_LABELS[self._visibility_index]
        self.query_one(ConversationPanel).set_visibility(self._visibility_index)
        # Replace the 'h' Binding in the active bindings map so the Footer
        # re-renders with the new description on refresh_bindings().
        new_binding = Binding("h", "cycle_visibility", f"Show: {label}")
        for bindings_map in (self._bindings, self.screen._bindings):
            if "h" in bindings_map.key_to_bindings:
                bindings_map.key_to_bindings["h"] = [
                    new_binding if b.action == "cycle_visibility" else b
                    for b in bindings_map.key_to_bindings["h"]
                ]
        self.refresh_bindings()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "switch_panel_right":
            return not self._detail_active
        if action == "switch_panel_left":
            return self._detail_active
        return True

    def action_switch_panel_right(self):
        conv = self.query_one(ConversationPanel)
        detail = self.query_one(DetailPanel)
        self._last_conv_focus = self.focused
        detail.focus()
        self._detail_active = True
        conv.remove_class("active")
        detail.add_class("active")

    def action_switch_panel_left(self):
        conv = self.query_one(ConversationPanel)
        detail = self.query_one(DetailPanel)
        self._detail_active = False
        detail.remove_class("active")
        conv.add_class("active")
        if self._last_conv_focus is not None:
            try:
                self._last_conv_focus.focus()
                self._last_conv_focus.scroll_visible()
                return
            except Exception:
                self._last_conv_focus = None
        if not self._focus_first_block():
            conv.focus()

    def action_open_search(self):
        if self._search_visible:
            self._hide_search()
        else:
            search = self.query_one("#search-bar", Input)
            search.styles.display = "block"
            search.focus()
            self._search_visible = True

    def _hide_search(self):
        search = self.query_one("#search-bar", Input)
        search.styles.display = "none"
        search.value = ""
        search.border_title = ""
        self._search_visible = False
        self._focus_first_block()

    def _find_matches(self, query: str):
        conv = self.query_one(ConversationPanel)
        return [
            w for w in conv.query(_BLOCK_SELECTOR)
            if hasattr(w, "searchable_text") and query in w.searchable_text.lower()
        ]

    def on_input_submitted(self, event: Input.Submitted):
        query = event.value.strip().lower()
        if not query:
            self._hide_search()
            return
        matches = self._find_matches(query)
        search = self.query_one("#search-bar", Input)
        if not matches:
            self._last_query = None
            self._last_match_index = -1
            search.border_title = escape(f"(0 results for {query!r})")
            return
        self._last_query = query
        self._last_match_index = 0
        self._hide_search()
        matches[0].focus()
        matches[0].scroll_visible()

    def _jump_match(self, delta: int):
        if not self._last_query:
            return
        matches = self._find_matches(self._last_query)
        if not matches:
            return
        self._last_match_index = (self._last_match_index + delta) % len(matches)
        matches[self._last_match_index].focus()
        matches[self._last_match_index].scroll_visible()

    def action_next_match(self):
        self._jump_match(1)

    def action_prev_match(self):
        self._jump_match(-1)

    def action_show_help(self):
        detail = self.query_one(DetailPanel)
        help_text = (
            "[bold]Keybindings[/bold]\n\n"
            "  Up/Down, j/k  Navigate between blocks (scroll in detail panel)\n"
            "  Enter         Expand focused item \u2192 detail panel\n"
            "  t             Toggle all thinking blocks\n"
            "  h             Cycle visibility: all \u2192 messages only \u2192 user+tools \u2192 all\n"
            "  /             Open search\n"
            "  n / N         Next / previous search match\n"
            "  Tab           Switch focus between panels\n"
            "  Esc           Close detail panel / search\n"
            "  q, Ctrl+C     Quit\n"
            "  ?             Show this help\n"
        )
        detail.remove_children()
        detail.mount(Static(help_text))
