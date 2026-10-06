# transcript

Convert Claude Code, Gemini CLI, and Codex conversation logs into readable Markdown transcripts, or browse them interactively in a terminal UI.

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
ln -sf "$(pwd)/.venv/bin/transcript" ~/.local/bin/transcript
```

## Usage

### CLI — Markdown output

```bash
# Auto-detects format (Claude JSONL, Gemini JSON, or Codex JSONL)
transcript session.jsonl

# Write to file
transcript -o review.md session.jsonl

# Tools-only view: what did the agent do?
transcript --no-thinking --no-text session.jsonl

# Just the header stats
transcript --no-thinking --no-tools --no-text session.jsonl

# Full tool output (no truncation)
transcript --expand-tools session.jsonl

# Hide cost/token info
transcript --no-cost session.jsonl

# Force format
transcript --format claude session.jsonl
transcript --format codex session.jsonl
```

### TUI — Interactive viewer

```bash
transcript view session.jsonl
```

```
+-- Conversation ------------------------------------+-- Detail ----------------+
| # Transcript                                       |                          |
| Duration: 12m · claude-opus-4-6                    |  (empty until            |
| Messages: 8 · Tools: 12 (1 x) · $0.42             |   something is           |
|                                                    |   selected)              |
| -------------------------------------------------- |                          |
|                                                    |                          |
| ## User · 14:02:03                                 |                          |
| Help me refactor auth                              |                          |
|                                                    |                          |
| ## Assistant · 14:02:08 · ^12k v1.2k               |                          |
| > Thinking (3 lines)                         [>]   |                          |
|                                                    |                          |
| I'll start by reading the middleware.              |                          |
|                                                    |                          |
|   Read: /src/auth.py -> 84 lines             [>]   |                          |
|   Grep: session_token in src/ -> 12          [>]   |                          |
| x Bash: pytest tests/ -> FAILED              [>]   |                          |
|                                                    |                          |
| ## User · 14:03:15                                 |                          |
| focus on the jwt validation                        |                          |
+----------------------------------------------------+--------------------------+
 [t]hinking [/]search [q]uit [tab]panel [h]ide [?]help
```

**Keybindings:**

| Key | Action |
|-----|--------|
| `j/k`, Up/Down | Scroll conversation |
| `Enter` | Expand focused item into detail panel |
| `t` | Toggle all thinking blocks |
| `h` | Cycle visibility: all / assistant only / user only |
| `Tab` | Switch focus between panels |
| `Esc` | Close detail panel |
| `?` | Show help |
| `q` | Quit |

## Log locations

| Agent | Path | Format |
|-------|------|--------|
| Claude Code | `~/.claude/projects/<hash>/<session>.jsonl` | JSONL |
| Gemini CLI | `~/.gemini/tmp/<hash>/chats/session-*.json` | JSON |
| Codex CLI/Desktop | `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` | JSONL |

Format is auto-detected. Use `--format claude`, `--format gemini`, or `--format codex` to override.

## Output example

```markdown
# Transcript

- **Duration**: 12m 34s (2026-03-18 14:02:03 -> 14:14:37)
- **Model(s)**: claude-opus-4-6
- **Messages**: 8 (3 user, 5 assistant)
- **Tool calls**: 12 (11 passed, 1 failed)
- **Tokens**: ^32,450 v8,120 · $0.42

---

## User · 2026-03-18 14:02:03

Help me refactor auth

---

## Assistant · 2026-03-18 14:02:08 · ^12,300 v1,200 · $0.08

> Let me explore the current auth implementation.

I'll start by reading the middleware.

```
Read: /src/middleware/auth.py -> 84 lines
Grep: session_token in src/ -> 12 matches
Bash: pytest tests/ -> FAILED (exit 1)
```
```

## Cost estimation

Cached tokens (cache reads and cache writes) are treated as free. Only uncached input tokens are billed.

| Model | Input (per 1M) | Output (per 1M) |
|-------|---------------|-----------------|
| claude-fable-5-1 | $10.00 | $50.00 |
| claude-fable-5 | $10.00 | $50.00 |
| claude-opus-5-5 | $4.00 | $20.00 |
| claude-opus-5 | $5.00 | $25.00 |
| claude-opus-4-8 | $5.00 | $25.00 |
| claude-opus-4-7 | $5.00 | $25.00 |
| claude-opus-4-6 | $5.00 | $25.00 |
| claude-opus-4-5 | $5.00 | $25.00 |
| claude-opus-4-1 | $15.00 | $75.00 |
| claude-opus-4-0 (`claude-opus-4-20250514`) | $15.00 | $75.00 |
| claude-sonnet-5-5 | $2.00 | $10.00 |
| claude-sonnet-5 | $2.00 | $10.00 |
| claude-sonnet-4-6 | $3.00 | $15.00 |
| claude-sonnet-4-5 | $3.00 | $15.00 |
| claude-sonnet-4-0 (`claude-sonnet-4-20250514`) | $3.00 | $15.00 |
| claude-haiku-4-5 | $1.00 | $5.00 |
| gemini-2.5-pro | $1.25 | $10.00 |
| gemini-2.5-flash | $0.30 | $2.50 |
| gemini-2.5-flash-lite | $0.10 | $0.40 |

Model ids are matched by the longest table entry they start with, so dated ids such as `claude-sonnet-4-5-20250929` use the `claude-sonnet-4-5` price, and `gemini-2.5-flash-lite` is not priced as `gemini-2.5-flash`.

`gemini-2.5-pro` uses the price for prompts up to 200k tokens; the higher long-prompt tier is not modeled.

Models not in the table show cost as unknown (`$?`), or as `(partial)` when only some messages could be priced. This includes all OpenAI/Codex models: Codex transcripts show tokens but no cost estimate.

## Requirements

- Python 3.12+
- textual, rich (installed automatically)
