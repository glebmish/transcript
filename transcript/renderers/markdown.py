import re
from dataclasses import dataclass
from datetime import datetime
from transcript.model import Status, Role, ToolCall, Transcript
from transcript.parsers.common import is_real_model
from transcript.pricing import message_cost
from transcript.sanitize import sanitize_text


@dataclass
class RenderOptions:
    show_thinking: bool = True
    show_tools: bool = True
    show_text: bool = True
    show_cost: bool = True
    expand_tools: bool = False


def _fmt_tokens(n: int) -> str:
    return f"{n:,}"


def _fmt_cost(cost: float | None) -> str:
    if cost is None:
        return "$?"
    if cost < 0.01:
        return f"${cost:.4f}"
    return f"${cost:.2f}"


def _fmt_duration(start: datetime, end: datetime) -> str:
    total = int((end - start).total_seconds())
    if total < 0:
        return "0s"
    h, r = divmod(total, 3600)
    m, s = divmod(r, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


def _fmt_ts(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d %H:%M:%S")


_BACKTICK_RUN_RE = re.compile(r"`+")


def _longest_backtick_run(text: str) -> int:
    return max((len(run) for run in _BACKTICK_RUN_RE.findall(text)), default=0)


def _fence(content: str) -> str:
    """Code fence longer than any backtick run in content (minimum 3)."""
    return "`" * max(3, _longest_backtick_run(content) + 1)


def _inline_code(content: str) -> str:
    """Inline code span that log content cannot close early (CommonMark rules)."""
    ticks = "`" * (_longest_backtick_run(content) + 1)
    if content.startswith("`") or content.endswith("`"):
        content = f" {content} "
    return f"{ticks}{content}{ticks}"


def _expanded_tool_lines(tc: ToolCall) -> list[str]:
    marker = "x " if tc.status == Status.FAILED else "~ " if tc.status == Status.CANCELLED else "  "
    lines = [f"{marker}{tc.display_name}: {tc.summary} \u2192 {tc.result_summary}"]
    if tc.result_full:
        fence = _fence(tc.result_full)
        lines += ["", fence, tc.result_full, fence]
    lines.append("")
    return lines


def _role_label(role: Role) -> str:
    if role == Role.USER:
        return "User"
    if role == Role.ASSISTANT:
        return "Assistant"
    if role == Role.SYSTEM:
        return "System"
    if role == Role.DEVELOPER:
        return "Developer"
    return role.value.title()


def render(transcript: Transcript, options: RenderOptions | None = None) -> str:
    opts = options or RenderOptions()
    msgs = transcript.messages

    if not msgs:
        return "# Transcript\n\nNo messages.\n"

    lines: list[str] = []

    user_count = sum(1 for m in msgs if m.role == Role.USER and not m.is_compaction_marker and not m.command_name)
    asst_count = sum(1 for m in msgs if m.role == Role.ASSISTANT)
    total_msgs = user_count + asst_count
    ts = transcript.tool_stats

    lines.append("# Transcript")
    lines.append("")
    lines.append(
        f"- **Duration**: {_fmt_duration(transcript.start_time, transcript.end_time)} "
        f"({_fmt_ts(transcript.start_time)} \u2192 {_fmt_ts(transcript.end_time)})"
    )
    lines.append(f"- **Model(s)**: {', '.join(sorted(transcript.models)) or 'unknown'}")
    lines.append(f"- **Messages**: {total_msgs} ({user_count} user, {asst_count} assistant)")

    if opts.show_cost:
        cancelled_str = f", {ts.cancelled} cancelled" if ts.cancelled else ""
        lines.append(
            f"- **Tool calls**: {ts.passed + ts.failed + ts.cancelled} "
            f"({ts.passed} passed, {ts.failed} failed{cancelled_str})"
        )
        cost_str = _fmt_cost(transcript.total_cost)
        if transcript.cost_is_partial and transcript.total_cost is not None:
            cost_str += " (partial)"
        lines.append(
            f"- **Tokens**: \u2191{_fmt_tokens(transcript.total_tokens_in)} \u2193{_fmt_tokens(transcript.total_tokens_out)} \u00b7 {cost_str}"
        )

    for m in msgs:
        if m.is_compaction_marker:
            lines.append("")
            lines.append("--- conversation compacted ---")
            continue

        if m.command_name:
            lines.append("")
            lines.append(f"*`{m.command_name}` \u00b7 {_fmt_ts(m.timestamp)}*")
            continue

        lines.append("")
        lines.append("---")
        lines.append("")

        if m.role == Role.ASSISTANT:
            header = f"## Assistant \u00b7 {_fmt_ts(m.timestamp)}"
            if opts.show_cost:
                header += f" \u00b7 \u2191{_fmt_tokens(m.tokens_in)} \u2193{_fmt_tokens(m.tokens_out)}"
                # Placeholder models such as <synthetic> made no API call:
                # no cost, rather than an unknown "$?".
                if is_real_model(m.model):
                    msg_cost = message_cost(m)
                    header += f" \u00b7 {_fmt_cost(msg_cost)}"
            lines.append(header)
        else:
            lines.append(f"## {_role_label(m.role)} \u00b7 {_fmt_ts(m.timestamp)}")

        lines.append("")

        if m.role == Role.ASSISTANT and m.content_order:
            for kind, idx in m.content_order:
                if kind == "thinking" and opts.show_thinking and idx < len(m.thinking):
                    for tline in m.thinking[idx].split("\n"):
                        lines.append(f"> {tline}")
                    lines.append("")
                elif kind == "text" and opts.show_text and idx < len(m.text):
                    lines.append(m.text[idx])
                    lines.append("")
                elif kind == "tool" and opts.show_tools and idx < len(m.tool_calls):
                    tc = m.tool_calls[idx]
                    if opts.expand_tools:
                        lines.extend(_expanded_tool_lines(tc))
                    else:
                        lines.append(_inline_code(f"{tc.display_name}: {tc.summary} \u2192 {tc.result_summary}"))
                        lines.append("")
        else:
            if opts.show_thinking:
                for t in m.thinking:
                    for tline in t.split("\n"):
                        lines.append(f"> {tline}")
                    lines.append("")

            if opts.show_text:
                for t in m.text:
                    lines.append(t)
                    lines.append("")

            if opts.show_tools and m.tool_calls:
                if opts.expand_tools:
                    for tc in m.tool_calls:
                        lines.extend(_expanded_tool_lines(tc))
                else:
                    batch = "\n".join(
                        f"{tc.display_name}: {tc.summary} \u2192 {tc.result_summary}" for tc in m.tool_calls
                    )
                    fence = _fence(batch)
                    lines += [fence, batch, fence, ""]

    # Log-derived text may contain terminal control sequences; make them inert
    # once here so stdout, -o files and --pretty are all covered.
    return sanitize_text("\n".join(lines).rstrip() + "\n")
