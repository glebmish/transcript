import json
import sys
from datetime import datetime, timezone
from transcript.model import Status, Role, ToolCall, Message, ToolStats, Transcript
from transcript.pricing import message_cost
from transcript.sanitize import sanitize_text
from transcript.parsers.common import as_dict, as_int, as_list, as_str, count_label, is_real_model

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


def _tool_summary(name: str, args) -> str:
    args = as_dict(args)

    def arg(key: str) -> str:
        return as_str(args.get(key))

    if name == "read_file":
        return arg("absolute_path") or arg("file_path") or "?"
    if name in ("write_file", "replace"):
        return arg("file_path") or "?"
    if name == "read_many_files":
        paths = args.get("paths", "?")
        if isinstance(paths, list):
            return ", ".join(str(p) for p in paths[:3])
        return str(paths)
    if name == "list_directory":
        return arg("dir_path") or "?"
    if name == "run_shell_command":
        return arg("description") or (arg("command") or "?")[:80]
    if name in ("grep_search", "search_file_content"):
        return arg("pattern") or "?"
    if name == "glob":
        return arg("pattern") or "?"
    if name == "google_web_search":
        return arg("query") or "?"
    if name == "web_fetch":
        return arg("url") or arg("prompt") or "?"
    if name == "activate_skill":
        return arg("name") or "?"
    if name == "ask_user":
        q = args.get("questions", "?")
        if isinstance(q, list) and q:
            return str(q[0])[:80]
        return str(q)[:80]
    if name == "enter_plan_mode":
        return arg("reason") or "?"
    if name == "exit_plan_mode":
        return arg("plan_path") or "?"
    if name == "codebase_investigator":
        return (arg("objective") or "?")[:80]
    if name == "generalist":
        return (arg("request") or "?")[:80]
    if name == "cli_help":
        return (arg("question") or "?")[:80]
    for v in args.values():
        if isinstance(v, str) and v:
            return v[:80]
    return "?"


def _summarize_text(text: str) -> str:
    if len(text) <= 50 and "\n" not in text:
        return text
    lines = text.strip().split("\n")
    return count_label(len(lines), "line")


def _summary_from_display(display) -> str:
    """Convert Gemini's string/list/dict resultDisplay into a compact string."""
    if not display:
        return ""
    if isinstance(display, str):
        return _summarize_text(display)
    if isinstance(display, list):
        return count_label(len(display), "line")
    if isinstance(display, dict):
        for key in ("summary", "result", "state", "terminateReason"):
            value = display.get(key)
            if isinstance(value, str) and value:
                return _summarize_text(value)
        files = display.get("files")
        if isinstance(files, list):
            return count_label(len(files), "file")
        diff_stat = display.get("diffStat")
        if isinstance(diff_stat, str) and diff_stat:
            return diff_stat
        if display.get("isSubagentProgress"):
            return "subagent progress"
        return count_label(len(display), "field")
    return str(display)[:50]


_NOTICE_TYPES = ("error", "warning")


def _content_text(content) -> str:
    """Stripped text of a message ``content`` that is a string or a list of parts."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return " ".join(
            as_str(item.get("text")) for item in content if isinstance(item, dict)
        ).strip()
    return ""


def _to_text(value) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value, indent=2, sort_keys=True, default=str)


def _extract_result(tc: dict) -> tuple[str, str, Status]:
    """Returns (result_summary, result_full, status)."""
    status = _STATUS_MAP.get(as_str(tc.get("status")) or "success", Status.PASSED)
    result_display = tc.get("resultDisplay") or ""
    result_data = as_list(tc.get("result"))

    result_full = ""
    if result_data:
        fr = result_data[0]
        if isinstance(fr, dict):
            resp = as_dict(as_dict(fr.get("functionResponse")).get("response"))
            if "error" in resp:
                error_text = _to_text(resp["error"])
                # Cancelled tools may have error text but keep CANCELLED status
                error_status = Status.CANCELLED if status == Status.CANCELLED else Status.FAILED
                return error_text, error_text, error_status
            result_full = _to_text(resp.get("output"))

    display_summary = _summary_from_display(result_display)
    if display_summary:
        return display_summary, result_full, status

    if result_full:
        return _summarize_text(result_full), result_full, status

    return "ok", result_full, status


def parse(path: str) -> Transcript:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object at the top level")

    messages: list[Message] = []

    for entry_num, entry in enumerate(as_list(data.get("messages")), 1):
        if not isinstance(entry, dict):
            print(f"Warning: skipping non-object message {entry_num}", file=sys.stderr)
            continue
        msg_type = entry.get("type")
        ts = _parse_ts(entry.get("timestamp", ""))

        if msg_type == "info":
            continue

        if msg_type == "user":
            text = _content_text(entry.get("content"))
            if text:
                messages.append(Message(role=Role.USER, timestamp=ts, text=[text]))

        elif msg_type in _NOTICE_TYPES:
            # Runtime errors and warnings are shown as system messages, labelled
            # with their native type so they are distinguishable.
            text = _content_text(entry.get("content"))
            label = f"[{msg_type}]"
            messages.append(Message(
                role=Role.SYSTEM,
                timestamp=ts,
                text=[f"{label} {text}" if text else label],
            ))

        elif msg_type == "gemini":
            tokens = as_dict(entry.get("tokens"))
            model = as_str(entry.get("model")) or None

            # tokens.input is this API call's full prompt size and tokens.cached
            # is the cached portion of it, which matches the common contract
            # (tokens_in = full context, tokens_cache_read = its cached part).
            # No deltas. Gemini CLI uses implicit caching, so there are no
            # cache writes to record.
            msg = Message(
                role=Role.ASSISTANT,
                timestamp=ts,
                model=model,
                tokens_in=as_int(tokens.get("input")),
                tokens_out=as_int(tokens.get("output")),
                tokens_cache_read=as_int(tokens.get("cached")),
                tokens_thinking=as_int(tokens.get("thoughts")),
            )

            for thought in as_list(entry.get("thoughts")):
                desc = as_str(as_dict(thought).get("description"))
                if desc.strip():
                    idx = len(msg.thinking)
                    msg.thinking.append(desc.strip())
                    msg.content_order.append(("thinking", idx))

            content = entry.get("content", "")
            if isinstance(content, str) and content.strip():
                idx = len(msg.text)
                msg.text.append(content.strip())
                msg.content_order.append(("text", idx))

            for tc in as_list(entry.get("toolCalls")):
                if not isinstance(tc, dict):
                    continue
                name = as_str(tc.get("name")) or "?"
                display_name = as_str(tc.get("displayName")) or name
                summary = _tool_summary(name, tc.get("args"))
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

        else:
            print(
                f"Warning: skipping unknown Gemini message type "
                f"'{sanitize_text(str(msg_type))}' in message {entry_num}",
                file=sys.stderr,
            )

    return _build_transcript(messages, data)


def _build_transcript(messages: list[Message], data: dict) -> Transcript:
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
        session_id=as_str(data.get("sessionId")) or None,
        start_time=start,
        end_time=end,
        models=models,
        total_tokens_in=total_in,
        total_tokens_out=total_out,
        total_cost=final_cost,
        cost_is_partial=cost_is_partial,
        tool_stats=ToolStats(passed=passed, failed=failed, cancelled=cancelled),
    )
