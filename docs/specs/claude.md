# Claude Code Format & Parser

## Input

JSONL file, one JSON object per line. Located at `~/.claude/projects/<project-hash>/<session-id>.jsonl`.

## Entry Types

| Type | Action |
|------|--------|
| `user` with text content | Create `Message(role=USER)` |
| `user` with `tool_result` content block | Attach result to pending `ToolCall` on current assistant message |
| `assistant` | Create or extend `Message(role=ASSISTANT)` |
| `progress` | Skip |
| `attachment` | Skip |
| `permission-mode` | Skip |
| `last-prompt` | Skip |

## Content Block Mapping

Inside `message.content[]` on assistant entries:

| Block `type` | Maps to |
|-------------|---------|
| `text` | `Message.text[]` |
| `thinking` | `Message.thinking[]` — discard `signature` field |
| `tool_use` | Add to pending tool uses, becomes `ToolCall` when result arrives |

## Tool Use Resolution

Tool uses in assistant content are matched **positionally** to subsequent `user` entries that contain `tool_result` content blocks:

1. Assistant entry has `tool_use` blocks in `message.content[]` — queue them in order.
2. Each subsequent `user` entry with a `tool_result` content block pops from the queue.
3. The `toolUseResult` field at root level of the `user` entry provides structured metadata.
4. The `tool_result.content` provides `result_full`.

### Extracting `result_summary`

From `toolUseResult` (structured metadata at root of user entry):

| Field present | Result summary |
|--------------|---------------|
| `file` with `totalLines` | `"{n} lines"` |
| `filenames` with `numFiles` | `"{n} files"` |
| `numMatches` | `"{n} matches"` |
| `url` with `code` | `"HTTP {code}"` |
| `exitCode` != 0 | `"FAILED (exit {n})"` |
| `exitCode` == 0 | `"ok"` |
| None of the above | `"ok"` |

### Extracting `result_full`

From `tool_result.content` in the user entry. This is typically a string containing the full tool output (file contents, command output, search results, etc.).

## Tool Name Mapping

Claude tools use the same name for internal and display (`name` = `display_name`).

| Tool | Summary extracted from `input` |
|------|-------------------------------|
| `Read`, `Write`, `Edit` | `file_path` |
| `Bash` | `description`, fallback `command[:80]` |
| `Grep` | `pattern` + `path` |
| `Glob` | `pattern` |
| `WebFetch`, `WebSearch` | `url` or `query` |
| `Agent` | `description` or `prompt[:80]` |
| `Skill` | `skill` |
| `TaskCreate`, `TaskUpdate` | `subject` or `taskId` |
| Other | First string value from `input`, truncated to 80 chars |

## Token Extraction

From `message.usage`:

| Usage field | Maps to |
|------------|---------|
| `input_tokens` | `tokens_in` |
| `output_tokens` | `tokens_out` |
| `cache_read_input_tokens` | `tokens_cached` |
| (not tracked separately) | `tokens_thinking` = 0 |

## Deduplication

Streaming produces multiple JSONL lines with the same `message.id`. Merge these into a single `Message`:
- Accumulate content blocks across duplicates.
- Count tokens only once per unique `message.id`.
- Take the latest `model` value.

## Status Mapping

| Condition | Status |
|-----------|--------|
| `tool_result.is_error: true` | `FAILED` |
| `toolUseResult.exitCode` != 0 | `FAILED` |
| Otherwise | `PASSED` |

Claude logs do not have `CANCELLED` status.

## Out of Scope

- **Subagent logs**: Files under `subagents/agent-<id>.jsonl` with `isSidechain: true` are not parsed. The `Agent` tool call in the parent log shows the dispatch and response, not the subagent's internal conversation.
- **Attachments**: Hook outputs and skill content loaded via `attachment` entries are skipped.
- **Progress entries**: Hook execution progress is skipped.

## Edge Cases

- Empty or malformed JSONL lines: skip with warning to stderr.
- Missing `timestamp`: use `datetime.min` as fallback.
- Missing `message.usage`: default all token counts to 0.
- `tool_use` with no subsequent `tool_result`: create `ToolCall` with `result_summary="no result"`, `status=FAILED`.
