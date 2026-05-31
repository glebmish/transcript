# Claude Code Format Mapping

This parser supports native Claude Code JSONL logs.

## Native Log Identity

- Parser key: `claude`
- Typical location: `~/.claude/projects/<project-hash>/<session-id>.jsonl`
- File shape: JSONL, one JSON object per line
- Detection signal: at least one valid JSONL entry with a known Claude Code `type`

## Native Entry Types

| Native `type` | Common action | Presented? |
|---|---|---|
| `user` with text content | Create `Message(role=USER)` | yes |
| `user` with `tool_result` blocks | Attach results to pending assistant tool calls | yes, through `ToolCall` |
| `assistant` | Create or extend `Message(role=ASSISTANT)` | yes |
| `system` | Handle selected subtypes | sometimes |
| `progress` | Skip | no |
| `attachment` | Skip | no |
| `permission-mode` | Skip | no |
| `last-prompt` | Skip | no |
| `queue-operation` | Skip | no |
| `mode` | Skip | no |
| `file-history-snapshot` | Skip | no |
| `ai-title` | Skip | no |
| `agent-setting` | Skip | no |
| `bridge-session` | Skip | no |

Unknown entry types are skipped silently for forward compatibility.

## System Subtypes

| Subtype | Common action | Reason |
|---|---|---|
| `compact_boundary` | Insert `Message(is_compaction_marker=True)` | Shows context compaction point |
| `local_command` | Create message with `command_name` when command name exists | Shows slash-command activity |
| `api_error` | Skip | Transient retry metadata |
| `turn_duration` | Skip | Runtime timing metadata |
| `bridge_status` | Skip | Remote-control status metadata |
| `stop_hook_summary` | Skip | Hook summary metadata |
| `away_summary` | Skip | Away-mode summary metadata |
| `informational` | Skip | Runtime informational metadata |
| `scheduled_task_fire` | Skip | Scheduled-task runtime metadata |
| unknown | Skip with warning | Native shape is not yet mapped |

## User Content Mapping

Text content becomes:

```python
Message(role=Role.USER, timestamp=ts, text=[text])
```

If text contains `<command-name>...</command-name>`, the extracted value becomes `Message.command_name`.

If text starts with `<local-command-caveat>` or `<local-command-stdout>`, `command_name` is set to `"(command output)"`.

Messages with `command_name` are displayed but are not counted as user messages.

For `system` entries with `subtype: "local_command"`, preserve the raw `content` string in `Message.text` and store the extracted command in `Message.command_name`.

User `image` content blocks are represented as text placeholders such as `[image: base64]`. The current common model does not carry binary media or image source payloads.

## Assistant Content Mapping

Claude assistant entries use `message.content[]`.

| Native content block | Common field |
|---|---|
| `text` | `Message.text[]` |
| `thinking` | `Message.thinking[]`; ignore `signature` |
| `tool_use` | pending tool use, later converted to `ToolCall` |

Assistant entries with the same `message.id` are streaming fragments of the same assistant message. The parser merges their content and uses max token counts for that message ID.

When a new `message.id` appears, the previous assistant message is finalized and a new `Message` is started.

## Tool Use Resolution

Claude tool uses are matched to results by ID.

1. `assistant.message.content[]` contains `tool_use` blocks with `id`.
2. Later `user.message.content[]` contains one or more `tool_result` blocks with `tool_use_id`.
3. Match where `tool_result.tool_use_id == tool_use.id`.
4. Use root-level `toolUseResult` for structured result metadata when present.
5. Use `tool_result.content` for `ToolCall.result_full`.

Batched `tool_result` blocks must all be processed. Matching is ID-based, not positional.

Unresolved tool uses become failed tool calls:

```python
ToolCall(result_summary="no result", result_full="", status=Status.FAILED)
```

## Tool Fields

Claude uses the same value for `ToolCall.name` and `ToolCall.display_name`.

| Claude tool | Summary source |
|---|---|
| `Read`, `Write`, `Edit` | `input.file_path` |
| `Bash` | `input.description`, fallback `input.command[:80]` |
| `Grep` | `input.pattern` plus optional `input.path` |
| `Glob` | `input.pattern` |
| `WebFetch`, `WebSearch` | `input.url` or `input.query` |
| `Agent` | `input.description` or `input.prompt[:80]` |
| `Skill` | `input.skill` |
| `TaskCreate`, `TaskUpdate` | `input.subject` or `input.taskId` |
| `AskUserQuestion` | first item from `input.questions` |
| `StructuredOutput` | `input.recap_short`, fallback `input.goal` or `input.prose[:80]` |
| `ToolSearch` | `input.query` |
| `Monitor` | `input.description`, fallback `input.command[:80]` |
| `Workflow` | `input.scriptPath`, fallback `input.script[:80]` |
| `TaskStop` | `input.task_id` |
| `TaskList` | literal `tasks` |
| other | first non-empty string value from `input`, truncated to 80 chars |

## Result Summary

From root-level `toolUseResult`:

| Native field or condition | `ToolCall.result_summary` |
|---|---|
| `file.totalLines` | `{n} lines` |
| `filenames` with `numFiles` | `{n} files` |
| `numMatches` | `{n} matches` |
| `url` with `code` | `HTTP {code}` |
| `exitCode != 0` | `FAILED (exit N)` |
| `exitCode == 0` | `ok` |
| string result | `FAILED: <first line>` |
| missing/unknown | `ok` |

If `tool_result.is_error` is true, status is `FAILED` and the result summary must be failure-coded.

## Token Mapping

Claude usage fields are per assistant message.

| Native field | Common field |
|---|---|
| `input_tokens + cache_creation_input_tokens + cache_read_input_tokens` | `tokens_in` |
| `output_tokens` | `tokens_out` |
| `cache_creation_input_tokens + cache_read_input_tokens` | `tokens_cached` |
| none | `tokens_thinking = 0` |

Claude `input_tokens` is the uncached, billable input portion. Total context is the sum of input, cache creation, and cache read tokens.

## Status Mapping

| Native condition | Common status |
|---|---|
| `tool_result.is_error == true` | `FAILED` |
| `toolUseResult.exitCode != 0` | `FAILED` |
| unresolved tool use | `FAILED` |
| otherwise | `PASSED` |

Claude Code logs do not currently map any native condition to `CANCELLED`.

## Content Ordering

Each assistant content block appends to `Message.content_order`:

- `("thinking", idx)`
- `("text", idx)`
- `("tool", idx)`

Tool-use blocks reserve a placeholder until the matching result arrives. Renderers use `content_order` to preserve native interleaving.

## Skipped Native Data

| Native data | Reason skipped |
|---|---|
| `progress` entries | hook and runtime progress |
| `attachment` entries | deferred tool, skill, and metadata payloads |
| `permission-mode` entries | mode bookkeeping |
| `last-prompt` entries | prompt recovery bookmarks |
| `queue-operation` entries | queue bookkeeping |
| `mode` entries | mode bookkeeping |
| `file-history-snapshot` entries | file history metadata |
| `ai-title` entries | generated title metadata |
| `agent-setting` entries | agent configuration metadata |
| `bridge-session` entries | remote bridge metadata |
| subagent JSONL files | separate conversations, not yet modeled as nested transcripts |

## Edge Cases

- Malformed JSONL lines: skip with warning including line number.
- Missing timestamp: use UTC `datetime.min`.
- Missing usage: token counts default to 0.
- Multiple `tool_result` blocks in one user entry: process all blocks.
- Tool results must match by ID.
- Known metadata system subtypes are skipped silently.
- Unknown system subtypes: warn and skip.
