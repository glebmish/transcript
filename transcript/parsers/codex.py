import json
import re
import sys
from datetime import datetime, timezone
from transcript.model import Status, Role, ToolCall, Message, ToolStats, Transcript
from transcript.pricing import message_cost
from transcript.sanitize import sanitize_text
from transcript.parsers.common import as_dict, as_int, as_str, count_label, is_real_model

_MIN_TS = datetime.min.replace(tzinfo=timezone.utc)
_EXIT_RE = re.compile(r"(?:Process exited with code|Exit code:)\s*(-?\d+)")
_PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", re.MULTILINE)
# Lowercased prefixes of the first non-empty output line.
_CANCEL_MARKERS = ("cancelled", "canceled")
_FAILURE_MARKERS = ("error:", "failed")


def _parse_ts(raw: str) -> datetime:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return _MIN_TS


def _role(raw: str) -> Role | None:
    if raw == "user":
        return Role.USER
    if raw == "assistant":
        return Role.ASSISTANT
    if raw == "system":
        return Role.SYSTEM
    if raw == "developer":
        return Role.DEVELOPER
    return None


def _text_blocks(content, text_types: tuple[str, ...]) -> list[str]:
    if isinstance(content, str):
        return [content.strip()] if content.strip() else []
    if not isinstance(content, list):
        return []

    texts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type in text_types:
            text = block.get("text", "")
            if isinstance(text, str) and text.strip():
                texts.append(text.strip())
        elif block_type in ("input_image", "image"):
            source = block.get("source") or block.get("path") or block.get("file_path") or ""
            suffix = f": {source}" if source else ""
            texts.append(f"[image{suffix}]")
        elif block_type in ("input_file", "file"):
            path = block.get("path") or block.get("file_path") or ""
            suffix = f": {path}" if path else ""
            texts.append(f"[file{suffix}]")
    return texts


def _reasoning_texts(payload: dict) -> list[str]:
    texts: list[str] = []

    content = payload.get("content")
    if isinstance(content, str) and content.strip():
        texts.append(content.strip())
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, str) and block.strip():
                texts.append(block.strip())
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    texts.append(text.strip())

    summary = payload.get("summary")
    if isinstance(summary, str) and summary.strip():
        texts.append(summary.strip())
    elif isinstance(summary, list):
        for block in summary:
            if isinstance(block, str) and block.strip():
                texts.append(block.strip())
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    texts.append(text.strip())

    return texts


def _parse_arguments(raw) -> tuple[dict, str]:
    if isinstance(raw, dict):
        return raw, json.dumps(raw)
    if not isinstance(raw, str):
        return {}, "" if raw is None else str(raw)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}, raw
    if isinstance(parsed, dict):
        return parsed, raw
    return {"_raw": raw}, raw


def _first_string(value) -> str:
    if isinstance(value, str) and value:
        return value[:80]
    if isinstance(value, dict):
        for item in value.values():
            found = _first_string(item)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _first_string(item)
            if found:
                return found
    return ""


def _tool_summary(name: str, args: dict, raw_input: str) -> str:
    if name == "exec_command":
        cmd = args.get("cmd")
        if isinstance(cmd, list):
            cmd = " ".join(str(part) for part in cmd)
        return as_str(cmd)[:80] or _first_string(args) or "?"
    if name == "write_stdin":
        session_id = args.get("session_id", "?")
        chars = args.get("chars", "")
        if isinstance(chars, str) and chars.strip():
            return f"{session_id}: {chars.strip()[:60]}"
        return str(session_id)
    if name == "apply_patch":
        match = _PATCH_FILE_RE.search(raw_input)
        return match.group(1) if match else "apply patch"
    for key in ("url", "query", "ticker", "location", "path", "file_path", "selector", "prompt"):
        value = args.get(key)
        if isinstance(value, str) and value:
            return value[:80]
    return _first_string(args) or raw_input.strip()[:80] or "?"


def _line_count(text: str) -> int:
    stripped = text.strip("\n")
    if not stripped:
        return 0
    return len(stripped.splitlines())


def _summarize_output(output: str, patch_event: dict | None = None) -> tuple[str, Status]:
    if patch_event:
        success = patch_event.get("success")
        if success is False:
            detail = patch_event.get("stderr") or patch_event.get("stdout") or ""
            first = str(detail).strip().splitlines()[0] if str(detail).strip() else ""
            return f"FAILED: {first}" if first else "FAILED", Status.FAILED
        if success is True:
            changes = patch_event.get("changes")
            if isinstance(changes, (list, dict)) and changes:
                return f"{count_label(len(changes), 'file')} changed", Status.PASSED
            return "ok", Status.PASSED

    match = _EXIT_RE.search(output)
    if match:
        code = int(match.group(1))
        if code == 0:
            return "ok", Status.PASSED
        return f"FAILED (exit {code})", Status.FAILED

    # Only the first non-empty line can mark a cancellation or failure, so
    # output that merely mentions "cancelled" or "0 failed" keeps PASSED.
    first = output.strip().splitlines()[0].strip() if output.strip() else ""
    first_lower = first.lower()
    if first_lower.startswith(_CANCEL_MARKERS):
        return "cancelled", Status.CANCELLED
    if first_lower.startswith(_FAILURE_MARKERS):
        return (first[:50] if first.startswith("FAILED") else f"FAILED: {first[:50]}"), Status.FAILED
    if output.strip() in ("Success", "Success."):
        return "ok", Status.PASSED

    lines = _line_count(output)
    if lines == 0:
        return "ok", Status.PASSED
    if lines == 1 and len(output.strip()) <= 50:
        return output.strip(), Status.PASSED
    return count_label(lines, "line"), Status.PASSED


def _make_tool_call(pending: dict, output: str, patch_event: dict | None = None) -> ToolCall:
    result_summary, status = _summarize_output(output, patch_event)
    native_status = pending.get("status")
    if native_status in ("cancelled", "canceled"):
        status = Status.CANCELLED
    elif native_status in ("failed", "error"):
        status = Status.FAILED
        if not result_summary.startswith("FAILED"):
            result_summary = f"FAILED: {result_summary}"

    return ToolCall(
        name=pending["name"],
        display_name=pending["name"],
        summary=_tool_summary(pending["name"], pending["args"], pending["raw_input"]),
        result_summary=result_summary,
        result_full=output,
        status=status,
    )


def _apply_token_usage(msg: Message, usage: dict) -> None:
    msg.tokens_in += as_int(usage.get("input_tokens"))
    msg.tokens_out += as_int(usage.get("output_tokens"))
    # input_tokens already includes cached_input_tokens (cache reads).
    msg.tokens_cache_read += as_int(usage.get("cached_input_tokens"))
    msg.tokens_thinking += as_int(usage.get("reasoning_output_tokens"))


def parse(path: str) -> Transcript:
    messages: list[Message] = []
    current_assistant: Message | None = None
    active_model: str | None = None
    session_id: str | None = None
    start_time = _MIN_TS
    end_time = _MIN_TS
    pending_tools: dict[str, dict] = {}
    pending_tool_order: dict[str, int] = {}
    completed_tools: dict[str, tuple[Message, int]] = {}
    patch_events: dict[str, dict] = {}

    def update_end(ts: datetime) -> None:
        nonlocal end_time
        if ts != _MIN_TS and (end_time == _MIN_TS or ts > end_time):
            end_time = ts

    def finalize_assistant() -> None:
        nonlocal current_assistant
        if current_assistant is None:
            return
        for call_id, pending in list(pending_tools.items()):
            tool_idx = len(current_assistant.tool_calls)
            current_assistant.tool_calls.append(ToolCall(
                name=pending["name"],
                display_name=pending["name"],
                summary=_tool_summary(pending["name"], pending["args"], pending["raw_input"]),
                result_summary="no result",
                result_full="",
                status=Status.FAILED,
            ))
            order_pos = pending_tool_order.get(call_id)
            if order_pos is not None and order_pos < len(current_assistant.content_order):
                current_assistant.content_order[order_pos] = ("tool", tool_idx)
            pending_tools.pop(call_id, None)
            pending_tool_order.pop(call_id, None)
        current_assistant.content_order = [item for item in current_assistant.content_order if item[1] != -1]
        messages.append(current_assistant)
        current_assistant = None

    def ensure_assistant(ts: datetime) -> Message:
        nonlocal current_assistant
        if current_assistant is None:
            current_assistant = Message(role=Role.ASSISTANT, timestamp=ts, model=active_model)
        elif active_model and not current_assistant.model:
            current_assistant.model = active_model
        return current_assistant

    def update_completed_tool(call_id: str, patch_event: dict) -> None:
        found = completed_tools.get(call_id)
        if not found:
            return
        msg, idx = found
        existing = msg.tool_calls[idx]
        updated_summary, updated_status = _summarize_output(existing.result_full, patch_event)
        msg.tool_calls[idx] = ToolCall(
            name=existing.name,
            display_name=existing.display_name,
            summary=existing.summary,
            result_summary=updated_summary,
            result_full=existing.result_full,
            status=updated_status,
        )

    with open(path, encoding="utf-8") as f:
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

            ts = _parse_ts(entry.get("timestamp", ""))
            update_end(ts)
            entry_type = entry.get("type")
            payload = entry.get("payload", {})
            if not isinstance(payload, dict):
                continue

            if entry_type == "session_meta":
                session_id = as_str(payload.get("id")) or session_id
                meta_ts = _parse_ts(payload.get("timestamp", ""))
                if meta_ts != _MIN_TS:
                    start_time = meta_ts
                    update_end(meta_ts)
                continue

            if entry_type == "turn_context":
                active_model = as_str(payload.get("model")) or active_model
                if current_assistant and active_model:
                    current_assistant.model = active_model
                continue

            if entry_type == "event_msg":
                event_type = payload.get("type")
                if event_type == "token_count":
                    info = as_dict(payload.get("info"))
                    usage = info.get("last_token_usage")
                    if isinstance(usage, dict) and usage:
                        target = current_assistant
                        if target is None:
                            for msg in reversed(messages):
                                if msg.role == Role.ASSISTANT:
                                    target = msg
                                    break
                        if target is not None:
                            _apply_token_usage(target, usage)
                elif event_type == "patch_apply_end":
                    call_id = as_str(payload.get("call_id"))
                    if call_id:
                        patch_events[call_id] = payload
                        update_completed_tool(call_id, payload)
                elif event_type == "task_complete":
                    completed = _parse_ts(payload.get("completed_at", ""))
                    update_end(completed)
                    finalize_assistant()
                continue

            if entry_type != "response_item":
                continue

            item_type = payload.get("type")

            if item_type == "message":
                role = _role(payload.get("role", ""))
                if role is None:
                    print(f"Warning: unknown Codex message role at line {line_num}", file=sys.stderr)
                    continue

                if role == Role.ASSISTANT:
                    msg = ensure_assistant(ts)
                    for text in _text_blocks(payload.get("content", []), ("output_text", "text")):
                        idx = len(msg.text)
                        msg.text.append(text)
                        msg.content_order.append(("text", idx))
                else:
                    finalize_assistant()
                    texts = _text_blocks(payload.get("content", []), ("input_text", "text", "output_text"))
                    if texts:
                        messages.append(Message(role=role, timestamp=ts, text=texts))
                continue

            if item_type == "reasoning":
                msg = ensure_assistant(ts)
                for text in _reasoning_texts(payload):
                    idx = len(msg.thinking)
                    msg.thinking.append(text)
                    msg.content_order.append(("thinking", idx))
                continue

            if item_type in ("function_call", "custom_tool_call"):
                msg = ensure_assistant(ts)
                call_id = as_str(payload.get("call_id"))
                if not call_id:
                    print(f"Warning: Codex tool call without call_id at line {line_num}", file=sys.stderr)
                    continue
                raw_input = payload.get("arguments") if item_type == "function_call" else payload.get("input")
                args, raw_string = _parse_arguments(raw_input)
                pending_tools[call_id] = {
                    "name": as_str(payload.get("name")) or "?",
                    "args": args,
                    "raw_input": raw_string,
                    "status": payload.get("status"),
                }
                pending_tool_order[call_id] = len(msg.content_order)
                msg.content_order.append(("tool", -1))
                continue

            if item_type in ("function_call_output", "custom_tool_call_output"):
                call_id = as_str(payload.get("call_id"))
                pending = pending_tools.pop(call_id, None)
                if pending is None:
                    # No call to attach to: keep the output visible anyway.
                    pending = {
                        "name": "?",
                        "args": {},
                        "raw_input": f"unmatched output for call {call_id or '?'}",
                        "status": None,
                    }
                msg = ensure_assistant(ts)
                output = payload.get("output")
                if output is None:
                    output = ""
                elif not isinstance(output, str):
                    output = json.dumps(output, indent=2, sort_keys=True)
                tool_call = _make_tool_call(pending, output, patch_events.get(call_id))
                tool_idx = len(msg.tool_calls)
                msg.tool_calls.append(tool_call)
                completed_tools[call_id] = (msg, tool_idx)
                order_pos = pending_tool_order.pop(call_id, None)
                if order_pos is not None and order_pos < len(msg.content_order):
                    msg.content_order[order_pos] = ("tool", tool_idx)
                elif order_pos is None:
                    msg.content_order.append(("tool", tool_idx))
                continue

            if item_type:
                print(
                    f"Warning: unknown Codex response item type '{sanitize_text(str(item_type))}' at line {line_num}",
                    file=sys.stderr,
                )

    finalize_assistant()
    return _build_transcript(messages, session_id, start_time, end_time)


def _build_transcript(
    messages: list[Message],
    session_id: str | None,
    start_time: datetime,
    end_time: datetime,
) -> Transcript:
    models: set[str] = set()
    total_in = total_out = 0
    passed = failed = cancelled = 0
    total_cost = 0.0
    cost_is_partial = False

    for m in messages:
        if m.role == Role.ASSISTANT and is_real_model(m.model):
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
        if m.role == Role.ASSISTANT and is_real_model(m.model):
            c = message_cost(m)
            if c is not None:
                total_cost += c
            else:
                cost_is_partial = True

    non_marker = [m for m in messages if not m.is_compaction_marker]
    if start_time == _MIN_TS and non_marker:
        start_time = non_marker[0].timestamp
    if end_time == _MIN_TS and non_marker:
        end_time = non_marker[-1].timestamp

    if not models or (cost_is_partial and total_cost == 0.0):
        final_cost = None
    else:
        final_cost = total_cost

    return Transcript(
        messages=messages,
        source_format="codex",
        session_id=session_id,
        start_time=start_time,
        end_time=end_time,
        models=models,
        total_tokens_in=total_in,
        total_tokens_out=total_out,
        total_cost=final_cost,
        cost_is_partial=cost_is_partial,
        tool_stats=ToolStats(passed=passed, failed=failed, cancelled=cancelled),
    )
