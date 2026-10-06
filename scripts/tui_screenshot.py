"""Regenerate docs/images/tui.svg, the TUI screenshot shown in the README.

Run from the repo root after any change that affects what the TUI shows:

    .venv/bin/python scripts/tui_screenshot.py
"""

import asyncio
from pathlib import Path

from transcript.model import Status
from transcript.parsers.claude import parse
from transcript.tui.app import TranscriptApp

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "claude_minimal.jsonl"
OUT_DIR = ROOT / "docs" / "images"


async def main() -> None:
    app = TranscriptApp(parse(str(FIXTURE)))
    async with app.run_test(size=(100, 26)) as pilot:
        await pilot.pause()
        # Move down to the failed tool call and open it in the detail panel.
        for _ in range(40):
            tool_call = getattr(app.focused, "tool_call", None)
            if tool_call is not None and tool_call.status == Status.FAILED:
                break
            await pilot.press("j")
            await pilot.pause()
        else:
            raise SystemExit("no failed tool call found in the fixture")
        await pilot.press("enter")
        await pilot.pause()
        app.save_screenshot(filename="tui.svg", path=str(OUT_DIR))
    print(f"wrote {OUT_DIR / 'tui.svg'}")


if __name__ == "__main__":
    asyncio.run(main())
