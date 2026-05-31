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
