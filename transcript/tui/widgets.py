from textual.widgets import Static, Input
from textual.containers import VerticalScroll
from rich.syntax import Syntax
from rich.markdown import Markdown
from transcript.model import Status, Role, Message, Transcript, ToolCall
from pathlib import Path


_GUTTER = "  "  # 2-space gutter, replaced by ▶ on focus
_POINTER = "\u25b6 "


class _FocusableBlock(Static):
    """Base for blocks that show a pointer when focused."""

    def __init__(self, content: str, **kwargs):
        self._raw_content = content
        super().__init__(_GUTTER + content, **kwargs)
        self.can_focus = True

    @property
    def searchable_text(self) -> str:
        return self._raw_content

    def on_focus(self):
        self.update(_POINTER + self._raw_content)
        self.styles.background = "#333333"

    def on_blur(self):
        self.update(_GUTTER + self._raw_content)
        self.styles.background = "transparent"


class MessageHeaderWidget(_FocusableBlock):
    """A message header (User/Assistant) that can receive focus."""

    def __init__(self, content: str, **kwargs):
        # Strip leading newline — rendered as margin-top instead
        self._raw_content = content.lstrip("\n")
        super(_FocusableBlock, self).__init__(_GUTTER + self._raw_content, **kwargs)
        self.can_focus = True
        self.styles.margin = (1, 0, 0, 0)


class MessageTextWidget(_FocusableBlock):
    """A message text block that can receive focus."""
    pass


class ToolCallWidget(Static):
    """A single tool call line that can be focused and expanded."""

    def __init__(self, tool_call: ToolCall, **kwargs):
        self.tool_call = tool_call
        if tool_call.status == Status.FAILED:
            marker = "[red]\u2718[/red]"
        elif tool_call.status == Status.CANCELLED:
            marker = "[yellow]~[/yellow]"
        else:
            marker = "[dim]\u2502[/dim]"
        self._marker = marker
        self._label = (
            f"[bold]{tool_call.display_name}[/bold] {tool_call.summary} "
            f"[dim]\u2192 {tool_call.result_summary}  \\[>][/dim]"
        )
        super().__init__(f"{marker} {self._label}", **kwargs)
        self.can_focus = True
        if tool_call.status == Status.FAILED:
            self.styles.color = "red"
        elif tool_call.status == Status.CANCELLED:
            self.styles.color = "yellow"

    @property
    def searchable_text(self) -> str:
        return f"{self.tool_call.display_name} {self.tool_call.summary} {self.tool_call.result_summary}"

    def on_focus(self):
        self.update(f"{_POINTER}{self._label}")
        self.styles.background = "#333333"

    def on_blur(self):
        self.update(f"{self._marker} {self._label}")
        self.styles.background = "transparent"


class ThinkingWidget(Static):
    """A collapsible thinking block."""

    def __init__(self, text: str, **kwargs):
        self._full_text = text
        self._collapsed = True
        lines = text.strip().split("\n")
        self._line_count = len(lines)
        super().__init__(_GUTTER + self._collapsed_text(), **kwargs)
        self.can_focus = True

    def _collapsed_text(self):
        return f"[grey50]\u2502[/grey50] [dim italic]Thinking ({self._line_count} lines)  \\[>][/dim italic]"

    def _expanded_text(self):
        lines = self._full_text.strip().split("\n")
        rendered = "\n".join(f"  [grey50]\u2502[/grey50] [dim italic]{line}[/dim italic]" for line in lines)
        return f"[grey50]\u2502[/grey50] [dim italic]Thinking[/dim italic]\n{rendered}"

    def _current_text(self):
        return self._collapsed_text() if self._collapsed else self._expanded_text()

    def toggle(self):
        self._collapsed = not self._collapsed
        self.update(_GUTTER + self._current_text())

    @property
    def searchable_text(self) -> str:
        return self._full_text

    def on_focus(self):
        self.update(_POINTER + self._current_text())
        self.styles.background = "#333333"

    def on_blur(self):
        self.update(_GUTTER + self._current_text())
        self.styles.background = "transparent"

    @property
    def collapsed(self):
        return self._collapsed


class ConversationPanel(VerticalScroll):
    """Left panel: scrollable conversation."""

    def __init__(self, transcript: Transcript, **kwargs):
        super().__init__(**kwargs)
        self.transcript = transcript
        self._visibility = 0  # 0=all, 1=assistant, 2=user

    def compose(self):
        yield self._render_header()
        for msg in self.transcript.messages:
            if msg.is_compaction_marker:
                yield Static(f"{_GUTTER}[dim]\u2500\u2500\u2500 conversation compacted \u2500\u2500\u2500[/dim]")
                continue
            yield from self._render_message(msg)

    def _render_header(self):
        t = self.transcript
        ts = t.tool_stats
        total_tools = ts.passed + ts.failed + ts.cancelled
        failed_str = f" ({ts.failed} x)" if ts.failed else ""

        if t.total_cost is not None:
            cost_str = f"${t.total_cost:.2f}" if t.total_cost >= 0.01 else f"${t.total_cost:.4f}"
            if t.cost_is_partial:
                cost_str += " (partial)"
        else:
            cost_str = "$?"

        model_str = ", ".join(sorted(t.models)) or "unknown"
        delta = t.end_time - t.start_time
        total_s = int(delta.total_seconds())
        if total_s >= 3600:
            dur = f"{total_s // 3600}h {(total_s % 3600) // 60}m"
        elif total_s >= 60:
            dur = f"{total_s // 60}m {total_s % 60}s"
        else:
            dur = f"{total_s}s"

        user_c = sum(1 for m in t.messages if m.role == Role.USER and not m.is_compaction_marker)
        asst_c = sum(1 for m in t.messages if m.role == Role.ASSISTANT)

        header = (
            f"{_GUTTER}[bold]# Transcript[/bold]\n"
            f"{_GUTTER}[dim]Duration: {dur} \u00b7 {model_str}\n"
            f"{_GUTTER}Messages: {user_c + asst_c} \u00b7 Tools: {total_tools}{failed_str} \u00b7 {cost_str}[/dim]"
        )
        return Static(header)

    def _render_message(self, msg: Message):
        ts_str = msg.timestamp.strftime("%H:%M:%S")
        if msg.role == Role.USER:
            yield MessageHeaderWidget(f"\n[bold green]## User \u00b7 {ts_str}[/bold green]")
            for t in msg.text:
                yield MessageTextWidget(t)
            # mode 2: user messages + tools — show tool calls after user turns too
            if self._visibility == 2:
                return
        else:
            # mode 2: skip assistant text, only show tool calls
            if self._visibility == 2:
                for tc in msg.tool_calls:
                    yield ToolCallWidget(tc)
                return

            header = f"\n[bold cyan]## Assistant \u00b7 {ts_str}[/bold cyan]"
            if msg.tokens_in or msg.tokens_out:
                header += f" [dim]\u00b7 ^{msg.tokens_in:,} v{msg.tokens_out:,}[/dim]"
            yield MessageHeaderWidget(header)

            # mode 1: messages only — skip thinking and tools
            if self._visibility == 1:
                for t in msg.text:
                    yield MessageTextWidget(t)
                return

            for t in msg.thinking:
                yield ThinkingWidget(t)

            for t in msg.text:
                yield MessageTextWidget(t)

            for tc in msg.tool_calls:
                yield ToolCallWidget(tc)

    def toggle_thinking(self):
        for w in self.query(ThinkingWidget):
            w.toggle()

    def set_visibility(self, mode: int):
        self._visibility = mode
        self._refresh_content()

    def _refresh_content(self):
        self.remove_children()
        self.mount(self._render_header())
        for msg in self.transcript.messages:
            if msg.is_compaction_marker:
                self.mount(Static(f"{_GUTTER}[dim]\u2500\u2500\u2500 conversation compacted \u2500\u2500\u2500[/dim]"))
                continue
            for w in self._render_message(msg):
                self.mount(w)


class DetailPanel(VerticalScroll):
    """Right panel: detail view for expanded tool output or file contents."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.can_focus = True

    def compose(self):
        yield Static("[dim]Select a tool call or thinking block and press Enter to view details[/dim]")

    def show_tool_call(self, tc: ToolCall):
        self.remove_children()
        self.mount(Static(f"[bold]{tc.display_name}: {tc.summary}[/bold]"))
        self.mount(Static(tc.result_summary))
        if tc.result_full:
            ext = Path(tc.summary).suffix if "/" in tc.summary else ""
            if ext in (".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java", ".rb",
                        ".sh", ".yaml", ".yml", ".toml", ".json", ".css", ".html"):
                try:
                    self.mount(Static(Syntax(tc.result_full, ext.lstrip("."), theme="monokai")))
                    return
                except Exception:
                    pass
            if ext == ".md":
                try:
                    self.mount(Static(Markdown(tc.result_full)))
                    return
                except Exception:
                    pass
            self.mount(Static(tc.result_full))

    def show_thinking(self, text: str):
        self.remove_children()
        self.mount(Static("[bold]Thinking[/bold]"))
        self.mount(Static(f"[dim italic]{text}[/dim italic]"))

    def clear_detail(self):
        self.remove_children()
        self.mount(Static("[dim]Select a tool call or thinking block and press Enter to view details[/dim]"))
