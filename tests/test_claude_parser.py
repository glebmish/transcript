from pathlib import Path
import json
from transcript.parsers.claude import parse
from transcript.model import Status, Role

FIXTURE = str(Path(__file__).parent / "fixtures" / "claude_minimal.jsonl")


def test_parse_message_count():
    t = parse(FIXTURE)
    # 2 user + 2 assistant + 1 compaction marker = 5
    assert len(t.messages) == 5


def test_parse_user_message():
    t = parse(FIXTURE)
    msg = t.messages[0]
    assert msg.role == Role.USER
    assert msg.text == ["Help me refactor auth"]
    assert msg.is_compaction_marker is False


def test_parse_assistant_with_thinking():
    t = parse(FIXTURE)
    msg = t.messages[1]
    assert msg.role == Role.ASSISTANT
    assert msg.model == "claude-opus-4-6"
    assert msg.thinking == ["Let me look at auth code."]
    assert msg.text == ["I'll read the middleware."]


def test_parse_tool_call_by_id():
    t = parse(FIXTURE)
    msg = t.messages[1]
    assert len(msg.tool_calls) == 1
    tc = msg.tool_calls[0]
    assert tc.name == "Read"
    assert tc.display_name == "Read"
    assert tc.summary == "/src/auth.py"
    assert tc.result_summary == "84 lines"
    assert "def authenticate" in tc.result_full
    assert tc.status == Status.PASSED


def test_parse_failed_tool():
    t = parse(FIXTURE)
    msg = t.messages[4]  # second assistant (after compaction marker + user)
    tc = msg.tool_calls[0]
    assert tc.name == "Bash"
    assert tc.summary == "Run tests"
    assert tc.result_summary == "FAILED (exit 1)"
    assert tc.status == Status.FAILED
    assert "AssertionError" in tc.result_full


def test_parse_compaction_marker():
    t = parse(FIXTURE)
    marker = t.messages[2]
    assert marker.is_compaction_marker is True


def test_parse_tokens_cache_aware():
    t = parse(FIXTURE)
    msg = t.messages[1]
    assert msg.tokens_in == 10000
    assert msg.tokens_out == 500
    assert msg.tokens_cached == 8000


def test_parse_transcript_metadata():
    t = parse(FIXTURE)
    assert t.source_format == "claude"
    assert "claude-opus-4-6" in t.models
    assert t.total_tokens_in == 22000
    assert t.total_tokens_out == 800


def test_parse_tool_stats():
    t = parse(FIXTURE)
    assert t.tool_stats.passed == 1
    assert t.tool_stats.failed == 1
    assert t.tool_stats.cancelled == 0


def test_parse_cost():
    t = parse(FIXTURE)
    # billable_in = (10000-8000) + (12000-9000) = 5000
    # cost = 5000/1M * 5.00 + 800/1M * 25.00 = 0.025 + 0.02 = 0.045
    assert t.total_cost is not None
    assert abs(t.total_cost - 0.045) < 0.001
    assert t.cost_is_partial is False


def test_deduplication():
    import tempfile, os
    lines = [
        '{"type":"user","timestamp":"2026-01-01T10:00:00Z","message":{"role":"user","content":[{"type":"text","text":"hi"}]}}',
        '{"type":"assistant","timestamp":"2026-01-01T10:00:01Z","message":{"id":"msg_dup","role":"assistant","model":"claude-sonnet-4-6","content":[{"type":"text","text":"hello"}],"usage":{"input_tokens":100,"output_tokens":50,"cache_read_input_tokens":0}}}',
        '{"type":"assistant","timestamp":"2026-01-01T10:00:01Z","message":{"id":"msg_dup","role":"assistant","model":"claude-sonnet-4-6","content":[{"type":"text","text":" world"}],"usage":{"input_tokens":100,"output_tokens":50,"cache_read_input_tokens":0}}}',
    ]
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    try:
        with os.fdopen(fd, "w") as f:
            f.write("\n".join(lines))
        t = parse(path)
        assistant_msgs = [m for m in t.messages if m.role == Role.ASSISTANT]
        assert len(assistant_msgs) == 1
        assert assistant_msgs[0].tokens_in == 100  # counted once
        assert assistant_msgs[0].text == ["hello", "world"]  # both accumulated
    finally:
        os.unlink(path)


def test_unresolved_tool_use_then_new_assistant_turn():
    """Tool_use with no matching tool_result must be flushed onto its owning
    assistant before the next assistant turn starts. Otherwise the reserved
    content_order slot leaks into the next assistant (which has a shorter
    content_order) and triggers IndexError at end-of-file flush.
    """
    import tempfile, os
    lines = [
        '{"type":"user","timestamp":"2026-01-01T10:00:00Z","message":{"role":"user","content":[{"type":"text","text":"hi"}]}}',
        # Assistant A emits text + tool_use; no tool_result ever arrives.
        '{"type":"assistant","timestamp":"2026-01-01T10:00:01Z","message":{"id":"msg_A","role":"assistant","model":"claude-sonnet-4-6","content":[{"type":"text","text":"let me check"},{"type":"tool_use","id":"tu_orphan","name":"Read","input":{"file_path":"/x"}}],"usage":{"input_tokens":10,"output_tokens":5,"cache_read_input_tokens":0}}}',
        # Assistant B starts with a different msg_id and shorter content.
        '{"type":"assistant","timestamp":"2026-01-01T10:00:02Z","message":{"id":"msg_B","role":"assistant","model":"claude-sonnet-4-6","content":[{"type":"text","text":"done"}],"usage":{"input_tokens":12,"output_tokens":3,"cache_read_input_tokens":0}}}',
    ]
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    try:
        with os.fdopen(fd, "w") as f:
            f.write("\n".join(lines))
        t = parse(path)
        assistant_msgs = [m for m in t.messages if m.role == Role.ASSISTANT]
        assert len(assistant_msgs) == 2
        msg_a, msg_b = assistant_msgs
        assert len(msg_a.tool_calls) == 1
        assert msg_a.tool_calls[0].name == "Read"
        assert msg_a.tool_calls[0].status == Status.FAILED
        assert msg_a.tool_calls[0].result_summary == "no result"
        assert msg_b.tool_calls == []
    finally:
        os.unlink(path)


def test_local_command_system_preserves_raw_content(tmp_path):
    p = tmp_path / "local_command.jsonl"
    raw = "<command-name>/model</command-name><local-command-stdout>ok</local-command-stdout>"
    p.write_text(json.dumps({
        "type": "system",
        "subtype": "local_command",
        "timestamp": "2026-01-01T10:00:00Z",
        "content": raw,
    }))

    t = parse(str(p))
    assert len(t.messages) == 1
    assert t.messages[0].command_name == "/model"
    assert t.messages[0].text == [raw]


def test_user_image_block_is_visible_placeholder(tmp_path):
    p = tmp_path / "image.jsonl"
    p.write_text(
        '{"type":"user","timestamp":"2026-01-01T10:00:00Z",'
        '"message":{"role":"user","content":[{"type":"text","text":"see this"},'
        '{"type":"image","source":{"type":"base64","media_type":"image/png","data":"redacted"}}]}}'
    )

    t = parse(str(p))
    assert t.messages[0].text == ["see this [image: base64]"]


def test_known_hook_system_subtypes_do_not_warn(tmp_path, capsys):
    p = tmp_path / "known_system.jsonl"
    p.write_text(
        '{"type":"system","subtype":"stop_hook_summary","timestamp":"2026-01-01T10:00:00Z"}\n'
        '{"type":"system","subtype":"away_summary","timestamp":"2026-01-01T10:00:01Z"}'
    )

    parse(str(p))
    captured = capsys.readouterr()
    assert "unknown system subtype" not in captured.err


def test_non_dict_json_line_is_skipped_with_warning(tmp_path, capsys):
    p = tmp_path / "non_dict.jsonl"
    p.write_text(
        '{"type":"user","timestamp":"2026-01-01T10:00:00Z","message":{"role":"user","content":"hi"}}\n'
        '[1,2]\n'
        '"just a string"\n'
        '{"type":"user","timestamp":"2026-01-01T10:00:01Z","message":{"role":"user","content":"again"}}\n'
    )

    t = parse(str(p))
    assert [m.text for m in t.messages] == [["hi"], ["again"]]
    err = capsys.readouterr().err
    assert "line 2" in err
    assert "line 3" in err


def test_null_and_wrong_type_nested_fields_do_not_abort(tmp_path):
    p = tmp_path / "nulls.jsonl"
    lines = [
        {"type": "user", "timestamp": "2026-01-01T10:00:00Z", "message": None},
        {"type": "user", "timestamp": "2026-01-01T10:00:01Z", "message": {"role": "user", "content": "start"}},
        {"type": "assistant", "timestamp": "2026-01-01T10:00:02Z", "message": {
            "id": "msg_null_usage", "role": "assistant", "model": "claude-sonnet-4-6",
            "content": [{"type": "text", "text": "ok"}], "usage": None,
        }},
        {"type": "assistant", "timestamp": "2026-01-01T10:00:03Z", "message": {
            "id": "msg_bad_numbers", "role": "assistant", "model": "claude-sonnet-4-6",
            "content": [
                {"type": "thinking", "thinking": None},
                {"type": "text", "text": None},
                {"type": "tool_use", "id": "tu_1", "name": "Bash", "input": None},
            ],
            "usage": {"input_tokens": None, "output_tokens": "7", "cache_read_input_tokens": [1]},
        }},
        {"type": "user", "timestamp": "2026-01-01T10:00:04Z", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "tu_1", "content": None},
        ]}, "toolUseResult": {"file": None}},
        {"type": "assistant", "timestamp": "2026-01-01T10:00:05Z", "message": {
            "id": "msg_null_content", "role": "assistant", "model": "claude-sonnet-4-6",
            "content": None, "usage": {"input_tokens": 5, "output_tokens": 1},
        }},
        {"type": "system", "subtype": "local_command", "timestamp": "2026-01-01T10:00:06Z", "content": None},
    ]
    p.write_text("\n".join(json.dumps(line) for line in lines))

    t = parse(str(p))
    assistants = [m for m in t.messages if m.role == Role.ASSISTANT]
    assert len(assistants) == 3
    assert assistants[0].text == ["ok"]
    assert assistants[0].tokens_in == 0
    assert assistants[0].tokens_out == 0
    assert assistants[1].tokens_in == 0
    assert assistants[1].tokens_out == 0
    assert len(assistants[1].tool_calls) == 1
    assert assistants[1].tool_calls[0].result_full == ""
    assert assistants[2].tokens_in == 5


def test_synthetic_model_not_counted_as_model_or_partial_cost(tmp_path):
    p = tmp_path / "synthetic.jsonl"
    lines = [
        {"type": "user", "timestamp": "2026-01-01T10:00:00Z", "message": {"role": "user", "content": "hi"}},
        {"type": "assistant", "timestamp": "2026-01-01T10:00:01Z", "message": {
            "id": "msg_real", "role": "assistant", "model": "claude-sonnet-4-6",
            "content": [{"type": "text", "text": "hello"}],
            "usage": {"input_tokens": 1000, "output_tokens": 100},
        }},
        {"type": "user", "timestamp": "2026-01-01T10:00:02Z", "message": {"role": "user", "content": "stop"}},
        {"type": "assistant", "timestamp": "2026-01-01T10:00:03Z", "isApiErrorMessage": True, "message": {
            "id": "msg_synth", "role": "assistant", "model": "<synthetic>",
            "content": [{"type": "text", "text": "API Error: synthetic placeholder"}],
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }},
    ]
    p.write_text("\n".join(json.dumps(line) for line in lines))

    t = parse(str(p))
    assert t.models == {"claude-sonnet-4-6"}
    assert t.cost_is_partial is False
    assert t.total_cost is not None
    # The placeholder message itself is kept: nothing is filtered out.
    synthetic = [m for m in t.messages if m.model == "<synthetic>"]
    assert len(synthetic) == 1
    assert synthetic[0].text == ["API Error: synthetic placeholder"]


def test_prompt_mentioning_command_tag_is_a_normal_user_message(tmp_path):
    from transcript.renderers.markdown import render

    prompt = "Why does my parser choke on <command-name>/model</command-name> tags in the middle of text?"
    p = tmp_path / "mention.jsonl"
    p.write_text(json.dumps({
        "type": "user", "timestamp": "2026-01-01T10:00:00Z",
        "message": {"role": "user", "content": prompt},
    }))

    t = parse(str(p))
    assert len(t.messages) == 1
    assert t.messages[0].command_name is None
    assert t.messages[0].text == [prompt]

    md = render(t)
    assert prompt in md
    assert "1 user" in md


def test_genuine_slash_command_user_entries_still_detected(tmp_path):
    p = tmp_path / "commands.jsonl"
    entries = [
        "<command-message>review</command-message>\n<command-name>/review</command-name>\n<command-args></command-args>",
        "<command-name>/clear</command-name>",
        "<local-command-stdout>done</local-command-stdout>",
        "<local-command-caveat>Caveat: generated by local commands</local-command-caveat>",
    ]
    p.write_text("\n".join(json.dumps({
        "type": "user", "timestamp": "2026-01-01T10:00:00Z",
        "message": {"role": "user", "content": c},
    }) for c in entries))

    t = parse(str(p))
    assert [m.command_name for m in t.messages] == [
        "/review", "/clear", "(command output)", "(command output)",
    ]
