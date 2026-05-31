import json
from datetime import datetime, timezone
from transcript.model import Status, Role, ToolCall, Message, ToolStats, Transcript
from transcript.pricing import estimate_cost

_MIN_TS = datetime.min.replace(tzinfo=timezone.utc)

_STATUS_MAP = {
    "success": Status.PASSED,
    "error": Status.FAILED,
    "cancelled": Status.CANCELLED,
}


def _parse_ts(raw: str) -> datetime:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return _MIN_TS


def _tool_summary(name: str, args: dict) -> str:
    if name == "read_file":
        return args.get("absolute_path") or args.get("file_path") or "?"
    if name in ("write_file", "replace"):
        return args.get("file_path", "?")
    if name == "read_many_files":
        paths = args.get("paths", "?")
        if isinstance(paths, list):
            return ", ".join(str(p) for p in paths[:3])
        return str(paths)
    if name == "list_directory":
        return args.get("dir_path", "?")
    if name == "run_shell_command":
        return args.get("description") or (args.get("command", "?")[:80])
    if name in ("grep_search", "search_file_content"):
        return args.get("pattern", "?")
    if name == "glob":
        return args.get("pattern", "?")
    if name == "google_web_search":
        return args.get("query", "?")
    if name == "web_fetch":
        return args.get("url") or args.get("prompt") or "?"
    if name == "activate_skill":
        return args.get("name", "?")
    if name == "ask_user":
        q = args.get("questions", "?")
        if isinstance(q, list) and q:
            return str(q[0])[:80]
        return str(q)[:80]
    if name == "enter_plan_mode":
        return args.get("reason", "?")
    if name == "exit_plan_mode":
        return args.get("plan_path", "?")
    if name == "codebase_investigator":
        return args.get("objective", "?")[:80]
    if name == "generalist":
        return args.get("request", "?")[:80]
    if name == "cli_help":
        return args.get("question", "?")[:80]
    for v in args.values():
        if isinstance(v, str) and v:
            return v[:80]
    return "?"


def _extract_result(tc: dict) -> tuple[str, str, Status]:
    """Returns (result_summary, result_full, status)."""
    status = _STATUS_MAP.get(tc.get("status", "success"), Status.PASSED)
    result_display = tc.get("resultDisplay") or ""
    result_data = tc.get("result") or []

    result_full = ""
    if result_data and isinstance(result_data, list):
        fr = result_data[0]
        if isinstance(fr, dict):
            resp = fr.get("functionResponse", {}).get("response", {})
            if "error" in resp:
                error_text = resp["error"]
                # Cancelled tools may have error text but keep CANCELLED status
                error_status = Status.CANCELLED if status == Status.CANCELLED else Status.FAILED
                return error_text, error_text, error_status
            result_full = resp.get("output", "")

    if result_display:
        if len(result_display) <= 50 and "\n" not in result_display:
            return result_display, result_full, status
        lines = result_display.strip().split("\n")
        return f"{len(lines)} lines", result_full, status

    if result_full:
        if len(result_full) <= 50 and "\n" not in result_full:
            return result_full, result_full, status
        lines = result_full.strip().split("\n")
        return f"{len(lines)} lines", result_full, status

    return "ok", result_full, status


def parse(path: str) -> Transcript:
    with open(path) as f:
        data = json.load(f)

    messages: list[Message] = []
    prev_input = 0

    for entry in data.get("messages", []):
        msg_type = entry.get("type")
        ts = _parse_ts(entry.get("timestamp", ""))

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
                messages.append(Message(role=Role.USER, timestamp=ts, text=[text.strip()]))

        elif msg_type == "gemini":
            tokens = entry.get("tokens", {})
            model = entry.get("model")
            full_input = tokens.get("input", 0)
            delta_input = full_input - prev_input if prev_input > 0 else full_input
            prev_input = full_input

            msg = Message(
                role=Role.ASSISTANT,
                timestamp=ts,
                model=model,
                tokens_in=delta_input,
                tokens_out=tokens.get("output", 0),
                tokens_cached=tokens.get("cached", 0),
                tokens_thinking=tokens.get("thoughts", 0),
            )

            for thought in entry.get("thoughts", []):
                desc = thought.get("description", "")
                if desc.strip():
                    idx = len(msg.thinking)
                    msg.thinking.append(desc.strip())
                    msg.content_order.append(("thinking", idx))

            content = entry.get("content", "")
            if isinstance(content, str) and content.strip():
                idx = len(msg.text)
                msg.text.append(content.strip())
                msg.content_order.append(("text", idx))

            for tc in entry.get("toolCalls", []):
                name = tc.get("name", "?")
                display_name = tc.get("displayName") or name
                summary = _tool_summary(name, tc.get("args", {}))
                result_summary, result_full, status = _extract_result(tc)
                tool_idx = len(msg.tool_calls)
                msg.content_order.append(("tool", tool_idx))
                msg.tool_calls.append(ToolCall(
                    name=name,
                    display_name=display_name,
                    summary=summary,
                    result_summary=result_summary,
                    result_full=result_full,
                    status=status,
                ))

            messages.append(msg)

    return _build_transcript(messages, data)


def _build_transcript(messages: list[Message], data: dict) -> Transcript:
    models: set[str] = set()
    total_in = total_out = 0
    passed = failed = cancelled = 0
    total_cost = 0.0
    cost_is_partial = False

    for m in messages:
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

    start = _parse_ts(data.get("startTime", ""))
    end = _parse_ts(data.get("lastUpdated", ""))
    if end == _MIN_TS and messages:
        end = messages[-1].timestamp

    if not models or (cost_is_partial and total_cost == 0.0):
        final_cost = None
    else:
        final_cost = total_cost

    return Transcript(
        messages=messages,
        source_format="gemini",
        session_id=data.get("sessionId"),
        start_time=start,
        end_time=end,
        models=models,
        total_tokens_in=total_in,
        total_tokens_out=total_out,
        total_cost=final_cost,
        cost_is_partial=cost_is_partial,
        tool_stats=ToolStats(passed=passed, failed=failed, cancelled=cancelled),
    )
