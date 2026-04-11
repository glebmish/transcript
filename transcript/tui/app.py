from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static
from textual.containers import Horizontal
from textual.events import Key
from transcript.model import Transcript
from transcript.tui.widgets import ConversationPanel, DetailPanel, ToolCallWidget, ThinkingWidget


class TranscriptApp(App):
    CSS = """
    Horizontal { height: 1fr; }
    ConversationPanel { width: 2fr; overflow-y: auto; }
    DetailPanel { width: 1fr; overflow-y: auto; border: solid gray; }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("t", "toggle_thinking", "Thinking"),
        ("h", "cycle_visibility", "Hide"),
        ("tab", "focus_next", "Panel"),
        ("slash", "open_search", "Search"),
        ("question_mark", "show_help", "Help"),
    ]

    def __init__(self, transcript: Transcript):
        super().__init__()
        self.transcript = transcript
        self._help_visible = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield ConversationPanel(self.transcript)
            yield DetailPanel()
        yield Footer()

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
            self.query_one(DetailPanel).clear_detail()

    def action_toggle_thinking(self):
        self.query_one(ConversationPanel).toggle_thinking()

    def action_cycle_visibility(self):
        self.query_one(ConversationPanel).cycle_visibility()

    def action_open_search(self):
        pass  # TODO: search bar

    def action_show_help(self):
        detail = self.query_one(DetailPanel)
        help_text = (
            "[bold]Keybindings[/bold]\n\n"
            "  Up/Down, j/k  Scroll conversation\n"
            "  Enter          Expand focused item → detail panel\n"
            "  t              Toggle all thinking blocks\n"
            "  h              Cycle visibility: all → assistant → user → all\n"
            "  /              Open search\n"
            "  Tab            Switch focus between panels\n"
            "  Esc            Close detail panel / search\n"
            "  q              Quit\n"
            "  ?              Show this help\n"
        )
        detail.remove_children()
        detail.mount(Static(help_text))
