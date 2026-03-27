# Agent Log Transcript Tool — Design Spec

## Overview

A single-file Python script that converts agent conversation logs (Claude Code or Gemini CLI) into compact, readable Markdown transcripts.

## CLI Interface

```
python transcript.py --format claude|gemini <input_file> [-o output.md]
```

- `--format` / `-f` (required): `claude` or `gemini`
- Positional: path to input file (JSONL for Claude, JSON for Gemini)
- `-o` (optional): output file path. Defaults to stdout.

## Input Formats

### Claude Code

- Location: `~/.claude/projects/<project>/` — JSONL files
- Each line is a JSON object with fields:
  - `type`: `"user"` or `"assistant"`
  - `timestamp`: ISO 8601
  - `message.content[]`: array of content blocks, each with a `type` field:
    - `{"type": "text", "text": "..."}` — text content
    - `{"type": "thinking", "thinking": "..."}` — extended thinking
    - `{"type": "tool_use", "id": "toolu_...", "name": "Read", "input": {...}}` — tool invocation
    - `{"type": "tool_result", "tool_use_id": "toolu_...", "content": "..."}` — tool result (in subsequent user-type entries)
  - `message.model`: string, present on assistant messages only (e.g. `"claude-opus-4-6"`)
  - `message.usage`: `{input_tokens, output_tokens}` — present on assistant messages only
  - `toolUseResult`: structured result at root level of user-type entries, one per JSONL line, linked to the preceding `tool_use` block by position (each tool_use in an assistant message produces one subsequent user-type line with `toolUseResult`)
- **Pass/fail detection**: a tool call is considered failed if the `tool_result` content block has `"is_error": true`, or if `toolUseResult` contains an error indicator. Otherwise it's a pass.

### Gemini CLI

- Location: project-specific `chats/` dirs — single JSON files
- Top-level `messages[]` array with fields:
  - `type`: `"user"`, `"gemini"`, `"info"`
  - `timestamp`: ISO 8601
  - `content`: string (gemini) or array of `{text}` (user)
  - `thoughts[]`: array of `{subject, description, timestamp}`
  - `toolCalls[]`: array of `{name, args, result, status}`
  - `tokens`: `{input, output, cached, thoughts, tool, total}`
  - `model`: string

## Output Format

### Summary Header

```markdown
# Transcript

- **Duration**: 12m 34s (2026-03-18 14:02:03 → 14:14:37)
- **Model(s)**: claude-opus-4-6
- **Messages**: 8 (3 user, 5 assistant)
- **Tool calls**: 12 (11 passed, 1 failed)
- **Tokens**: ↑32,450 ↓8,120 · $0.42
```

Fields:
- Duration with absolute start/end times
- Model(s) used (deduplicated)
- Message count with breakdown by role
- Tool call count with pass/fail breakdown
- Total input (↑) and output (↓) tokens with estimated cost

### Message Format

Messages are separated by `---`. Each message has a level-2 header:

**User messages:**
```markdown
---

## User · 2026-03-18 14:02:03

<message text>
```

**Assistant messages:**
```markdown
---

## Assistant · 2026-03-18 14:02:08 · ↑12,300 ↓1,200 · $0.08

<message text>
```

Token info (↑input ↓output · cost) appears only on assistant messages.

### Thinking Blocks

Rendered as blockquotes:

```markdown
> Let me explore the current auth implementation to understand the existing pattern.
```

For Gemini, each thought's description becomes a blockquote. Multiple thoughts become consecutive blockquotes.

### Tool Calls

Rendered in fenced code blocks. Consecutive tool calls are grouped into a single block:

````markdown
```
Read: /src/middleware/auth.py → 84 lines
Grep: session_token in src/ → 12 matches
Bash: pip list | grep jwt → PyJWT 2.8.0
Read: /src/config.py → 45 lines
```
````

Each line: `ToolName: <key_param> → <compact_result>`

**Result formatting rules:**
- Success with countable output: `→ 84 lines`, `→ 12 matches`
- Success with short output (single line, ≤50 chars): show full output inline, e.g. `→ PyJWT 2.8.0`
- Success with long/multi-line output: `→ ok` or `→ <N> lines`
- Failure: `→ FAILED` (with exit code if available, e.g. `→ FAILED (exit 1)`)

**Tool-specific key params:**
- `Read`: file path
- `Write`/`Edit`: file path
- `Bash`: `description` field from `input` if present, otherwise `command` field truncated to 80 chars
- `Grep`: pattern + path
- `Glob`: pattern
- `WebFetch`/`WebSearch`: URL or query
- Other/unknown tools: first meaningful param value

### What Gets Discarded

- Full file contents from Read results
- Full tool output (beyond the compact summary line)
- Token cache details (cache_creation, cache_read breakdowns)
- UUIDs, session IDs, request IDs
- `isSidechain`, `parentUuid`, `version`, `cwd`, `gitBranch`
- `info` type messages from Gemini (e.g. "Request cancelled.")
- Thinking signatures (Claude)
- Tool descriptions (Gemini)

## Cost Estimation

Simple dict of per-token pricing (USD per 1M tokens). Starter values:

```python
PRICING = {
    # Claude (input, output) per 1M tokens
    "claude-opus-4-6":          (15.00, 75.00),
    "claude-sonnet-4-6":        (3.00,  15.00),
    "claude-haiku-4-5":         (0.80,   4.00),
    # Gemini (input, output) per 1M tokens
    "gemini-2.5-pro":           (1.25,  10.00),
    "gemini-2.5-flash":         (0.15,   0.60),
    "gemini-3-flash-preview":   (0.15,   0.60),
}
```

Model names are matched by prefix (e.g. `"claude-opus-4-6-20250618"` matches `"claude-opus-4-6"`). Unknown models show `$?` instead of a cost.

## Architecture

Single file `transcript.py` with three sections:

1. **Claude parser**: reads JSONL, yields intermediate message dicts
2. **Gemini parser**: reads JSON, yields intermediate message dicts
3. **Markdown renderer**: takes message dicts, produces output

Intermediate message format (internal, not persisted):
```python
{
    "role": "user" | "assistant",
    "timestamp": datetime,
    "model": str | None,
    "tokens_in": int | None,
    "tokens_out": int | None,
    "thinking": [str],        # list of thinking text blocks
    "text": [str],            # list of text blocks
    "tool_calls": [{
        "name": str,
        "summary": str,       # e.g. "/src/app.py"
        "result": str,        # e.g. "84 lines"
        "passed": bool,
    }],
}
```

## Edge Cases

- Empty input (zero messages): output summary with all zeros, no message sections
- Malformed JSONL lines or missing fields: skip with warning to stderr
- User message text is passed through verbatim (no markdown escaping)
- Timestamps are rendered without timezone (strip to local or UTC as-is from input)
- Message counts in summary reflect only user + assistant messages (after filtering `info` types)
- `model` is collected only from assistant/gemini messages for the summary

## Dependencies

- Python 3.10+ (standard library only — `json`, `argparse`, `datetime`, `sys`)
- No external packages
