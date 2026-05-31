import textwrap
from textual.widgets import Static, Input
from textual.containers import VerticalScroll, Horizontal
from textual.content import Content
from rich.syntax import Syntax
from rich.markdown import Markdown
from transcript.model import Status, Role, Message, Transcript, ToolCall
from pathlib import Path


_POINTER = "\u25b6"  # ▶


class GutterRow(Horizontal):
    """A row with a fixed 2-char gutter + content. Focus lives on the row."""

    DEFAULT_CSS = """
    GutterRow {
        height: auto;
        padding: 0 1 0 0;
    }
    GutterRow > .gutter {
        width: 2;
        min-width: 2;
        max-width: 2;
        height: 1;
    }
    GutterRow > .content {
        width: 1fr;
    }
    GutterRow:focus > .gutter,
    GutterRow:focus > .content {
        background: #333333;
    }
    """

    def __init__(
        self,
        gutter_text: str,
        content,
        *,
        markup: bool = False,
        searchable_text: str | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._gutter_text = gutter_text
        self._content = content
        self._markup = markup
        self._searchable_text = searchable_text if searchable_text is not None else str(content)
        self.can_focus = True

    def compose(self):
        yield Static(self._gutter_text, classes="gutter", id=f"g-{id(self)}", markup=True)
        yield Static(
            self._content,
            classes="content",
            id=f"c-{id(self)}",
            markup=self._markup,
        )

    @property
    def searchable_text(self) -> str:
        return self._searchable_text

    def _gutter_widget(self):
        return self.query_one(f"#g-{id(self)}", Static)

    def _focused_gutter(self) -> str:
        return f"{_POINTER} "

    def on_focus(self):
        self._gutter_widget().update(self._focused_gutter())

    def on_blur(self):
        self._gutter_widget().update(self._gutter_text)


class MessageHeaderWidget(GutterRow):
    """A message header (User/Assistant) that can receive focus."""

    def __init__(self, content: str, **kwargs):
        super().__init__("  ", content, markup=True, **kwargs)
        self.styles.margin = (1, 0, 0, 0)


class MessageTextWidget(GutterRow):
    """A message text block that can receive focus."""

    def __init__(self, content: str, style: str | None = None, **kwargs):
        renderable = Content.assemble((content, style)) if style else content
        super().__init__("  ", renderable, searchable_text=content, **kwargs)


class ToolCallWidget(GutterRow):
    """A single tool call line that can be focused and expanded."""

    def __init__(self, tool_call: ToolCall, **kwargs):
        self.tool_call = tool_call
        if tool_call.status == Status.FAILED:
            gutter = "[red]\u2718[/red] "
        elif tool_call.status == Status.CANCELLED:
            gutter = "[yellow]~[/yellow] "
        else:
            gutter = "[grey50]\u2502[/grey50] "
        label = Content.assemble(
            (tool_call.display_name, "bold"),
            " ",
            tool_call.summary,
            " ",
            Content.from_markup(
                "[dim]\u2192 $summary  \\[>][/dim]",
                summary=tool_call.result_summary,
            ),
        )
        super().__init__(gutter, label, searchable_text=self.searchable_text, **kwargs)
        if tool_call.status == Status.FAILED:
            self.styles.color = "red"
        elif tool_call.status == Status.CANCELLED:
            self.styles.color = "yellow"

    @property
    def searchable_text(self) -> str:
        return f"{self.tool_call.display_name} {self.tool_call.summary} {self.tool_call.result_summary}"

    def _focused_gutter(self) -> str:
        if self.tool_call.status == Status.FAILED:
            return f"{_POINTER}[red]✘[/red]"
        if self.tool_call.status == Status.CANCELLED:
            return f"{_POINTER}[yellow]~[/yellow]"
        return f"{_POINTER} "


class ThinkingWidget(GutterRow):
    """A collapsible thinking block."""

    _GREY_BAR = "[grey50]\u2502[/grey50] "

    def __init__(self, text: str, **kwargs):
        self._full_text = text
        self._collapsed = True
        lines = text.strip().split("\n")
        self._line_count = len(lines)
        super().__init__(
            self._GREY_BAR,
            self._collapsed_text(),
            searchable_text=text,
            **kwargs,
        )

    def _collapsed_text(self):
        return Content.assemble((f"Thinking ({self._line_count} lines)  [>]", "dim italic"))

    def _expanded_text(self):
        lines = self._full_text.strip().split("\n")
        parts = [("Thinking", "dim italic"), "\n"]
        for idx, line in enumerate(lines):
            if idx:
                parts.append("\n")
            parts.append((line, "dim italic"))
        return Content.assemble(*parts)

    def _content_widget(self):
        return self.query_one(f"#c-{id(self)}", Static)

    def _current_text(self):
        return self._collapsed_text() if self._collapsed else self._expanded_text()

    def toggle(self):
        self._collapsed = not self._collapsed
        self._content_widget().update(self._current_text())

    @property
    def searchable_text(self) -> str:
        return self._full_text

    @property
    def collapsed(self):
        return self._collapsed


class ConversationPanel(VerticalScroll):
    """Left panel: scrollable conversation."""

    def __init__(self, transcript: Transcript, **kwargs):
        super().__init__(**kwargs)
        self.transcript = transcript
        self._visibility = 0  # 0=all, 1=messages only, 2=user+tools

    def compose(self):
        yield self._render_header()
        for msg in self.transcript.messages:
            if msg.is_compaction_marker:
                yield Static("  [dim]\u2500\u2500\u2500 conversation compacted \u2500\u2500\u2500[/dim]")
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

        user_c = sum(1 for m in t.messages if m.role == Role.USER and not m.is_compaction_marker and not m.command_name)
        asst_c = sum(1 for m in t.messages if m.role == Role.ASSISTANT)

        header = (
            f"  [bold]# Transcript[/bold]\n"
            f"  [dim]Duration: {dur} \u00b7 {model_str}\n"
            f"  Messages: {user_c + asst_c} \u00b7 Tools: {total_tools}{failed_str} \u00b7 {cost_str}[/dim]"
        )
        return Static(header)

    def _render_message(self, msg: Message):
        ts_str = msg.timestamp.strftime("%H:%M:%S")

        if msg.command_name:
            cmd_label = f"'{msg.command_name}' command" if msg.command_name != "(command output)" else "command output"
            yield MessageHeaderWidget(f"[bold green]## User ({cmd_label}) \u00b7 {ts_str}[/bold green]")
            for t in msg.text:
                dedented = "\n".join(line.strip() for line in t.splitlines())
                yield MessageTextWidget(dedented, style="magenta")
            return

        if msg.role == Role.USER:
            yield MessageHeaderWidget(f"[bold green]## User \u00b7 {ts_str}[/bold green]")
            for t in msg.text:
                yield MessageTextWidget(t)
            if self._visibility == 2:
                return
        else:
            # mode 2: skip assistant text, only show tool calls (in content order)
            if self._visibility == 2:
                if msg.content_order:
                    for kind, idx in msg.content_order:
                        if kind == "tool" and idx < len(msg.tool_calls):
                            yield ToolCallWidget(msg.tool_calls[idx])
                else:
                    for tc in msg.tool_calls:
                        yield ToolCallWidget(tc)
                return

            header = f"[bold cyan]## Assistant \u00b7 {ts_str}[/bold cyan]"
            if msg.tokens_in or msg.tokens_out:
                header += f" [dim]\u00b7 \u2191{msg.tokens_in:,} \u2193{msg.tokens_out:,}[/dim]"
            yield MessageHeaderWidget(header)

            # mode 1: messages only — skip thinking and tools
            if self._visibility == 1:
                for t in msg.text:
                    yield MessageTextWidget(t)
                return

            # Use content_order to preserve interleaved sequence
            if msg.content_order:
                for kind, idx in msg.content_order:
                    if kind == "thinking" and idx < len(msg.thinking):
                        yield ThinkingWidget(msg.thinking[idx])
                    elif kind == "text" and idx < len(msg.text):
                        yield MessageTextWidget(msg.text[idx])
                    elif kind == "tool" and idx < len(msg.tool_calls):
                        yield ToolCallWidget(msg.tool_calls[idx])
            else:
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
                self.mount(Static("  [dim]\u2500\u2500\u2500 conversation compacted \u2500\u2500\u2500[/dim]"))
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
        self.mount(Static(Content.assemble((f"{tc.display_name}: {tc.summary}", "bold"))))
        self.mount(Static(tc.result_summary, markup=False))
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
            self.mount(Static(tc.result_full, markup=False))

    def show_thinking(self, text: str):
        self.remove_children()
        self.mount(Static("[bold]Thinking[/bold]"))
        self.mount(Static(Content.assemble((text, "dim italic"))))

    def clear_detail(self):
        self.remove_children()
        self.mount(Static("[dim]Select a tool call or thinking block and press Enter to view details[/dim]"))
