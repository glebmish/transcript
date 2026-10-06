from datetime import datetime, timezone
from transcript.model import Status, Role, ToolCall, Message, ToolStats, Transcript
from transcript.renderers.markdown import render, RenderOptions


def _make_transcript(messages, **kwargs):
    defaults = dict(
        source_format="claude",
        session_id=None,
        start_time=messages[0].timestamp if messages else datetime.min.replace(tzinfo=timezone.utc),
        end_time=messages[-1].timestamp if messages else datetime.min.replace(tzinfo=timezone.utc),
        models={"claude-opus-4-6"},
        total_tokens_in=10000,
        total_tokens_out=500,
        total_cost=0.045,
        cost_is_partial=False,
        tool_stats=ToolStats(passed=1, failed=1, cancelled=0),
    )
    defaults.update(kwargs)
    return Transcript(messages=messages, **defaults)


TS1 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
TS2 = datetime(2026, 1, 1, 10, 0, 5, tzinfo=timezone.utc)


def test_render_summary_header():
    t = _make_transcript([
        Message(role=Role.USER, timestamp=TS1, text=["hello"]),
        Message(role=Role.ASSISTANT, timestamp=TS2, model="claude-opus-4-6",
                tokens_in=10000, tokens_out=500, text=["hi"]),
    ])
    md = render(t)
    assert "# Transcript" in md
    assert "Duration" in md
    assert "claude-opus-4-6" in md
    assert "2 (1 user, 1 assistant)" in md


def test_render_instruction_roles_visible_but_not_counted():
    t = _make_transcript([
        Message(role=Role.DEVELOPER, timestamp=TS1, text=["Follow project conventions"]),
        Message(role=Role.USER, timestamp=TS1, text=["hello"]),
        Message(role=Role.ASSISTANT, timestamp=TS2, model="claude-opus-4-6", text=["hi"]),
    ])
    md = render(t)
    assert "## Developer" in md
    assert "Follow project conventions" in md
    assert "2 (1 user, 1 assistant)" in md


def test_render_no_thinking():
    t = _make_transcript([
        Message(role=Role.ASSISTANT, timestamp=TS1, model="claude-opus-4-6",
                thinking=["secret thoughts"], text=["visible"]),
    ])
    md = render(t, RenderOptions(show_thinking=False))
    assert "secret thoughts" not in md
    assert "visible" in md


def test_render_no_tools():
    t = _make_transcript([
        Message(role=Role.ASSISTANT, timestamp=TS1, model="claude-opus-4-6",
                text=["visible"], tool_calls=[
                    ToolCall(name="Read", display_name="Read", summary="/f.py",
                             result_summary="10 lines", result_full="content", status=Status.PASSED)
                ]),
    ])
    md = render(t, RenderOptions(show_tools=False))
    assert "Read" not in md


def test_render_no_text():
    t = _make_transcript([
        Message(role=Role.ASSISTANT, timestamp=TS1, model="claude-opus-4-6",
                text=["hidden text"], tool_calls=[
                    ToolCall(name="Read", display_name="Read", summary="/f.py",
                             result_summary="10 lines", result_full="content", status=Status.PASSED)
                ]),
    ])
    md = render(t, RenderOptions(show_text=False))
    assert "hidden text" not in md
    assert "Read" in md


def test_render_no_cost():
    t = _make_transcript([
        Message(role=Role.ASSISTANT, timestamp=TS1, model="claude-opus-4-6",
                tokens_in=10000, tokens_out=500, text=["hi"]),
    ])
    md = render(t, RenderOptions(show_cost=False))
    assert "$" not in md
    assert "\u2191" not in md  # ↑


def test_render_expand_tools():
    t = _make_transcript([
        Message(role=Role.ASSISTANT, timestamp=TS1, model="claude-opus-4-6",
                text=["ok"], tool_calls=[
                    ToolCall(name="Bash", display_name="Bash", summary="ls",
                             result_summary="ok", result_full="file1.py\nfile2.py", status=Status.PASSED)
                ]),
    ])
    md = render(t, RenderOptions(expand_tools=True))
    assert "file1.py" in md
    assert "file2.py" in md


def test_render_compaction_marker():
    t = _make_transcript([
        Message(role=Role.USER, timestamp=TS1, text=["before"]),
        Message(role=Role.USER, timestamp=TS1, is_compaction_marker=True, text=["Conversation compacted"]),
        Message(role=Role.USER, timestamp=TS2, text=["after"]),
    ])
    md = render(t)
    assert "conversation compacted" in md.lower()
    assert "before" in md
    assert "after" in md


def test_render_partial_cost():
    t = _make_transcript([
        Message(role=Role.ASSISTANT, timestamp=TS1, model="claude-opus-4-6",
                tokens_in=10000, tokens_out=500, text=["hi"]),
    ], total_cost=0.045, cost_is_partial=True)
    md = render(t)
    assert "partial" in md.lower()


def test_render_empty():
    t = _make_transcript([], models=set(), total_tokens_in=0, total_tokens_out=0,
                          total_cost=None, tool_stats=ToolStats(0, 0, 0))
    md = render(t)
    assert "No messages" in md


def _tool_msg(tc, ordered=True):
    return Message(
        role=Role.ASSISTANT, timestamp=TS1, model="claude-opus-4-6",
        text=["after"], tool_calls=[tc],
        content_order=[("tool", 0), ("text", 0)] if ordered else [],
    )


def test_expanded_fence_longer_than_backticks_in_output():
    output = "```python\nprint('x')\n```\n\n# Not a heading\n`````"
    tc = ToolCall(name="Read", display_name="Read", summary="/README.md",
                  result_summary="6 lines", result_full=output, status=Status.PASSED)
    for ordered in (True, False):
        md = render(_make_transcript([_tool_msg(tc, ordered)]), RenderOptions(expand_tools=True))
        assert "``````\n" + output + "\n``````" in md


def test_expanded_fence_minimum_is_three_backticks():
    tc = ToolCall(name="Bash", display_name="Bash", summary="ls",
                  result_summary="ok", result_full="a `b` c", status=Status.PASSED)
    md = render(_make_transcript([_tool_msg(tc)]), RenderOptions(expand_tools=True))
    assert "```\na `b` c\n```" in md


def test_compact_inline_span_longer_than_backticks():
    tc = ToolCall(name="Bash", display_name="Bash", summary="echo ``x``",
                  result_summary="ok", result_full="", status=Status.PASSED)
    md = render(_make_transcript([_tool_msg(tc)]))
    assert "```Bash: echo ``x`` → ok```" in md


def test_compact_inline_span_padded_when_edge_is_backtick():
    tc = ToolCall(name="Bash", display_name="Bash", summary="echo",
                  result_summary="`ok`", result_full="", status=Status.PASSED)
    md = render(_make_transcript([_tool_msg(tc)]))
    assert "`` Bash: echo → `ok` ``" in md


def test_compact_batch_fence_longer_than_backticks():
    tc = ToolCall(name="Bash", display_name="Bash", summary="cat ```",
                  result_summary="ok", result_full="", status=Status.PASSED)
    md = render(_make_transcript([_tool_msg(tc, ordered=False)]))
    assert "````\nBash: cat ``` → ok\n````" in md


def test_synthetic_assistant_header_has_no_cost():
    t = _make_transcript([
        Message(role=Role.ASSISTANT, timestamp=TS1, model="<synthetic>", text=["API Error"]),
    ], models=set(), total_cost=None)
    header = next(line for line in render(t).splitlines() if line.startswith("## Assistant"))
    assert header == "## Assistant · 2026-01-01 10:00:00 · ↑0 ↓0"
    assert "$" not in header


def test_real_model_assistant_header_keeps_cost():
    t = _make_transcript([
        Message(role=Role.ASSISTANT, timestamp=TS1, model="claude-opus-4-6",
                tokens_in=1000, tokens_out=100, text=["hi"]),
    ])
    header = next(line for line in render(t).splitlines() if line.startswith("## Assistant"))
    assert header.endswith("· $0.0075")


def test_tool_call_header_shows_cancelled_when_present():
    msg = Message(role=Role.USER, timestamp=TS1, text=["hi"])
    md = render(_make_transcript([msg], tool_stats=ToolStats(passed=2, failed=1, cancelled=3)))
    assert "- **Tool calls**: 6 (2 passed, 1 failed, 3 cancelled)" in md


def test_tool_call_header_omits_zero_cancelled():
    msg = Message(role=Role.USER, timestamp=TS1, text=["hi"])
    md = render(_make_transcript([msg], tool_stats=ToolStats(passed=2, failed=1, cancelled=0)))
    assert "- **Tool calls**: 3 (2 passed, 1 failed)\n" in md
