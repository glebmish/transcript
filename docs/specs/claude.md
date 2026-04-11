# Claude Code Format & Parser

## Input

JSONL file, one JSON object per line. Located at `~/.claude/projects/<project-hash>/<session-id>.jsonl`.

## Entry Types

| Type | Action |
|------|--------|
| `user` with text content | Create `Message(role=USER)` |
| `user` with `tool_result` content block | Attach result to pending `ToolCall` on current assistant message |
| `assistant` | Create or extend `Message(role=ASSISTANT)` |
| `system` | See system subtypes below |
| `progress` | Skip — hook and agent execution progress |
| `attachment` | Skip — deferred tools, skill listings, companion metadata |
| `permission-mode` | Skip — permission mode changes (`"default"`, `"acceptEdits"`) |
| `last-prompt` | Skip — prompt recovery bookmarks |
| `queue-operation` | Skip — prompt queue enqueue/remove operations |

### System Entry Subtypes

System entries have a `subtype` field. Handling:

| Subtype | Action | Why |
|---------|--------|-----|
| `compact_boundary` | Insert a visual separator in the transcript | Marks where conversation was compacted — indicates context was summarized and prior messages may be incomplete |
| `api_error` | Skip | Transient API errors with retries — not part of the conversation |
| `turn_duration` | Skip | Internal timing metadata (`durationMs`, `messageCount`) |
| `local_command` | Skip | Local slash-command output (e.g. `/plugins reload`) |
| `bridge_status` | Skip | Remote Control activation status |
| Unknown subtypes | Skip with warning to stderr |

## Content Block Mapping

Inside `message.content[]` on assistant entries:

| Block `type` | Maps to |
|-------------|---------|
| `text` | `Message.text[]` |
| `thinking` | `Message.thinking[]` — discard `signature` field |
| `tool_use` | Add to pending tool uses, becomes `ToolCall` when result arrives |

## Tool Use Resolution

Tool uses in assistant content are matched to results **by ID**:

1. Assistant entry has `tool_use` blocks in `message.content[]` — each has an `id` field (e.g. `"toolu_01EXAMPLE"`). Store them in a dict keyed by `id`.
2. Each subsequent `user` entry with a `tool_result` content block has a `tool_use_id` field that references the original `tool_use.id`.
3. Match by `tool_result.tool_use_id` == `tool_use.id`.
4. The `toolUseResult` field at root level of the `user` entry provides structured metadata.
5. The `tool_result.content` provides `result_full`.

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

| Usage field | Meaning | Maps to |
|------------|---------|---------|
| `input_tokens` | Uncached, non-cache-write input (billable portion) | See formula below |
| `cache_creation_input_tokens` | Tokens written to cache this request | See formula below |
| `cache_read_input_tokens` | Tokens read from cache (free) | See formula below |
| `output_tokens` | Output tokens | `tokens_out` |

Token aggregation:
- `tokens_in` = `input_tokens + cache_creation_input_tokens + cache_read_input_tokens` (total context size)
- `tokens_cached` = `cache_creation_input_tokens + cache_read_input_tokens` (everything not charged)
- Billable input = `tokens_in - tokens_cached` = `input_tokens` (the original uncached portion)

`tokens_thinking` is always 0 for Claude — Claude does not report thinking tokens separately in `message.usage`.

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

## Compact Boundary Handling

When a `system` entry with `subtype: "compact_boundary"` is encountered, insert a pseudo-message into the message list:

```python
Message(
    role=Role.USER,  # arbitrary, not displayed
    timestamp=entry_timestamp,
    is_compaction_marker=True,
    text=["Conversation compacted"],
    # all other fields default/empty
)
```

Renderers check `is_compaction_marker` and render a visual separator instead of a normal message.

## Out of Scope

- **Subagent logs**: Files under `subagents/agent-<id>.jsonl` with `isSidechain: true` are not parsed. The `Agent` tool call in the parent log shows the dispatch and response, not the subagent's internal conversation.
- **Attachments**: Deferred tool listings, skill content, and companion metadata loaded via `attachment` entries are skipped.
- **Progress entries**: Hook execution and agent progress tracking are skipped.
- **Queue operations**: Prompt queue enqueue/remove operations are skipped.
- **Permission mode**: Permission mode change entries are skipped.
- **Last prompt**: Prompt recovery bookmarks are skipped.

## Edge Cases

- Empty or malformed JSONL lines: skip with warning to stderr **including the line number**.
- Missing `timestamp`: use `datetime.min` (UTC) as fallback.
- Missing `message.usage`: default all token counts to 0.
- `tool_use` with no matching `tool_result`: create `ToolCall` with `result_summary="no result"`, `result_full=""`, `status=FAILED`.
- Unknown entry `type` values: skip silently (future-proofing).
