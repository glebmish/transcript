# CLI Design

## Entry Point

`transcript` — installed as a console script via `pip install -e .`.

## Usage

```
transcript [options] <input_file>
transcript view [options] <input_file>
```

- No subcommand: CLI mode — convert log to markdown, write to stdout or file.
- `view` subcommand: launch interactive TUI.

## Log Locations

| Agent | Location | Format |
|-------|----------|--------|
| Claude Code | `~/.claude/projects/<project-hash>/<session-id>.jsonl` | JSONL, one entry per line |
| Gemini CLI | `~/.gemini/tmp/<project-hash>/chats/session-<timestamp>-<uuid>.json` | Single JSON file |

## Format Detection

Auto-detect by default:

1. Try `json.load()` — if succeeds, has top-level `messages` array, **and** has a `sessionId` field, it's Gemini.
2. Otherwise read line-by-line as JSONL — if first valid JSON line has `type` field with value in `("user", "assistant", "system", "progress", "attachment")`, it's Claude.
3. If neither matches, exit with error naming the file and what was found (e.g. "Could not detect format: <file> has no 'sessionId' field and no valid JSONL entries").

`--format claude|gemini` overrides auto-detection.

## Content Control Flags

| Flag | Default | Effect |
|------|---------|--------|
| `--no-thinking` | show | Exclude thinking blocks |
| `--no-tools` | show | Exclude tool calls entirely |
| `--no-text` | show | Exclude assistant response text |
| `--no-cost` | show | Exclude cost/token info from headers |
| `--expand-tools` | collapsed | Show full tool output instead of compact summary (no truncation — full output always shown) |

Flags are `--no-*` because the default is to include everything. `--expand-tools` is the exception — default is compact.

## Output Control

| Flag | Default | Effect |
|------|---------|--------|
| `-o`, `--output` | stdout | Write to file |

## Markdown Output Layout

Summary header, then messages separated by `---`. Each element is controlled by flags:

- Summary header: Duration, Model(s), Messages always shown. Tool calls and Tokens lines hidden by `--no-cost`.
- User messages: header with timestamp, then message text.
- Assistant messages: header with timestamp (and token/cost info unless `--no-cost`), then thinking blocks (unless `--no-thinking`), then response text (unless `--no-text`), then tool call block (unless `--no-tools`).
- Tool calls: fenced code block, one line per call (`ToolName: summary -> result`).
- Compaction markers (Claude only): rendered as `--- conversation compacted ---` between messages.

With `--expand-tools`, each tool call is followed by its full output. No truncation — the complete output is always included.

## Examples

```bash
# Basic conversion (auto-detect format)
transcript session.jsonl

# Tools-only view: what did it do?
transcript --no-thinking --no-text session.jsonl

# Minimal: just the header stats
transcript --no-thinking --no-tools --no-text session.jsonl

# Full detail with expanded tool output
transcript --expand-tools session.jsonl -o review.md

# Launch TUI
transcript view session.jsonl
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Parse error (malformed input, unrecognized format) |
| 2 | File not found |
