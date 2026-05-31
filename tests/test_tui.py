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
