# transcript

Convert Claude Code and Gemini CLI conversation logs into readable Markdown transcripts, or browse them interactively in a terminal UI.

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
ln -sf "$(pwd)/.venv/bin/transcript" ~/.local/bin/transcript
```

## Usage

### CLI — Markdown output

```bash
# Auto-detects format (Claude JSONL or Gemini JSON)
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

Format is auto-detected. Use `--format claude` or `--format gemini` to override.

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
| claude-opus-4-6 | $5.00 | $25.00 |
| claude-sonnet-4-6 | $3.00 | $15.00 |
| claude-haiku-4-5 | $1.00 | $5.00 |
| gemini-2.5-pro | $1.00 | $10.00 |
| gemini-2.5-flash | $0.30 | $2.50 |

## Requirements

- Python 3.12+
- textual, rich (installed automatically)
