# Project: transcript

CLI + TUI tool for converting Claude Code, Gemini CLI and Codex conversation logs into readable Markdown transcripts.

## Commands

```bash
# Run tests and lint (same checks as CI)
.venv/bin/pytest tests/ -v
.venv/bin/ruff check .

# Run the tool (must be installed: pip install -e .)
transcript <logfile>
transcript view <logfile>
```

- Always use `transcript` as a CLI command, never `python -m transcript`.

## Structure

```text
transcript/
    __main__.py       # python -m entry point (calls cli.main)
    model.py          # Status, Role, ToolCall, Message, ToolStats, Transcript
    pricing.py        # PRICING dict, estimate_cost()
    detect.py         # format auto-detection
    sanitize.py       # neutralize terminal control characters in log text
    parsers/
        common.py     # as_* coercions, is_real_model, count_label
        claude.py     # JSONL parser -> Transcript
        gemini.py     # JSON parser -> Transcript
        codex.py      # Codex JSONL parser -> Transcript
    renderers/
        markdown.py   # render(transcript, options) -> str
    tui/
        app.py        # textual Application
        widgets.py    # GutterRow, MessageHeaderWidget, MessageTextWidget, ToolCallWidget,
                      # ThinkingWidget, ConversationPanel, DetailPanel
    cli.py            # main() entry point, argparse
tests/
    fixtures/         # synthetic test data (no real user logs)
```

## Conventions

- All parsers produce a `Transcript` dataclass. Renderers and TUI consume only this model.
- Test fixtures must use generic/synthetic data, never real user logs.
- Cache reads and cache writes are treated as free for cost estimation.
- Claude's `input_tokens` is the uncached portion only; total context = `input_tokens + cache_creation_input_tokens + cache_read_input_tokens`.
- Tool use matching is ID-based (`tool_use.id` <-> `tool_result.tool_use_id`; Codex uses `call_id`), not positional.
- `--expand-tools` shows full output with no truncation.
- `Message.content_order` tracks interleaved thinking/text/tool sequence. Renderers iterate it when non-empty, fall back to legacy order otherwise.
- `Message.command_name` is set for local slash commands: from `local_command` system entries, and from user text that starts with `<command-name>`, `<command-message>`, `<local-command-caveat>` or `<local-command-stdout>`. These are not counted as user messages.
- Transcript tool's primary goal is full visibility into agent session internals — nothing is filtered out.
- Specs live in `docs/specs/` and are living documents — update them when the implementation changes.

## Agent skill trees

- `.claude/skills/` and `.agents/skills/` are optional maintainer tooling for coding agents. They are not needed to build, test or use the tool.
- Some skills depend on the maintainer's personal setup: Cloudinary (`CLOUDINARY_URL`, the `cld` CLI), `textimg`, ImageMagick, a JetBrainsMono Nerd Font path, and tmux/cmux.
- `session-reflection/reflect.py` is experimental and uses its own pricing model (it charges cache writes and reads), which differs from `transcript/pricing.py`.
- The `.agents` copy is adapted from the `.claude` copy, and some pieces still assume Claude Code paths (for example `~/.claude/projects` in `reflect.py`).
