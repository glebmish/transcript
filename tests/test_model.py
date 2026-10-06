from datetime import datetime, timezone
from transcript.model import Status, Role, ToolCall, Message, ToolStats, Transcript


def test_status_values():
    assert Status.PASSED.value == "passed"
    assert Status.FAILED.value == "failed"
    assert Status.CANCELLED.value == "cancelled"


def test_role_values():
    assert Role.USER.value == "user"
    assert Role.ASSISTANT.value == "assistant"
    assert Role.SYSTEM.value == "system"
    assert Role.DEVELOPER.value == "developer"


def test_tool_call_creation():
    tc = ToolCall(
        name="Bash",
        display_name="Bash",
        summary="pytest tests/",
        result_summary="FAILED (exit 1)",
        result_full="FAILED test_auth.py::test_jwt\nAssertionError",
        status=Status.FAILED,
    )
    assert tc.name == "Bash"
    assert tc.status == Status.FAILED


def test_message_defaults():
    msg = Message(role=Role.USER, timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert msg.model is None
    assert msg.tokens_in == 0
    assert msg.tokens_out == 0
    assert msg.tokens_cache_read == 0
    assert msg.tokens_cache_write_5m == 0
    assert msg.tokens_cache_write_1h == 0
    assert msg.tokens_thinking == 0
    assert msg.thinking == []
    assert msg.text == []
    assert msg.tool_calls == []
    assert msg.is_compaction_marker is False


def test_transcript_creation():
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t = Transcript(
        messages=[],
        source_format="claude",
        session_id="abc",
        start_time=ts,
        end_time=ts,
        models=set(),
        total_tokens_in=0,
        total_tokens_out=0,
        total_cost=None,
        cost_is_partial=False,
        tool_stats=ToolStats(passed=0, failed=0, cancelled=0),
    )
    assert t.source_format == "claude"
    assert t.cost_is_partial is False
