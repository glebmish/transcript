# Project: transcript

CLI + TUI tool for converting Codex and Gemini CLI conversation logs into readable Markdown transcripts.

## Commands

```bash
# Run tests
.venv/bin/pytest tests/ -v

# Run the tool (must be installed: pip install -e .)
transcript <logfile>
transcript view <logfile>
```

- Always use `transcript` as a CLI command, never `python -m transcript`.

## Structure

```
transcript/
    model.py          # Status, Role, ToolCall, Message, ToolStats, Transcript
    pricing.py        # PRICING dict, estimate_cost()
    detect.py         # format auto-detection
    parsers/
        Codex.py     # JSONL parser -> Transcript
        gemini.py     # JSON parser -> Transcript
    renderers/
        markdown.py   # render(transcript, options) -> str
    tui/
        app.py        # textual Application
        widgets.py    # GutterRow, ConversationPanel, DetailPanel, ThinkingWidget, ToolCallWidget
    cli.py            # main() entry point, argparse
tests/
    fixtures/         # synthetic test data (no real user logs)
```

## Conventions

- All parsers produce a `Transcript` dataclass. Renderers and TUI consume only this model.
- Test fixtures must use generic/synthetic data, never real user logs.
- Cache reads and cache writes are treated as free for cost estimation.
- Codex's `input_tokens` is the uncached portion only; total context = `input_tokens + cache_creation_input_tokens + cache_read_input_tokens`.
- Tool use matching is ID-based (`tool_use.id` <-> `tool_result.tool_use_id`), not positional.
- `--expand-tools` shows full output with no truncation.
- `Message.content_order` tracks interleaved thinking/text/tool sequence. Renderers iterate it when non-empty, fall back to legacy order otherwise.
- `Message.command_name` is set for local slash commands (parsed from `local_command` system entries). These are not counted as user messages.
- Transcript tool's primary goal is full visibility into agent session internals — nothing is filtered out.
- Specs live in `docs/specs/` and are living documents — update them when the implementation changes.
