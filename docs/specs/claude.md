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
| `local_command` | Parse command name; create `Message` with `command_name` set | Local slash-commands (e.g. `/clear`, `/model`) — see below |
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

## Local Command Handling

Local slash commands (e.g. `/clear`, `/model`) appear in logs in two places:

1. **System entries** with `subtype: "local_command"` — `content` may contain `<command-name>/foo</command-name>` XML, or just `<local-command-stdout>...</local-command-stdout>`.
2. **User entries** — the same XML tags appear in the user message text content. `<local-command-caveat>` precedes the command, `<command-name>` carries the command itself, and `<local-command-stdout>` carries output.

Both sources produce `Message` objects with `command_name` set:

- If the text contains a `<command-name>` tag: `command_name` is the extracted name (e.g. `"/clear"`).
- If the text starts with `<local-command-caveat>` or `<local-command-stdout>`: `command_name` is `"(command output)"`.
- The full XML text is preserved in `Message.text` — the transcript tool's primary goal is full visibility into agent session internals.

```python
Message(
    role=Role.USER,
    timestamp=entry_timestamp,
    command_name="/clear",    # or "(command output)" for caveat/stdout entries
    text=["<command-name>/clear</command-name>..."],  # raw text preserved
)
```

Messages with `command_name` set are not counted in the user message total.

## Content Ordering

Within an assistant turn, content blocks (thinking, text, tool calls) are interleaved across multiple JSONL entries. A single turn flows:

```
assistant entry: [thinking, text, tool_use]
user entry: tool_result
assistant entry: [text, tool_use]
user entry: tool_result
assistant entry: [text]
```

All of this merges into one `Message`. The `content_order` field tracks the original sequence:

```python
content_order: list[tuple[str, int]]
# e.g. [("thinking", 0), ("text", 0), ("tool", 0), ("text", 1), ("tool", 1), ("text", 2)]
```

Each tuple is `(kind, index)` where `kind` is `"thinking"`, `"text"`, or `"tool"`, and `index` points into the corresponding list (`thinking[0]`, `text[0]`, `tool_calls[0]`, etc.).

Tool use blocks reserve a placeholder `("tool", -1)` in `content_order` when the `tool_use` block is seen. The placeholder is filled with the real index when the matching `tool_result` arrives. Unresolved placeholders are removed when the message is finalized.

Renderers should iterate `content_order` when non-empty to preserve the interleaved sequence. When empty (e.g. older data), fall back to the legacy order: thinking → text → tools.

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
