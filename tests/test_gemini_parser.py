from pathlib import Path
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


def test_parse_input_token_delta():
    t = parse(FIXTURE)
    msg1 = t.messages[1]  # first gemini, raw input=5000
    msg2 = t.messages[3]  # second gemini, raw input=8000, delta=3000
    assert msg1.tokens_in == 5000
    assert msg2.tokens_in == 3000


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
