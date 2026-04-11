from textual.widgets import Static
from textual.containers import VerticalScroll
from rich.syntax import Syntax
from rich.markdown import Markdown
from transcript.model import Status, Role, Message, Transcript, ToolCall
from pathlib import Path


class ToolCallWidget(Static):
    """A single tool call line that can be focused and expanded."""

    def __init__(self, tool_call: ToolCall, **kwargs):
        self.tool_call = tool_call
        if tool_call.status == Status.FAILED:
            marker = "[red]x[/red] "
        elif tool_call.status == Status.CANCELLED:
            marker = "[yellow]~[/yellow] "
        else:
            marker = "  "
        label = (
            f"{marker}{tool_call.display_name}: {tool_call.summary} "
            f"\u2192 {tool_call.result_summary}  [dim]\\[>][/dim]"
        )
        super().__init__(label, **kwargs)
        self.can_focus = True
        if tool_call.status == Status.FAILED:
            self.styles.color = "red"
        elif tool_call.status == Status.CANCELLED:
            self.styles.color = "yellow"


class ThinkingWidget(Static):
    """A collapsible thinking block."""

    def __init__(self, text: str, **kwargs):
        self._full_text = text
        self._collapsed = True
        lines = text.strip().split("\n")
        self._line_count = len(lines)
        super().__init__(self._collapsed_text(), **kwargs)
        self.can_focus = True

    def _collapsed_text(self):
        return f"[dim italic]> Thinking ({self._line_count} lines)  \\[>][/dim italic]"

    def _expanded_text(self):
        lines = self._full_text.strip().split("\n")
        rendered = "\n".join(f"[dim italic]\u2502 {line}[/dim italic]" for line in lines)
        return f"[dim italic]v Thinking[/dim italic]\n{rendered}"

    def toggle(self):
        self._collapsed = not self._collapsed
        self.update(self._collapsed_text() if self._collapsed else self._expanded_text())

    @property
    def collapsed(self):
        return self._collapsed


class ConversationPanel(VerticalScroll):
    """Left panel: scrollable conversation."""

    def __init__(self, transcript: Transcript, **kwargs):
        super().__init__(**kwargs)
        self.transcript = transcript
        self._visibility = 0  # 0=all, 1=assistant, 2=user
        self.can_focus = True

    def compose(self):
        yield self._render_header()
        for msg in self.transcript.messages:
            if msg.is_compaction_marker:
                yield Static("[dim]\u2500\u2500\u2500 conversation compacted \u2500\u2500\u2500[/dim]")
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
            f"[bold]# Transcript[/bold]\n"
            f"[dim]Duration: {dur} \u00b7 {model_str}\n"
            f"Messages: {user_c + asst_c} \u00b7 Tools: {total_tools}{failed_str} \u00b7 {cost_str}[/dim]"
        )
        return Static(header)

    def _render_message(self, msg: Message):
        if self._visibility == 1 and msg.role == Role.USER:
            return
        if self._visibility == 2 and msg.role == Role.ASSISTANT:
            return

        ts_str = msg.timestamp.strftime("%H:%M:%S")
        if msg.role == Role.USER:
            yield Static(f"\n[bold blue]## User \u00b7 {ts_str}[/bold blue]")
            for t in msg.text:
                yield Static(t)
        else:
            header = f"\n[bold green]## Assistant \u00b7 {ts_str}[/bold green]"
            if msg.tokens_in or msg.tokens_out:
                header += f" [dim]\u00b7 ^{msg.tokens_in:,} v{msg.tokens_out:,}[/dim]"
            yield Static(header)

            for t in msg.thinking:
                yield ThinkingWidget(t)

            for t in msg.text:
                yield Static(t)

            for tc in msg.tool_calls:
                yield ToolCallWidget(tc)

    def toggle_thinking(self):
        for w in self.query(ThinkingWidget):
            w.toggle()

    def cycle_visibility(self):
        self._visibility = (self._visibility + 1) % 3
        self._refresh_content()

    def _refresh_content(self):
        self.remove_children()
        self.mount(self._render_header())
        for msg in self.transcript.messages:
            if msg.is_compaction_marker:
                self.mount(Static("[dim]\u2500\u2500\u2500 conversation compacted \u2500\u2500\u2500[/dim]"))
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
