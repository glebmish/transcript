import asyncio
from datetime import datetime, timezone

from transcript.model import Message, Role, Status, ToolCall, ToolStats, Transcript
from transcript.tui.app import TranscriptApp


def _markup_edge_transcript() -> Transcript:
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bad_markup = "` - malformed [bold markup\n"
    tool = ToolCall(
        name="Read",
        display_name="Read",
        summary="/tmp/[broken.py",
        result_summary="` - malformed [dim summary\n",
        result_full="line one\n` - malformed [red output\n",
        status=Status.PASSED,
    )
    return Transcript(
        messages=[
            Message(
                role=Role.USER,
                timestamp=ts,
                text=[bad_markup],
            ),
            Message(
                role=Role.ASSISTANT,
                timestamp=ts,
                thinking=[bad_markup],
                text=[bad_markup],
                tool_calls=[tool],
                content_order=[("thinking", 0), ("text", 0), ("tool", 0)],
            ),
        ],
        source_format="claude",
        session_id="synthetic",
        start_time=ts,
        end_time=ts,
        models={"synthetic"},
        total_tokens_in=0,
        total_tokens_out=0,
        total_cost=None,
        cost_is_partial=False,
        tool_stats=ToolStats(passed=1, failed=0, cancelled=0),
    )


def test_tui_renders_malformed_markup_like_text():
    async def run():
        app = TranscriptApp(_markup_edge_transcript())
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            assert app.query_one("ConversationPanel") is not None

            await pilot.press("j", "enter")
            await pilot.pause()

            await pilot.press("j", "j", "enter")
            await pilot.pause()

            await pilot.press("enter")
            await pilot.pause()

            await pilot.press("j", "j", "enter")
            await pilot.pause()

    asyncio.run(run())


_OSC52 = "\x1b]52;c;ZWNobyBwd25lZAo=\x1b\\"


def _transcript(messages, models=None) -> Transcript:
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return Transcript(
        messages=messages,
        source_format="claude",
        session_id="synthetic",
        start_time=ts,
        end_time=ts,
        models=models if models is not None else {"synthetic"},
        total_tokens_in=0,
        total_tokens_out=0,
        total_cost=None,
        cost_is_partial=False,
        tool_stats=ToolStats(passed=1, failed=0, cancelled=0),
    )


def _rendered_text(app) -> str:
    """Text of every segment the app's Static widgets actually render."""
    from textual.geometry import Region
    from textual.widgets import Static

    chunks = []
    for widget in app.query(Static):
        width, height = widget.size
        if not width or not height:
            continue
        for strip in widget.render_lines(Region(0, 0, width, height)):
            chunks.append("".join(seg.text for seg in strip))
    return "\n".join(chunks)


def test_tui_never_renders_escape_characters():
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    tool = ToolCall(
        name="Bash", display_name="Bash", summary=f"echo {_OSC52}",
        result_summary="\x1b[2Jdone", result_full=f"line\n{_OSC52}\x9b31m",
        status=Status.PASSED,
    )
    transcript = _transcript([
        Message(role=Role.USER, timestamp=ts, text=[f"user {_OSC52}"]),
        Message(
            role=Role.ASSISTANT, timestamp=ts, model=f"model{_OSC52}",
            thinking=[f"thinking {_OSC52}"], text=[f"answer {_OSC52}"], tool_calls=[tool],
            content_order=[("thinking", 0), ("text", 0), ("tool", 0)],
        ),
        Message(role=Role.USER, timestamp=ts, text=[f"<command-name>/x{_OSC52}</command-name>"],
                command_name=f"/x{_OSC52}"),
    ], models={f"model{_OSC52}"})

    async def run():
        app = TranscriptApp(transcript)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            seen = [_rendered_text(app)]
            # header(user), user text, header(asst), thinking -> expand inline
            await pilot.press("j", "j", "j", "enter")
            await pilot.pause()
            seen.append(_rendered_text(app))
            # thinking again -> detail panel
            await pilot.press("enter")
            await pilot.pause()
            seen.append(_rendered_text(app))
            # text, tool -> detail panel
            await pilot.press("j", "j", "enter")
            await pilot.pause()
            seen.append(_rendered_text(app))
            for text in seen:
                assert "\x1b" not in text
                assert "\x9b" not in text
            # The payload is still visible, just inert.
            assert "␛]52;c;ZWNobyBwd25lZAo=" in seen[-1]

    asyncio.run(run())


def test_tui_markup_in_model_and_command_name_is_literal():
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    transcript = _transcript([
        Message(role=Role.USER, timestamp=ts, text=["hi"]),
        Message(role=Role.ASSISTANT, timestamp=ts, model="bad[/nope]", text=["ok"]),
        Message(role=Role.USER, timestamp=ts, text=["<command-name>[blink red]x[/]</command-name>"],
                command_name="[blink red]x[/] bad[/nope]"),
    ], models={"bad[/nope]", "[blink red]x[/]"})

    async def run():
        app = TranscriptApp(transcript)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            text = _rendered_text(app)
            assert "bad[/nope]" in text
            assert "[blink red]x[/]" in text

    asyncio.run(run())


def test_search_ignores_header_markup_and_matches_visible_text():
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    transcript = _transcript([
        Message(role=Role.USER, timestamp=ts, text=["hello"]),
        Message(role=Role.ASSISTANT, timestamp=ts, model="m", tokens_in=5, text=["world"]),
    ])

    async def run():
        app = TranscriptApp(transcript)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            for markup_word in ("cyan", "bold", "green", "dim", "[/"):
                assert app._find_matches(markup_word) == []
            headers = app._find_matches("## assistant")
            assert len(headers) == 1
            assert headers[0].searchable_text.startswith("## Assistant")
            assert len(app._find_matches("## user")) == 1

    asyncio.run(run())


def test_thinking_line_count_is_singular_for_one_line():
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    transcript = _transcript([
        Message(role=Role.ASSISTANT, timestamp=ts, thinking=["one", "two\nlines"],
                content_order=[("thinking", 0), ("thinking", 1)]),
    ])

    async def run():
        app = TranscriptApp(transcript)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            text = _rendered_text(app)
            assert "Thinking (1 line)" in text
            assert "Thinking (2 lines)" in text

    asyncio.run(run())


def test_help_lists_search_navigation_keys():
    transcript = _transcript([Message(role=Role.USER, timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc), text=["hi"])])

    async def run():
        app = TranscriptApp(transcript)
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.press("question_mark")
            await pilot.pause()
            text = _rendered_text(app)
            assert "n / N" in text
            assert "Next / previous search match" in text

    asyncio.run(run())


def _summary_line(app) -> str:
    return next(line for line in _rendered_text(app).splitlines() if "Tools:" in line)


def test_summary_shows_cancelled_tool_count():
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    msgs = [Message(role=Role.USER, timestamp=ts, text=["hi"])]
    with_cancel = _transcript(msgs)
    with_cancel.tool_stats = ToolStats(passed=2, failed=1, cancelled=3)
    no_cancel = _transcript(msgs)
    no_cancel.tool_stats = ToolStats(passed=2, failed=1, cancelled=0)

    async def run(t):
        app = TranscriptApp(t)
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            return _summary_line(app)

    assert "Tools: 6 (1 x, 3 cancelled)" in asyncio.run(run(with_cancel))
    line = asyncio.run(run(no_cancel))
    assert "Tools: 3 (1 x)" in line
    assert "cancelled" not in line
