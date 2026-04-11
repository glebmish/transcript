# Project: transcript

CLI + TUI tool for converting Claude Code and Gemini CLI conversation logs into readable Markdown transcripts.

## Commands

```bash
# Run tests
.venv/bin/pytest tests/ -v

# Run the tool
.venv/bin/python -m transcript <logfile>
.venv/bin/python -m transcript view <logfile>

# Or if installed
transcript <logfile>
```

## Structure

```
transcript/
    model.py          # Status, Role, ToolCall, Message, ToolStats, Transcript
    pricing.py        # PRICING dict, estimate_cost()
    detect.py         # format auto-detection
    parsers/
        claude.py     # JSONL parser -> Transcript
        gemini.py     # JSON parser -> Transcript
    renderers/
        markdown.py   # render(transcript, options) -> str
    tui/
        app.py        # textual Application
        widgets.py    # ConversationPanel, DetailPanel, ThinkingWidget, ToolCallWidget
    cli.py            # main() entry point, argparse
tests/
    fixtures/         # synthetic test data (no real user logs)
```

## Conventions

- All parsers produce a `Transcript` dataclass. Renderers and TUI consume only this model.
- Test fixtures must use generic/synthetic data, never real user logs.
- Cache reads and cache writes are treated as free for cost estimation.
- Claude's `input_tokens` is the uncached portion only; total context = `input_tokens + cache_creation_input_tokens + cache_read_input_tokens`.
- Tool use matching is ID-based (`tool_use.id` <-> `tool_result.tool_use_id`), not positional.
- `--expand-tools` shows full output with no truncation.
- Specs live in `docs/specs/`.
