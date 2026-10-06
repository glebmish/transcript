from pathlib import Path
import json
from transcript.parsers.gemini import parse
from transcript.model import Status, Role

FIXTURE = str(Path(__file__).parent / "fixtures" / "gemini_minimal.json")


def test_parse_message_count():
    t = parse(FIXTURE)
    # 2 user + 2 gemini = 4 (info skipped)
    assert len(t.messages) == 4


def test_parse_user_message():
    t = parse(FIXTURE)
    msg = t.messages[0]
    assert msg.role == Role.USER
    assert msg.text == ["Help me fix the login bug"]


def test_parse_gemini_content():
    t = parse(FIXTURE)
    msg = t.messages[1]
    assert msg.role == Role.ASSISTANT
    assert msg.model == "gemini-2.5-flash"
    assert msg.text == ["I'll investigate the login issue."]


def test_parse_thinking():
    t = parse(FIXTURE)
    msg = t.messages[1]
    assert msg.thinking == ["Let me check the auth module."]


def test_parse_tool_call_success():
    t = parse(FIXTURE)
    msg = t.messages[1]
    tc = msg.tool_calls[0]
    assert tc.name == "read_file"
    assert tc.display_name == "ReadFile"
    assert tc.summary == "/src/login.py"
    assert tc.result_summary == "22 lines"
    assert "def login" in tc.result_full
    assert tc.status == Status.PASSED


def test_parse_tool_call_cancelled():
    t = parse(FIXTURE)
    msg = t.messages[1]
    tc = msg.tool_calls[1]
    assert tc.name == "run_shell_command"
    assert tc.display_name == "Shell"
    assert tc.summary == "Run tests"
    assert tc.status == Status.CANCELLED


def test_parse_input_tokens_are_per_call_full_prompt():
    t = parse(FIXTURE)
    msg1 = t.messages[1]  # first gemini, tokens.input=5000
    msg2 = t.messages[3]  # second gemini, tokens.input=8000
    assert msg1.tokens_in == 5000
    assert msg2.tokens_in == 8000


def test_input_tokens_are_not_deltas(tmp_path):
    """tokens.input is each call's full prompt; tokens_cached is its cached part.

    Storing deltas made billable = tokens_in - tokens_cached wrong (and could go
    negative once the context shrank, e.g. after compression).
    """
    calls = [(50000, 0), (52000, 48000), (8000, 0)]
    p = tmp_path / "gemini_token_semantics.json"
    p.write_text(json.dumps({
        "sessionId": "token-semantics",
        "messages": [
            {
                "type": "gemini",
                "timestamp": f"2026-01-01T10:00:0{i}Z",
                "model": "gemini-2.5-flash",
                "content": f"reply {i}",
                "tokens": {"input": inp, "output": 10, "cached": cached, "thoughts": 0},
            }
            for i, (inp, cached) in enumerate(calls)
        ],
    }))

    t = parse(str(p))
    assert [m.tokens_in for m in t.messages] == [50000, 52000, 8000]
    assert [m.tokens_cached for m in t.messages] == [0, 48000, 0]
    assert all(m.tokens_in >= m.tokens_cached >= 0 for m in t.messages)
    assert t.total_tokens_in == 110000


def test_parse_cached_tokens():
    t = parse(FIXTURE)
    msg = t.messages[1]
    assert msg.tokens_cached == 3000
    assert msg.tokens_thinking == 100


def test_parse_transcript_metadata():
    t = parse(FIXTURE)
    assert t.source_format == "gemini"
    assert t.session_id == "test-session-001"
    assert "gemini-2.5-flash" in t.models


def test_parse_tool_stats():
    t = parse(FIXTURE)
    assert t.tool_stats.passed == 1
    assert t.tool_stats.failed == 0
    assert t.tool_stats.cancelled == 1


def test_info_messages_skipped():
    t = parse(FIXTURE)
    for m in t.messages:
        assert "Request cancelled" not in " ".join(m.text)


def test_structured_result_display_list(tmp_path):
    p = tmp_path / "gemini_structured_display.json"
    p.write_text(json.dumps({
        "sessionId": "structured-display",
        "startTime": "2026-01-01T10:00:00Z",
        "lastUpdated": "2026-01-01T10:00:01Z",
        "messages": [{
            "type": "gemini",
            "timestamp": "2026-01-01T10:00:01Z",
            "model": "gemini-2.5-flash",
            "content": "",
            "tokens": {"input": 10, "output": 2, "cached": 0, "thoughts": 0},
            "toolCalls": [{
                "name": "run_shell_command",
                "displayName": "Shell",
                "args": {"command": "printf hi"},
                "resultDisplay": [["line 1"], ["line 2"], ["line 3"]],
                "result": [{
                    "functionResponse": {
                        "response": {"output": "line 1\nline 2\nline 3"}
                    }
                }],
                "status": "success",
            }],
        }],
    }))

    t = parse(str(p))
    tc = t.messages[0].tool_calls[0]
    assert tc.result_summary == "3 lines"
    assert tc.result_full == "line 1\nline 2\nline 3"
    assert isinstance(tc.result_summary, str)


def test_structured_result_display_dict(tmp_path):
    p = tmp_path / "gemini_structured_dict.json"
    p.write_text(json.dumps({
        "sessionId": "structured-dict",
        "startTime": "2026-01-01T10:00:00Z",
        "lastUpdated": "2026-01-01T10:00:01Z",
        "messages": [{
            "type": "gemini",
            "timestamp": "2026-01-01T10:00:01Z",
            "model": "gemini-2.5-flash",
            "content": "",
            "tokens": {"input": 10, "output": 2, "cached": 0, "thoughts": 0, "tool": 5, "total": 17},
            "toolCalls": [{
                "name": "generalist",
                "displayName": "Generalist Agent",
                "args": {"request": "inspect fixtures"},
                "resultDisplay": {"summary": "done"},
                "result": [{
                    "functionResponse": {
                        "response": {"output": "full result"}
                    }
                }],
                "status": "success",
            }],
        }],
    }))

    t = parse(str(p))
    tc = t.messages[0].tool_calls[0]
    assert tc.result_summary == "done"
    assert tc.result_full == "full result"


def test_null_and_wrong_type_nested_fields_do_not_abort(tmp_path, capsys):
    p = tmp_path / "gemini_nulls.json"
    p.write_text(json.dumps({
        "sessionId": "nulls",
        "startTime": "2026-01-01T10:00:00Z",
        "lastUpdated": "2026-01-01T10:00:05Z",
        "messages": [
            [1, 2],
            {"type": "user", "timestamp": "2026-01-01T10:00:00Z", "content": None},
            {"type": "user", "timestamp": "2026-01-01T10:00:01Z", "content": [{"text": None}, {"text": "hello"}]},
            {
                "type": "gemini",
                "timestamp": "2026-01-01T10:00:02Z",
                "model": "gemini-2.5-flash",
                "content": None,
                "tokens": None,
                "thoughts": None,
                "toolCalls": None,
            },
            {
                "type": "gemini",
                "timestamp": "2026-01-01T10:00:03Z",
                "model": "gemini-2.5-flash",
                "content": "answer",
                "tokens": {"input": None, "output": "3", "cached": [], "thoughts": None},
                "thoughts": [None, {"description": None}, {"description": "think"}],
                "toolCalls": [
                    None,
                    {"name": "read_file", "args": None, "result": [{"functionResponse": None}], "status": None},
                    {"name": "run_shell_command", "args": {"command": None},
                     "result": [{"functionResponse": {"response": None}}]},
                ],
            },
        ],
    }))

    t = parse(str(p))
    assert len(t.messages) == 3
    assert t.messages[0].text == ["hello"]
    first, second = t.messages[1], t.messages[2]
    assert first.tokens_in == 0
    assert first.tool_calls == []
    assert second.tokens_in == 0
    assert second.tokens_out == 0
    assert second.thinking == ["think"]
    assert [tc.name for tc in second.tool_calls] == ["read_file", "run_shell_command"]
    assert "skipping non-object message 1" in capsys.readouterr().err


def test_null_tokens_gives_zero_counts(tmp_path):
    p = tmp_path / "gemini_null_tokens.json"
    p.write_text(json.dumps({
        "sessionId": "null-tokens",
        "messages": [{
            "type": "gemini",
            "timestamp": "2026-01-01T10:00:02Z",
            "model": "gemini-2.5-flash",
            "content": "hi",
            "tokens": None,
        }],
    }))

    t = parse(str(p))
    msg = t.messages[0]
    assert (msg.tokens_in, msg.tokens_out, msg.tokens_cached, msg.tokens_thinking) == (0, 0, 0, 0)


def test_error_and_warning_messages_become_system_messages(tmp_path, capsys):
    p = tmp_path / "gemini_error_warning.json"
    p.write_text(json.dumps({
        "sessionId": "error-warning",
        "messages": [
            {"type": "user", "timestamp": "2026-01-01T10:00:00Z", "content": [{"text": "hi"}]},
            {"type": "error", "timestamp": "2026-01-01T10:00:01Z", "content": "[API Error: quota exceeded]"},
            {"type": "warning", "timestamp": "2026-01-01T10:00:02Z", "content": [{"text": "Context nearly full"}]},
            {"type": "info", "timestamp": "2026-01-01T10:00:03Z", "content": "Request cancelled."},
            {"type": "mystery", "timestamp": "2026-01-01T10:00:04Z", "content": "?"},
        ],
    }))

    t = parse(str(p))
    assert [m.role for m in t.messages] == [Role.USER, Role.SYSTEM, Role.SYSTEM]
    assert t.messages[1].text == ["[error] [API Error: quota exceeded]"]
    assert t.messages[2].text == ["[warning] Context nearly full"]
    err = capsys.readouterr().err
    assert "unknown Gemini message type 'mystery'" in err
    assert "info" not in err
