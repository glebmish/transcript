from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.reactive import reactive
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
        Binding("h", "cycle_vis_0", "Show: all"),
        Binding("h", "cycle_vis_1", "Show: messages only"),
        Binding("h", "cycle_vis_2", "Show: user + tools"),
        Binding("up", "prev_block", "Up", show=False, priority=True),
        Binding("down", "next_block", "Down", show=False, priority=True),
        Binding("k", "prev_block", show=False),
        Binding("j", "next_block", show=False),
        Binding("tab", "switch_panel_right", "Panel: right", priority=True),
        Binding("tab", "switch_panel_left", "Panel: left", priority=True),
        Binding("slash", "open_search", "Search"),
        Binding("question_mark", "show_help", "Help"),
    ]

    _VISIBILITY_LABELS = ["all", "messages only", "user + tools"]

    _detail_active = reactive(False, bindings=True)
    _visibility_index = reactive(0, bindings=True)

    def __init__(self, transcript: Transcript):
        super().__init__()
        self.transcript = transcript
        self._search_visible = False
        self._last_conv_focus = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-split"):
            yield ConversationPanel(self.transcript)
            yield DetailPanel()
        yield Input(placeholder="Search...", id="search-bar")
        yield Footer()

    def on_mount(self):
        conv = self.query_one(ConversationPanel)
        conv.add_class("active")
        try:
            first = conv.query(_BLOCK_SELECTOR).first()
            first.focus()
        except Exception:
            pass

    def _get_blocks(self):
        return list(self.query_one(ConversationPanel).query(_BLOCK_SELECTOR))

    def _detail_is_active(self) -> bool:
        return self._detail_active

    def action_next_block(self):
        if self._detail_is_active():
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
        if self._detail_is_active():
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

    def _do_cycle_visibility(self):
        self._visibility_index = (self._visibility_index + 1) % 3
        self.query_one(ConversationPanel).set_visibility(self._visibility_index)

    def action_cycle_vis_0(self):
        self._do_cycle_visibility()

    def action_cycle_vis_1(self):
        self._do_cycle_visibility()

    def action_cycle_vis_2(self):
        self._do_cycle_visibility()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "switch_panel_right":
            return not self._detail_active
        if action == "switch_panel_left":
            return self._detail_active
        if action.startswith("cycle_vis_"):
            idx = int(action.split("_")[-1])
            return self._visibility_index == idx
        return True

    def _set_active_panel(self, panel: str):
        conv = self.query_one(ConversationPanel)
        detail = self.query_one(DetailPanel)
        if panel == "detail":
            conv.remove_class("active")
            detail.add_class("active")
        else:
            detail.remove_class("active")
            conv.add_class("active")

    def _switch_to_detail(self):
        detail = self.query_one(DetailPanel)
        self._last_conv_focus = self.focused
        detail.focus()
        self._detail_active = True
        self._set_active_panel("detail")

    def _switch_to_conv(self):
        conv = self.query_one(ConversationPanel)
        self._detail_active = False
        self._set_active_panel("conv")
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

    def action_switch_panel_right(self):
        self._switch_to_detail()

    def action_switch_panel_left(self):
        self._switch_to_conv()

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
