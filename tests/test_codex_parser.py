from pathlib import Path
import json
from transcript.parsers.codex import parse
from transcript.model import Status, Role

FIXTURE = str(Path(__file__).parent / "fixtures" / "codex_minimal.jsonl")


def test_parse_message_count():
    t = parse(FIXTURE)
    assert len(t.messages) == 3


def test_parse_developer_message():
    t = parse(FIXTURE)
    msg = t.messages[0]
    assert msg.role == Role.DEVELOPER
    assert msg.text == ["Follow project conventions."]


def test_parse_user_message():
    t = parse(FIXTURE)
    msg = t.messages[1]
    assert msg.role == Role.USER
    assert msg.text == ["Help me inspect tests"]


def test_parse_assistant_content_and_reasoning():
    t = parse(FIXTURE)
    msg = t.messages[2]
    assert msg.role == Role.ASSISTANT
    assert msg.model == "gpt-5.5"
    assert msg.thinking == ["I should inspect the test file first."]
    assert msg.text == ["I'll inspect the test file.", "Done."]
    assert msg.content_order[:3] == [("thinking", 0), ("text", 0), ("tool", 0)]


def test_parse_exec_command_tool_call():
    t = parse(FIXTURE)
    tc = t.messages[2].tool_calls[0]
    assert tc.name == "exec_command"
    assert tc.display_name == "exec_command"
    assert tc.summary == "sed -n '1,80p' tests/test_login.py"
    assert tc.result_summary == "ok"
    assert "def test_login" in tc.result_full
    assert tc.status == Status.PASSED


def test_parse_custom_apply_patch_tool_call():
    t = parse(FIXTURE)
    tc = t.messages[2].tool_calls[1]
    assert tc.name == "apply_patch"
    assert tc.summary == "tests/test_login.py"
    assert tc.result_summary == "1 files changed"
    assert tc.status == Status.PASSED


def test_parse_tokens_sum_last_usage_events():
    t = parse(FIXTURE)
    msg = t.messages[2]
    assert msg.tokens_in == 1200
    assert msg.tokens_out == 75
    assert msg.tokens_cached == 900
    assert msg.tokens_thinking == 12
    assert t.total_tokens_in == 1200
    assert t.total_tokens_out == 75


def test_parse_transcript_metadata():
    t = parse(FIXTURE)
    assert t.source_format == "codex"
    assert t.session_id == "codex-session-001"
    assert t.start_time.isoformat() == "2026-01-01T10:00:00+00:00"
    assert t.end_time.isoformat() == "2026-01-01T10:00:12+00:00"
    assert "gpt-5.5" in t.models


def test_parse_tool_stats():
    t = parse(FIXTURE)
    assert t.tool_stats.passed == 2
    assert t.tool_stats.failed == 0
    assert t.tool_stats.cancelled == 0


def test_unknown_codex_model_cost_is_partial():
    t = parse(FIXTURE)
    assert t.total_cost is None
    assert t.cost_is_partial is True


def test_parse_failed_command(tmp_path):
    p = tmp_path / "codex_failed.jsonl"
    lines = [
        {"timestamp": "2026-01-01T10:00:00Z", "type": "turn_context", "payload": {"model": "gpt-5.5"}},
        {"timestamp": "2026-01-01T10:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "run tests"}]}},
        {"timestamp": "2026-01-01T10:00:02Z", "type": "response_item", "payload": {"type": "function_call", "name": "exec_command", "arguments": json.dumps({"cmd": "pytest"}), "call_id": "call_fail"}},
        {"timestamp": "2026-01-01T10:00:03Z", "type": "response_item", "payload": {"type": "function_call_output", "call_id": "call_fail", "output": "Process exited with code 1\nOutput:\nAssertionError"}},
    ]
    p.write_text("\n".join(json.dumps(line) for line in lines))

    t = parse(str(p))
    tc = t.messages[1].tool_calls[0]
    assert tc.result_summary == "FAILED (exit 1)"
    assert tc.status == Status.FAILED


def test_unresolved_tool_is_failed(tmp_path):
    p = tmp_path / "codex_unresolved.jsonl"
    lines = [
        {"timestamp": "2026-01-01T10:00:00Z", "type": "turn_context", "payload": {"model": "gpt-5.5"}},
        {"timestamp": "2026-01-01T10:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "read"}]}},
        {"timestamp": "2026-01-01T10:00:02Z", "type": "response_item", "payload": {"type": "function_call", "name": "exec_command", "arguments": json.dumps({"cmd": "pwd"}), "call_id": "call_missing"}},
    ]
    p.write_text("\n".join(json.dumps(line) for line in lines))

    t = parse(str(p))
    tc = t.messages[1].tool_calls[0]
    assert tc.result_summary == "no result"
    assert tc.status == Status.FAILED


def _write_jsonl(path, entries):
    path.write_text("\n".join(e if isinstance(e, str) else json.dumps(e) for e in entries))


def test_token_count_with_null_info_does_not_crash(tmp_path):
    p = tmp_path / "codex_null_info.jsonl"
    _write_jsonl(p, [
        {"timestamp": "2026-01-01T10:00:00Z", "type": "session_meta", "payload": {"id": "s1"}},
        {"timestamp": "2026-01-01T10:00:01Z", "type": "turn_context", "payload": {"model": "gpt-5.5"}},
        {"timestamp": "2026-01-01T10:00:02Z", "type": "response_item",
         "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "hi"}]}},
        {"timestamp": "2026-01-01T10:00:03Z", "type": "event_msg", "payload": {"type": "token_count", "info": None}},
        {"timestamp": "2026-01-01T10:00:04Z", "type": "event_msg",
         "payload": {"type": "token_count", "info": {"last_token_usage": None}}},
        {"timestamp": "2026-01-01T10:00:05Z", "type": "event_msg",
         "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": None, "output_tokens": 4}}}},
    ])

    t = parse(str(p))
    assert len(t.messages) == 1
    assert t.messages[0].text == ["hi"]
    assert t.messages[0].tokens_in == 0
    assert t.messages[0].tokens_out == 4


def test_non_dict_line_and_wrong_types_do_not_abort(tmp_path, capsys):
    p = tmp_path / "codex_wrong_types.jsonl"
    _write_jsonl(p, [
        "[1,2]",
        {"timestamp": "2026-01-01T10:00:00Z", "type": "session_meta", "payload": {"id": "s1"}},
        {"timestamp": "2026-01-01T10:00:01Z", "type": "turn_context", "payload": {"model": ["not", "a", "string"]}},
        {"timestamp": "2026-01-01T10:00:02Z", "type": "response_item", "payload": None},
        {"timestamp": "2026-01-01T10:00:03Z", "type": "response_item",
         "payload": {"type": "function_call", "name": "exec_command", "call_id": "c1",
                     "arguments": json.dumps({"cmd": ["ls", "-la"]})}},
        {"timestamp": "2026-01-01T10:00:04Z", "type": "response_item",
         "payload": {"type": "function_call_output", "call_id": "c1", "output": None}},
    ])

    t = parse(str(p))
    assert len(t.messages) == 1
    tc = t.messages[0].tool_calls[0]
    assert isinstance(tc.summary, str)
    assert "ls" in tc.summary
    assert "line 1" in capsys.readouterr().err


def _single_tool_output(tmp_path, output, name="read_file", args=None):
    p = tmp_path / "codex_output.jsonl"
    _write_jsonl(p, [
        {"timestamp": "2026-01-01T10:00:00Z", "type": "turn_context", "payload": {"model": "gpt-5.5"}},
        {"timestamp": "2026-01-01T10:00:01Z", "type": "response_item",
         "payload": {"type": "function_call", "name": name, "call_id": "c1",
                     "arguments": json.dumps(args or {"path": "notes.txt"})}},
        {"timestamp": "2026-01-01T10:00:02Z", "type": "response_item",
         "payload": {"type": "function_call_output", "call_id": "c1", "output": output}},
    ])
    return parse(str(p)).messages[0].tool_calls[0]


def test_output_mentioning_cancelled_is_not_cancelled(tmp_path):
    tc = _single_tool_output(tmp_path, "Meeting notes\nthe job was cancelled last week\nreschedule it")
    assert tc.status == Status.PASSED
    assert tc.result_summary == "3 lines"


def test_output_mentioning_failed_is_not_failed(tmp_path):
    tc = _single_tool_output(tmp_path, "collected 10 items\n\n10 passed, 0 failed in 0.12s")
    assert tc.status == Status.PASSED
    assert tc.result_summary == "3 lines"


def test_output_mentioning_error_colon_later_is_not_failed(tmp_path):
    tc = _single_tool_output(tmp_path, "def handler():\n    log('error: retrying')\n")
    assert tc.status == Status.PASSED


def test_output_starting_with_error_marker_is_failed(tmp_path):
    tc = _single_tool_output(tmp_path, "\nError: file not found: notes.txt\nmore detail")
    assert tc.status == Status.FAILED
    assert tc.result_summary == "FAILED: Error: file not found: notes.txt"


def test_output_starting_with_failed_marker_is_failed(tmp_path):
    tc = _single_tool_output(tmp_path, "failed to parse function arguments: missing field `cmd`")
    assert tc.status == Status.FAILED
    assert tc.result_summary.startswith("FAILED: failed to parse function arguments")


def test_output_starting_with_cancelled_marker_is_cancelled(tmp_path):
    tc = _single_tool_output(tmp_path, "Cancelled by user")
    assert tc.status == Status.CANCELLED
    assert tc.result_summary == "cancelled"


def test_output_without_matching_call_is_kept(tmp_path, capsys):
    p = tmp_path / "codex_orphan.jsonl"
    _write_jsonl(p, [
        {"timestamp": "2026-01-01T10:00:00Z", "type": "turn_context", "payload": {"model": "gpt-5.5"}},
        {"timestamp": "2026-01-01T10:00:01Z", "type": "response_item",
         "payload": {"type": "function_call_output", "call_id": "c_lost", "output": "orphan output"}},
    ])
    t = parse(str(p))
    assert len(t.messages) == 1
    tc = t.messages[0].tool_calls[0]
    assert tc.name == "?"
    assert tc.summary == "unmatched output for call c_lost"
    assert tc.result_full == "orphan output"
    assert t.messages[0].content_order == [("tool", 0)]
