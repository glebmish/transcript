from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer, Static, Input
from textual.containers import Horizontal
from textual.events import Key
from transcript.model import Transcript
from transcript.tui.widgets import (
    ConversationPanel, DetailPanel, ToolCallWidget, ThinkingWidget,
    MessageHeaderWidget, MessageTextWidget, GutterRow,
)

# All focusable block types in the conversation panel
_BLOCK_SELECTOR = "GutterRow"


class TranscriptApp(App):
    CSS = """
    #main-split { height: 1fr; }
    ConversationPanel { width: 2fr; overflow-y: auto; }
    DetailPanel { width: 1fr; overflow-y: auto; border: solid gray; }
    #search-bar { dock: bottom; display: none; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("t", "toggle_thinking", "Thinking"),
        Binding("h", "cycle_visibility", "Show: all"),
        Binding("up", "prev_block", "Up", show=False, priority=True),
        Binding("down", "next_block", "Down", show=False, priority=True),
        Binding("k", "prev_block", show=False),
        Binding("j", "next_block", show=False),
        Binding("tab", "switch_panel", "Panel", priority=True),
        Binding("slash", "open_search", "Search"),
        Binding("question_mark", "show_help", "Help"),
    ]

    _VISIBILITY_LABELS = ["all", "messages only", "user + tools"]

    def __init__(self, transcript: Transcript):
        super().__init__()
        self.transcript = transcript
        self._search_visible = False
        self._visibility_index = 0
        self._last_conv_focus = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-split"):
            yield ConversationPanel(self.transcript)
            yield DetailPanel()
        yield Input(placeholder="Search...", id="search-bar")
        yield Footer()

    def on_mount(self):
        # Auto-focus the first block
        conv = self.query_one(ConversationPanel)
        try:
            first = conv.query(_BLOCK_SELECTOR).first()
            first.focus()
        except Exception:
            pass

    def _get_blocks(self):
        return list(self.query_one(ConversationPanel).query(_BLOCK_SELECTOR))

    def action_next_block(self):
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
        self.bind("h", "cycle_visibility", description=f"Show: {label}")
        self.refresh_bindings()

    def action_switch_panel(self):
        conv = self.query_one(ConversationPanel)
        detail = self.query_one(DetailPanel)
        focused = self.focused
        # Going from conversation to detail
        if focused is not None and focused is not detail and focused not in detail.query("*"):
            self._last_conv_focus = focused
            detail.focus()
        else:
            # Going back to conversation — restore last position
            if self._last_conv_focus is not None:
                try:
                    self._last_conv_focus.focus()
                    self._last_conv_focus.scroll_visible()
                    return
                except Exception:
                    pass
            try:
                first = conv.query(_BLOCK_SELECTOR).first()
                first.focus()
            except Exception:
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
        self._search_visible = False
        try:
            first = self.query_one(ConversationPanel).query(_BLOCK_SELECTOR).first()
            first.focus()
        except Exception:
            pass

    def on_input_submitted(self, event: Input.Submitted):
        query = event.value.strip().lower()
        if not query:
            self._hide_search()
            return
        self._hide_search()
        conv = self.query_one(ConversationPanel)
        for widget in conv.query(_BLOCK_SELECTOR):
            text = widget.searchable_text.lower() if hasattr(widget, 'searchable_text') else ""
            if query in text:
                widget.focus()
                widget.scroll_visible()
                return

    def action_show_help(self):
        detail = self.query_one(DetailPanel)
        help_text = (
            "[bold]Keybindings[/bold]\n\n"
            "  Up/Down, j/k  Navigate between blocks\n"
            "  Enter         Expand focused item \u2192 detail panel\n"
            "  t             Toggle all thinking blocks\n"
            "  h             Cycle visibility: all \u2192 messages only \u2192 user+tools \u2192 all\n"
            "  /             Open search\n"
            "  Tab           Switch focus between panels\n"
            "  Esc           Close detail panel / search\n"
            "  q             Quit\n"
            "  ?             Show this help\n"
        )
        detail.remove_children()
        detail.mount(Static(help_text))
