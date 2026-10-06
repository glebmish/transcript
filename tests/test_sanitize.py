import json
from datetime import datetime, timezone

from transcript.model import Message, Role, Status, ToolCall, ToolStats, Transcript
from transcript.parsers.claude import parse as parse_claude
from transcript.renderers.markdown import render, RenderOptions
from transcript.sanitize import sanitize_text, sanitize_transcript

OSC52 = "\x1b]52;c;ZWNobyBwd25lZAo=\x1b\\"


def test_c0_controls_become_control_pictures():
    assert sanitize_text("a\x1bb") == "a␛b"
    assert sanitize_text("\x00\x07\x08") == "␀␇␈"
    assert sanitize_text(OSC52) == "␛]52;c;ZWNobyBwd25lZAo=␛\\"


def test_newline_and_tab_are_kept():
    assert sanitize_text("a\n\tb") == "a\n\tb"


def test_crlf_normalized_and_lone_cr_visible():
    assert sanitize_text("a\r\nb") == "a\nb"
    assert sanitize_text("progress 10%\rprogress 99%") == "progress 10%␍progress 99%"


def test_del_and_c1_controls_are_visible():
    assert sanitize_text("x\x7fy") == "x␡y"
    assert sanitize_text("\x9b31m") == "\\x9b31m"
    assert sanitize_text("\x80\x9f") == "\\x80\\x9f"


def test_printable_unicode_untouched():
    text = "café → 日本 \U0001F600"
    assert sanitize_text(text) == text


def _hostile_transcript() -> Transcript:
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    tool = ToolCall(
        name="Bash", display_name="Bash", summary=f"echo {OSC52}",
        result_summary=f"\x1b[2Jcleared", result_full=f"out\x1b]0;pwned title\x07\n{OSC52}",
        status=Status.PASSED,
    )
    return Transcript(
        messages=[
            Message(role=Role.USER, timestamp=ts, text=[f"user {OSC52}"]),
            Message(
                role=Role.ASSISTANT, timestamp=ts, model="claude-sonnet-4-6",
                thinking=[f"thinking {OSC52}"], text=[f"answer {OSC52}"], tool_calls=[tool],
                content_order=[("thinking", 0), ("text", 0), ("tool", 0)],
            ),
        ],
        source_format="claude", session_id="s", start_time=ts, end_time=ts,
        models={"claude-sonnet-4-6"}, total_tokens_in=0, total_tokens_out=0,
        total_cost=None, cost_is_partial=False,
        tool_stats=ToolStats(passed=1, failed=0, cancelled=0),
    )


def test_markdown_output_has_no_escape_characters():
    for opts in (RenderOptions(), RenderOptions(expand_tools=True)):
        md = render(_hostile_transcript(), opts)
        assert "\x1b" not in md
        assert "\x07" not in md
        assert "␛]52;c;ZWNobyBwd25lZAo=" in md  # still visible


def test_sanitize_transcript_covers_all_string_fields():
    t = sanitize_transcript(_hostile_transcript())
    asst = t.messages[1]
    tc = asst.tool_calls[0]
    for s in [*t.messages[0].text, *asst.thinking, *asst.text,
              tc.summary, tc.result_summary, tc.result_full]:
        assert "\x1b" not in s
        assert "\x07" not in s
    assert asst.content_order == [("thinking", 0), ("text", 0), ("tool", 0)]


def test_sanitize_transcript_does_not_mutate_input():
    original = _hostile_transcript()
    sanitize_transcript(original)
    assert "\x1b" in original.messages[0].text[0]


def test_unknown_subtype_warning_does_not_echo_escapes(tmp_path, capsys):
    p = tmp_path / "evil_subtype.jsonl"
    p.write_text(json.dumps({"type": "system", "subtype": f"evil{OSC52}", "timestamp": "2026-01-01T10:00:00Z"}))
    parse_claude(str(p))
    err = capsys.readouterr().err
    assert "unknown system subtype" in err
    assert "\x1b" not in err
