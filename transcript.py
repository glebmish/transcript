"""Convert agent conversation logs to readable Markdown transcripts."""

import json
import re
import sys
import argparse
from dataclasses import dataclass, field
from datetime import datetime

# (input_price, output_price) per 1M tokens in USD
PRICING = {
    "claude-opus-4-6":        (15.00, 75.00),
    "claude-sonnet-4-6":      (3.00,  15.00),
    "claude-haiku-4-5":       (0.80,   4.00),
    "gemini-2.5-pro":         (1.25,  10.00),
    "gemini-2.5-flash":       (0.15,   0.60),
    "gemini-3-flash-preview": (0.15,   0.60),
}


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float | None:
    """Estimate cost in USD. Returns None if model is unknown."""
    for prefix, (in_price, out_price) in PRICING.items():
        if model == prefix or model.startswith(prefix):
            return tokens_in / 1_000_000 * in_price + tokens_out / 1_000_000 * out_price
    return None


@dataclass
class ToolCall:
    name: str
    summary: str       # key param, e.g. file path or command
    result: str        # compact result, e.g. "84 lines"
    passed: bool


@dataclass
class Message:
    role: str          # "user" or "assistant"
    timestamp: datetime
    model: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    thinking: list[str] = field(default_factory=list)
    text: list[str] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Claude Code parser
# ---------------------------------------------------------------------------

def _claude_tool_summary(name: str, input_data: dict) -> str:
    """Extract key param from a Claude tool_use input."""
    if name in ("Read", "Write", "Edit"):
        return input_data.get("file_path", "?")
    if name == "Bash":
        return input_data.get("description") or (input_data.get("command", "?")[:80])
    if name == "Grep":
        pat = input_data.get("pattern", "?")
        path = input_data.get("path", "")
        return f"{pat} in {path}" if path else pat
    if name == "Glob":
        return input_data.get("pattern", "?")
    if name in ("WebFetch", "WebSearch"):
        return input_data.get("url") or input_data.get("query") or "?"
    # Unknown tool: first string value
    for v in input_data.values():
        if isinstance(v, str) and v:
            return v[:80]
    return "?"


def _claude_tool_result(tool_use_result) -> tuple[str, bool]:
    """Extract compact result string and pass/fail from toolUseResult."""
    if isinstance(tool_use_result, str):
        short = tool_use_result.split("\n")[0][:50]
        return f"FAILED: {short}", False
    if isinstance(tool_use_result, dict):
        if "file" in tool_use_result:
            f = tool_use_result["file"]
            return f'{f.get("totalLines", "?")} lines', True
        if "filenames" in tool_use_result:
            return f'{tool_use_result.get("numFiles", "?")} files', True
        if "numMatches" in tool_use_result:
            return f'{tool_use_result["numMatches"]} matches', True
        if "url" in tool_use_result:
            code = tool_use_result.get("code", "?")
            return f"HTTP {code}", True
        if "exitCode" in tool_use_result:
            ec = tool_use_result["exitCode"]
            if ec != 0:
                return f"FAILED (exit {ec})", False
            return "ok", True
    return "ok", True


def parse_claude(path: str) -> list[Message]:
    """Parse a Claude Code JSONL log into a list of Messages."""
    messages: list[Message] = []
    current_assistant: Message | None = None
    pending_tool_uses: list[dict] = []
    seen_msg_id: str | None = None

    with open(path) as f:
        for line_str in f:
            line_str = line_str.strip()
            if not line_str:
                continue
            try:
                entry = json.loads(line_str)
            except json.JSONDecodeError:
                print("Warning: skipping malformed line", file=sys.stderr)
                continue

            entry_type = entry.get("type")
            if entry_type not in ("user", "assistant"):
                continue

            content = entry.get("message", {}).get("content", [])
            timestamp = entry.get("timestamp", "")

            try:
                ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                ts = datetime.min

            if entry_type == "user":
                if isinstance(content, list) and content and isinstance(content[0], dict):
                    block = content[0]
                    if block.get("type") == "tool_result":
                        is_error = block.get("is_error", False)
                        tool_use_result = entry.get("toolUseResult")
                        if pending_tool_uses:
                            tu = pending_tool_uses.pop(0)
                            summary = _claude_tool_summary(tu["name"], tu.get("input", {}))
                            result_str, passed = _claude_tool_result(tool_use_result)
                            if is_error:
                                passed = False
                                if not result_str.startswith("FAILED"):
                                    result_str = f"FAILED: {result_str}"
                            if current_assistant:
                                current_assistant.tool_calls.append(
                                    ToolCall(name=tu["name"], summary=summary, result=result_str, passed=passed)
                                )
                        continue

                # Actual user message
                if current_assistant:
                    messages.append(current_assistant)
                    current_assistant = None
                    pending_tool_uses = []
                    seen_msg_id = None

                text_content = ""
                if isinstance(content, str):
                    text_content = content
                elif isinstance(content, list):
                    text_content = " ".join(
                        b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
                    )
                if text_content.strip():
                    messages.append(Message(role="user", timestamp=ts, text=[text_content.strip()]))

            elif entry_type == "assistant":
                msg = entry.get("message", {})
                model = msg.get("model")
                usage = msg.get("usage", {})
                msg_id = msg.get("id")

                if current_assistant is None:
                    current_assistant = Message(role="assistant", timestamp=ts, model=model)
                    seen_msg_id = None

                if msg_id and msg_id != seen_msg_id:
                    current_assistant.tokens_in += usage.get("input_tokens", 0)
                    current_assistant.tokens_out += usage.get("output_tokens", 0)
                    if model:
                        current_assistant.model = model
                    seen_msg_id = msg_id

                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        btype = block.get("type")
                        if btype == "thinking":
                            thinking_text = block.get("thinking", "")
                            if thinking_text.strip():
                                current_assistant.thinking.append(thinking_text.strip())
                        elif btype == "text":
                            text = block.get("text", "")
                            if text.strip():
                                current_assistant.text.append(text.strip())
                        elif btype == "tool_use":
                            pending_tool_uses.append(block)

    if current_assistant:
        messages.append(current_assistant)

    return messages


# ---------------------------------------------------------------------------
# Gemini CLI parser
# ---------------------------------------------------------------------------

def _gemini_tool_summary(name: str, args: dict) -> str:
    """Extract key param from a Gemini tool call."""
    if name in ("read_file", "write_file", "edit_file", "read_many_files"):
        return args.get("file_path") or args.get("path") or args.get("paths", "?")
    if name in ("list_directory",):
        return args.get("dir_path", "?")
    if name == "run_shell_command":
        return args.get("description") or (args.get("command", "?")[:80])
    if name in ("search_files", "grep_search"):
        pat = args.get("pattern") or args.get("query") or "?"
        path = args.get("dir_path") or args.get("path") or ""
        return f"{pat} in {path}" if path else pat
    if name == "glob":
        return args.get("pattern", "?")
    if name in ("web_fetch", "web_search"):
        return args.get("url") or args.get("query") or "?"
    for v in args.values():
        if isinstance(v, str) and v:
            return v[:80]
    return "?"


def _gemini_tool_result(tc: dict) -> tuple[str, bool]:
    """Extract compact result and pass/fail from a Gemini toolCall."""
    result_display = tc.get("resultDisplay", "")
    result_data = tc.get("result", [])

    output = ""
    if result_data and isinstance(result_data, list):
        fr = result_data[0]
        if isinstance(fr, dict):
            resp = fr.get("functionResponse", {}).get("response", {})
            output = resp.get("output", "")

    if "Exit Code:" in output:
        ec_match = re.search(r"Exit Code:\s*(\d+)", output)
        if ec_match and ec_match.group(1) != "0":
            return f"FAILED (exit {ec_match.group(1)})", False

    if result_display:
        if len(result_display) <= 50 and "\n" not in result_display:
            return result_display, True
        lines = result_display.strip().split("\n")
        return f"{len(lines)} lines", True

    status = tc.get("status", "success")
    if status != "success":
        return "FAILED", False

    return "ok", True


def parse_gemini(path: str) -> list[Message]:
    """Parse a Gemini CLI JSON log into a list of Messages."""
    with open(path) as f:
        data = json.load(f)

    messages: list[Message] = []
    prev_input: int = 0  # track previous full input for delta calculation

    for entry in data.get("messages", []):
        msg_type = entry.get("type")
        timestamp = entry.get("timestamp", "")

        try:
            ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            ts = datetime.min

        if msg_type == "info":
            continue

        if msg_type == "user":
            content = entry.get("content", [])
            text = ""
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = " ".join(
                    item.get("text", "") for item in content if isinstance(item, dict)
                )
            if text.strip():
                messages.append(Message(role="user", timestamp=ts, text=[text.strip()]))

        elif msg_type == "gemini":
            tokens = entry.get("tokens", {})
            model = entry.get("model")
            full_input = tokens.get("input", 0)
            delta_input = full_input - prev_input if prev_input > 0 else full_input
            prev_input = full_input
            msg = Message(
                role="assistant",
                timestamp=ts,
                model=model,
                tokens_in=delta_input,
                tokens_out=tokens.get("output", 0),
            )

            content = entry.get("content", "")
            if isinstance(content, str) and content.strip():
                msg.text.append(content.strip())

            for thought in entry.get("thoughts", []):
                desc = thought.get("description", "")
                if desc.strip():
                    msg.thinking.append(desc.strip())

            for tc in entry.get("toolCalls", []):
                name = tc.get("displayName") or tc.get("name", "?")
                summary = _gemini_tool_summary(tc.get("name", ""), tc.get("args", {}))
                result_str, passed = _gemini_tool_result(tc)
                msg.tool_calls.append(ToolCall(name=name, summary=summary, result=result_str, passed=passed))

            messages.append(msg)

    return messages


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------

def _format_tokens(n: int) -> str:
    return f"{n:,}"


def _format_cost(cost: float | None) -> str:
    if cost is None:
        return "$?"
    if cost < 0.01:
        return f"${cost:.4f}"
    return f"${cost:.2f}"


def _format_duration(start: datetime, end: datetime) -> str:
    delta = end - start
    total_seconds = int(delta.total_seconds())
    if total_seconds < 0:
        return "0s"
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes > 0:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def _format_ts(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def render_markdown(messages: list[Message]) -> str:
    """Render messages to Markdown transcript."""
    if not messages:
        return "# Transcript\n\nNo messages.\n"

    lines: list[str] = []

    models = set()
    total_in = 0
    total_out = 0
    user_count = 0
    assistant_count = 0
    tool_passed = 0
    tool_failed = 0
    start_ts = messages[0].timestamp
    end_ts = messages[-1].timestamp

    for m in messages:
        if m.role == "user":
            user_count += 1
        else:
            assistant_count += 1
            total_in += m.tokens_in
            total_out += m.tokens_out
            if m.model:
                models.add(m.model)
        for tc in m.tool_calls:
            if tc.passed:
                tool_passed += 1
            else:
                tool_failed += 1

    total_cost = 0.0
    cost_known = True
    for m in messages:
        if m.role == "assistant" and m.model:
            c = estimate_cost(m.model, m.tokens_in, m.tokens_out)
            if c is not None:
                total_cost += c
            else:
                cost_known = False

    total_msgs = user_count + assistant_count
    total_tools = tool_passed + tool_failed

    # Summary header
    lines.append("# Transcript")
    lines.append("")
    lines.append(
        f"- **Duration**: {_format_duration(start_ts, end_ts)} "
        f"({_format_ts(start_ts)} \u2192 {_format_ts(end_ts)})"
    )
    lines.append(f"- **Model(s)**: {', '.join(sorted(models)) or 'unknown'}")
    lines.append(f"- **Messages**: {total_msgs} ({user_count} user, {assistant_count} assistant)")
    lines.append(f"- **Tool calls**: {total_tools} ({tool_passed} passed, {tool_failed} failed)")
    lines.append(
        f"- **Tokens**: \u2191{_format_tokens(total_in)} \u2193{_format_tokens(total_out)} \u00b7 "
        f"{_format_cost(total_cost) if cost_known else '$?'}"
    )

    # Messages
    for m in messages:
        lines.append("")
        lines.append("---")
        lines.append("")

        if m.role == "user":
            lines.append(f"## User \u00b7 {_format_ts(m.timestamp)}")
        else:
            msg_cost = estimate_cost(m.model or "", m.tokens_in, m.tokens_out)
            lines.append(
                f"## Assistant \u00b7 {_format_ts(m.timestamp)} \u00b7 "
                f"\u2191{_format_tokens(m.tokens_in)} \u2193{_format_tokens(m.tokens_out)} \u00b7 "
                f"{_format_cost(msg_cost)}"
            )

        lines.append("")

        # Thinking blocks
        for t in m.thinking:
            for tline in t.split("\n"):
                lines.append(f"> {tline}")
            lines.append("")

        # Text blocks
        for t in m.text:
            lines.append(t)
            lines.append("")

        # Tool calls in fenced code block
        if m.tool_calls:
            lines.append("```")
            for tc in m.tool_calls:
                lines.append(f"{tc.name}: {tc.summary} \u2192 {tc.result}")
            lines.append("```")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Convert agent logs to readable Markdown transcripts."
    )
    parser.add_argument(
        "-f", "--format", required=True, choices=["claude", "gemini"],
        help="Log format: claude (JSONL) or gemini (JSON)"
    )
    parser.add_argument("input", help="Path to log file")
    parser.add_argument("-o", "--output", help="Output file (default: stdout)")

    args = parser.parse_args()

    if args.format == "claude":
        messages = parse_claude(args.input)
    else:
        messages = parse_gemini(args.input)

    md = render_markdown(messages)

    if args.output:
        with open(args.output, "w") as f:
            f.write(md)
    else:
        sys.stdout.write(md)


if __name__ == "__main__":
    main()
