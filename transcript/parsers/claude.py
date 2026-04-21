import json
import re
import sys
from datetime import datetime, timezone
from transcript.model import Status, Role, ToolCall, Message, ToolStats, Transcript
from transcript.pricing import estimate_cost

_MIN_TS = datetime.min.replace(tzinfo=timezone.utc)


def _parse_ts(raw: str) -> datetime:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return _MIN_TS


def _tool_summary(name: str, input_data: dict) -> str:
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
    if name == "Agent":
        return input_data.get("description") or (input_data.get("prompt", "?")[:80])
    if name == "Skill":
        return input_data.get("skill", "?")
    if name in ("TaskCreate", "TaskUpdate"):
        return input_data.get("subject") or input_data.get("taskId") or "?"
    for v in input_data.values():
        if isinstance(v, str) and v:
            return v[:80]
    return "?"


_CMD_NAME_RE = re.compile(r"<command-name>(.*?)</command-name>")


def _extract_command_name(content: str) -> str | None:
    """Extract slash command name from local_command content XML."""
    m = _CMD_NAME_RE.search(content)
    return m.group(1) if m else None


def _tool_result_summary(tool_use_result) -> tuple[str, Status]:
    if tool_use_result is None:
        return "ok", Status.PASSED
    if isinstance(tool_use_result, str):
        short = tool_use_result.split("\n")[0][:50]
        return f"FAILED: {short}", Status.FAILED
    if isinstance(tool_use_result, dict):
        if "file" in tool_use_result:
            f = tool_use_result["file"]
            return f'{f.get("totalLines", "?")} lines', Status.PASSED
        if "filenames" in tool_use_result:
            return f'{tool_use_result.get("numFiles", "?")} files', Status.PASSED
        if "numMatches" in tool_use_result:
            return f'{tool_use_result["numMatches"]} matches', Status.PASSED
        if "url" in tool_use_result:
            return f'HTTP {tool_use_result.get("code", "?")}', Status.PASSED
        if "exitCode" in tool_use_result:
            ec = tool_use_result["exitCode"]
            if ec != 0:
                return f"FAILED (exit {ec})", Status.FAILED
            return "ok", Status.PASSED
    return "ok", Status.PASSED


def _finalize_assistant(msg: Message) -> None:
    """Remove unresolved tool placeholders from content_order."""
    msg.content_order = [e for e in msg.content_order if e[1] != -1]


def parse(path: str) -> Transcript:
    messages: list[Message] = []
    current_assistant: Message | None = None
    current_msg_id: str | None = None
    pending_tool_uses: dict[str, dict] = {}
    # Maps tool_use id -> index in content_order where ("tool", ?) will go
    pending_tool_order: dict[str, int] = {}

    with open(path) as f:
        for line_num, line_str in enumerate(f, 1):
            line_str = line_str.strip()
            if not line_str:
                continue
            try:
                entry = json.loads(line_str)
            except json.JSONDecodeError:
                print(f"Warning: skipping malformed line {line_num}", file=sys.stderr)
                continue

            entry_type = entry.get("type")

            if entry_type == "system":
                subtype = entry.get("subtype", "")
                if subtype == "compact_boundary":
                    if current_assistant:
                        _finalize_assistant(current_assistant)
                        messages.append(current_assistant)
                        current_assistant = None
                        current_msg_id = None
                        pending_tool_uses = {}
                        pending_tool_order = {}
                    messages.append(Message(
                        role=Role.USER,
                        timestamp=_parse_ts(entry.get("timestamp", "")),
                        is_compaction_marker=True,
                        text=["Conversation compacted"],
                    ))
                elif subtype == "local_command":
                    cmd_name = _extract_command_name(entry.get("content", ""))
                    if cmd_name:
                        if current_assistant:
                            _finalize_assistant(current_assistant)
                            messages.append(current_assistant)
                            current_assistant = None
                            current_msg_id = None
                            pending_tool_uses = {}
                            pending_tool_order = {}
                        messages.append(Message(
                            role=Role.USER,
                            timestamp=_parse_ts(entry.get("timestamp", "")),
                            command_name=cmd_name,
                            text=[cmd_name],
                        ))
                elif subtype not in ("api_error", "turn_duration", "bridge_status"):
                    print(f"Warning: unknown system subtype '{subtype}' at line {line_num}", file=sys.stderr)
                continue

            if entry_type not in ("user", "assistant"):
                continue

            content = entry.get("message", {}).get("content", [])
            ts = _parse_ts(entry.get("timestamp", ""))

            if entry_type == "user":
                if isinstance(content, list) and content and isinstance(content[0], dict) and content[0].get("type") == "tool_result":
                    tool_use_result = entry.get("toolUseResult")
                    for block in content:
                        if not isinstance(block, dict) or block.get("type") != "tool_result":
                            continue
                        tool_use_id = block.get("tool_use_id", "")
                        is_error = block.get("is_error", False)
                        result_full = block.get("content", "")
                        if isinstance(result_full, list):
                            result_full = "\n".join(
                                b.get("text", "") for b in result_full if isinstance(b, dict)
                            )

                        if tool_use_id in pending_tool_uses:
                            tu = pending_tool_uses.pop(tool_use_id)
                            summary = _tool_summary(tu["name"], tu.get("input", {}))
                            result_str, status = _tool_result_summary(tool_use_result)
                            if is_error:
                                status = Status.FAILED
                                if not result_str.startswith("FAILED"):
                                    result_str = f"FAILED: {result_str}"
                            if current_assistant:
                                tool_idx = len(current_assistant.tool_calls)
                                current_assistant.tool_calls.append(ToolCall(
                                    name=tu["name"],
                                    display_name=tu["name"],
                                    summary=summary,
                                    result_summary=result_str,
                                    result_full=result_full,
                                    status=status,
                                ))
                                if tool_use_id in pending_tool_order:
                                    order_pos = pending_tool_order.pop(tool_use_id)
                                    current_assistant.content_order[order_pos] = ("tool", tool_idx)
                    continue

                # Actual user message
                if current_assistant:
                    _finalize_assistant(current_assistant)
                    messages.append(current_assistant)
                    current_assistant = None
                    current_msg_id = None
                    pending_tool_uses = {}
                    pending_tool_order = {}

                text_content = ""
                if isinstance(content, str):
                    text_content = content
                elif isinstance(content, list):
                    text_content = " ".join(
                        b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
                    )
                if text_content.strip():
                    cmd_name = _extract_command_name(text_content)
                    stripped = text_content.strip()
                    if not cmd_name and (stripped.startswith("<local-command-caveat>") or stripped.startswith("<local-command-stdout>")):
                        cmd_name = "(command output)"
                    messages.append(Message(
                        role=Role.USER,
                        timestamp=ts,
                        text=[stripped],
                        command_name=cmd_name,
                    ))

            elif entry_type == "assistant":
                msg = entry.get("message", {})
                model = msg.get("model")
                usage = msg.get("usage", {})
                msg_id = msg.get("id")

                # Start a new Message when msg_id changes (or no current assistant).
                # Multiple streaming entries share msg_id: merge those with max().
                # Distinct msg_ids are separate assistant turns: sum across them.
                if current_assistant is None or (msg_id and msg_id != current_msg_id):
                    if current_assistant is not None:
                        _finalize_assistant(current_assistant)
                        messages.append(current_assistant)
                    current_assistant = Message(role=Role.ASSISTANT, timestamp=ts, model=model)
                    current_msg_id = msg_id

                # Claude's usage breakdown:
                #   input_tokens = uncached, non-cache-write input (the billable portion)
                #   cache_creation_input_tokens = tokens written to cache (treated as free)
                #   cache_read_input_tokens = tokens read from cache (free)
                #
                # tokens_in = total context = input + cache_creation + cache_read
                # tokens_cached = cache_read + cache_creation (everything not charged)
                # billable = tokens_in - tokens_cached = input_tokens
                if msg_id:
                    raw_input = usage.get("input_tokens", 0)
                    cache_creation = usage.get("cache_creation_input_tokens", 0)
                    cache_read = usage.get("cache_read_input_tokens", 0)
                    total_in = raw_input + cache_creation + cache_read
                    total_cached = cache_creation + cache_read

                    current_assistant.tokens_in = max(current_assistant.tokens_in, total_in)
                    current_assistant.tokens_out = max(current_assistant.tokens_out, usage.get("output_tokens", 0))
                    current_assistant.tokens_cached = max(current_assistant.tokens_cached, total_cached)
                    if model:
                        current_assistant.model = model

                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        btype = block.get("type")
                        if btype == "thinking":
                            text = block.get("thinking", "")
                            if text.strip():
                                idx = len(current_assistant.thinking)
                                current_assistant.thinking.append(text.strip())
                                current_assistant.content_order.append(("thinking", idx))
                        elif btype == "text":
                            text = block.get("text", "")
                            if text.strip():
                                idx = len(current_assistant.text)
                                current_assistant.text.append(text.strip())
                                current_assistant.content_order.append(("text", idx))
                        elif btype == "tool_use":
                            tu_id = block.get("id", "")
                            pending_tool_uses[tu_id] = block
                            # Reserve a slot; will be filled when result arrives
                            pending_tool_order[tu_id] = len(current_assistant.content_order)
                            current_assistant.content_order.append(("tool", -1))

    if current_assistant:
        for tu_id, tu in pending_tool_uses.items():
            tool_idx = len(current_assistant.tool_calls)
            current_assistant.tool_calls.append(ToolCall(
                name=tu["name"],
                display_name=tu["name"],
                summary=_tool_summary(tu["name"], tu.get("input", {})),
                result_summary="no result",
                result_full="",
                status=Status.FAILED,
            ))
            if tu_id in pending_tool_order:
                order_pos = pending_tool_order[tu_id]
                current_assistant.content_order[order_pos] = ("tool", tool_idx)
        _finalize_assistant(current_assistant)
        messages.append(current_assistant)

    return _build_transcript(messages)


def _build_transcript(messages: list[Message]) -> Transcript:
    models: set[str] = set()
    total_in = total_out = 0
    passed = failed = cancelled = 0
    total_cost = 0.0
    cost_is_partial = False

    for m in messages:
        if m.is_compaction_marker:
            continue
        if m.role == Role.ASSISTANT and m.model:
            models.add(m.model)
        total_in += m.tokens_in
        total_out += m.tokens_out
        for tc in m.tool_calls:
            if tc.status == Status.PASSED:
                passed += 1
            elif tc.status == Status.FAILED:
                failed += 1
            elif tc.status == Status.CANCELLED:
                cancelled += 1

    for m in messages:
        if m.role == Role.ASSISTANT and m.model:
            c = estimate_cost(m.model, m.tokens_in, m.tokens_out, m.tokens_cached)
            if c is not None:
                total_cost += c
            else:
                cost_is_partial = True

    non_marker = [m for m in messages if not m.is_compaction_marker]
    start = non_marker[0].timestamp if non_marker else _MIN_TS
    end = non_marker[-1].timestamp if non_marker else _MIN_TS

    if not models or (cost_is_partial and total_cost == 0.0):
        final_cost = None
    else:
        final_cost = total_cost

    return Transcript(
        messages=messages,
        source_format="claude",
        session_id=None,
        start_time=start,
        end_time=end,
        models=models,
        total_tokens_in=total_in,
        total_tokens_out=total_out,
        total_cost=final_cost,
        cost_is_partial=cost_is_partial,
        tool_stats=ToolStats(passed=passed, failed=failed, cancelled=cancelled),
    )
