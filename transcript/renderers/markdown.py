from dataclasses import dataclass
from datetime import datetime
from transcript.model import Status, Role, Message, Transcript
from transcript.pricing import estimate_cost
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
        lines.append(f"- **Tool calls**: {ts.passed + ts.failed + ts.cancelled} ({ts.passed} passed, {ts.failed} failed)")
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
                msg_cost = estimate_cost(m.model or "", m.tokens_in, m.tokens_out, m.tokens_cached)
                header += (
                    f" \u00b7 \u2191{_fmt_tokens(m.tokens_in)} \u2193{_fmt_tokens(m.tokens_out)}"
                    f" \u00b7 {_fmt_cost(msg_cost)}"
                )
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
                        marker = "x " if tc.status == Status.FAILED else "~ " if tc.status == Status.CANCELLED else "  "
                        lines.append(f"{marker}{tc.display_name}: {tc.summary} \u2192 {tc.result_summary}")
                        if tc.result_full:
                            lines.append("")
                            lines.append("```")
                            lines.append(tc.result_full)
                            lines.append("```")
                        lines.append("")
                    else:
                        lines.append(f"`{tc.display_name}: {tc.summary} \u2192 {tc.result_summary}`")
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
                        marker = "x " if tc.status == Status.FAILED else "~ " if tc.status == Status.CANCELLED else "  "
                        lines.append(f"{marker}{tc.display_name}: {tc.summary} \u2192 {tc.result_summary}")
                        if tc.result_full:
                            lines.append("")
                            lines.append("```")
                            lines.append(tc.result_full)
                            lines.append("```")
                        lines.append("")
                else:
                    lines.append("```")
                    for tc in m.tool_calls:
                        lines.append(f"{tc.display_name}: {tc.summary} \u2192 {tc.result_summary}")
                    lines.append("```")
                    lines.append("")

    # Log-derived text may contain terminal control sequences; make them inert
    # once here so stdout, -o files and --pretty are all covered.
    return sanitize_text("\n".join(lines).rstrip() + "\n")
