import json
import re
import sys
from datetime import datetime, timezone
from transcript.model import Status, Role, ToolCall, Message, ToolStats, Transcript
from transcript.pricing import estimate_cost
from transcript.parsers.common import as_dict, as_int, as_str

_MIN_TS = datetime.min.replace(tzinfo=timezone.utc)


def _parse_ts(raw: str) -> datetime:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return _MIN_TS


def _tool_summary(name: str, input_data) -> str:
    input_data = as_dict(input_data)

    def arg(key: str) -> str:
        return as_str(input_data.get(key))

    if name in ("Read", "Write", "Edit"):
        return arg("file_path") or "?"
    if name == "Bash":
        return arg("description") or (arg("command") or "?")[:80]
    if name == "Grep":
        pat = arg("pattern") or "?"
        path = arg("path")
        return f"{pat} in {path}" if path else pat
    if name == "Glob":
        return arg("pattern") or "?"
    if name in ("WebFetch", "WebSearch"):
        return arg("url") or arg("query") or "?"
    if name == "Agent":
        return arg("description") or (arg("prompt") or "?")[:80]
    if name == "Skill":
        return arg("skill") or "?"
    if name in ("TaskCreate", "TaskUpdate"):
        return arg("subject") or str(input_data.get("taskId") or "?")
    if name == "AskUserQuestion":
        questions = input_data.get("questions", "?")
        if isinstance(questions, list) and questions:
            return str(questions[0])[:80]
        return str(questions)[:80]
    if name == "StructuredOutput":
        return arg("recap_short") or arg("goal") or (arg("prose") or "?")[:80]
    if name == "ToolSearch":
        return arg("query") or "?"
    if name == "Monitor":
        return arg("description") or (arg("command") or "?")[:80]
    if name == "Workflow":
        return arg("scriptPath") or (arg("script") or "?")[:80]
    if name == "TaskStop":
        return str(input_data.get("task_id") or "?")
    if name == "TaskList":
        return "tasks"
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
            f = as_dict(tool_use_result["file"])
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


def _result_text(content) -> str:
    """Flatten a tool_result content payload (string, block list, or other) to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(as_str(b.get("text")) for b in content if isinstance(b, dict))
    if content is None:
        return ""
    return json.dumps(content, indent=2, sort_keys=True, default=str)


def _finalize_assistant(msg: Message) -> None:
    """Remove unresolved tool placeholders from content_order."""
    msg.content_order = [e for e in msg.content_order if e[1] != -1]


def _flush_pending_tool_uses(
    msg: Message,
    pending_tool_uses: dict[str, dict],
    pending_tool_order: dict[str, int],
) -> None:
    """Record any tool_uses that never got a tool_result as FAILED on their owning assistant.

    Must be called on the assistant that emitted the tool_uses — content_order slots
    were reserved against that message's content_order.
    """
    for tu_id, tu in pending_tool_uses.items():
        tool_idx = len(msg.tool_calls)
        msg.tool_calls.append(ToolCall(
            name=tu["name"],
            display_name=tu["name"],
            summary=_tool_summary(tu["name"], tu.get("input")),
            result_summary="no result",
            result_full="",
            status=Status.FAILED,
        ))
        if tu_id in pending_tool_order:
            order_pos = pending_tool_order[tu_id]
            msg.content_order[order_pos] = ("tool", tool_idx)


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
            except (json.JSONDecodeError, RecursionError):
                print(f"Warning: skipping malformed line {line_num}", file=sys.stderr)
                continue
            if not isinstance(entry, dict):
                print(f"Warning: skipping non-object line {line_num}", file=sys.stderr)
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
                    raw_content = as_str(entry.get("content"))
                    cmd_name = _extract_command_name(raw_content)
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
                            text=[raw_content or cmd_name],
                        ))
                elif subtype not in (
                    "api_error",
                    "turn_duration",
                    "bridge_status",
                    "stop_hook_summary",
                    "away_summary",
                    "informational",
                    "scheduled_task_fire",
                ):
                    print(f"Warning: unknown system subtype '{subtype}' at line {line_num}", file=sys.stderr)
                continue

            if entry_type not in ("user", "assistant"):
                continue

            message = as_dict(entry.get("message"))
            content = message.get("content")
            ts = _parse_ts(entry.get("timestamp", ""))

            if entry_type == "user":
                if isinstance(content, list) and content and isinstance(content[0], dict) and content[0].get("type") == "tool_result":
                    tool_use_result = entry.get("toolUseResult")
                    for block in content:
                        if not isinstance(block, dict) or block.get("type") != "tool_result":
                            continue
                        tool_use_id = as_str(block.get("tool_use_id"))
                        is_error = block.get("is_error") is True
                        result_full = _result_text(block.get("content"))

                        if tool_use_id in pending_tool_uses:
                            tu = pending_tool_uses.pop(tool_use_id)
                            summary = _tool_summary(tu["name"], tu.get("input"))
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
                    text_parts = []
                    for b in content:
                        if not isinstance(b, dict):
                            continue
                        if b.get("type") == "text":
                            text_parts.append(as_str(b.get("text")))
                        elif b.get("type") == "image":
                            source = b.get("source", {})
                            source_type = source.get("type") if isinstance(source, dict) else None
                            text_parts.append(f"[image{': ' + source_type if source_type else ''}]")
                    text_content = " ".join(text_parts)
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
                model = as_str(message.get("model")) or None
                usage = as_dict(message.get("usage"))
                msg_id = as_str(message.get("id")) or None

                # Start a new Message when msg_id changes (or no current assistant).
                # Multiple streaming entries share msg_id: merge those with max().
                # Distinct msg_ids are separate assistant turns: sum across them.
                if current_assistant is None or (msg_id and msg_id != current_msg_id):
                    if current_assistant is not None:
                        _flush_pending_tool_uses(current_assistant, pending_tool_uses, pending_tool_order)
                        _finalize_assistant(current_assistant)
                        messages.append(current_assistant)
                    pending_tool_uses = {}
                    pending_tool_order = {}
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
                    raw_input = as_int(usage.get("input_tokens"))
                    cache_creation = as_int(usage.get("cache_creation_input_tokens"))
                    cache_read = as_int(usage.get("cache_read_input_tokens"))
                    total_in = raw_input + cache_creation + cache_read
                    total_cached = cache_creation + cache_read

                    current_assistant.tokens_in = max(current_assistant.tokens_in, total_in)
                    current_assistant.tokens_out = max(current_assistant.tokens_out, as_int(usage.get("output_tokens")))
                    current_assistant.tokens_cached = max(current_assistant.tokens_cached, total_cached)
                    if model:
                        current_assistant.model = model

                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        btype = block.get("type")
                        if btype == "thinking":
                            text = as_str(block.get("thinking"))
                            if text.strip():
                                idx = len(current_assistant.thinking)
                                current_assistant.thinking.append(text.strip())
                                current_assistant.content_order.append(("thinking", idx))
                        elif btype == "text":
                            text = as_str(block.get("text"))
                            if text.strip():
                                idx = len(current_assistant.text)
                                current_assistant.text.append(text.strip())
                                current_assistant.content_order.append(("text", idx))
                        elif btype == "tool_use":
                            tu_id = as_str(block.get("id"))
                            pending_tool_uses[tu_id] = {
                                "name": as_str(block.get("name")) or "?",
                                "input": block.get("input"),
                            }
                            # Reserve a slot; will be filled when result arrives
                            pending_tool_order[tu_id] = len(current_assistant.content_order)
                            current_assistant.content_order.append(("tool", -1))

    if current_assistant:
        _flush_pending_tool_uses(current_assistant, pending_tool_uses, pending_tool_order)
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
