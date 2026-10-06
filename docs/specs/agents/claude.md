# Claude Code Format Mapping

This parser supports native Claude Code JSONL logs.

## Native Log Identity

- Parser key: `claude`
- Typical location: `~/.claude/projects/<project-hash>/<session-id>.jsonl`
- File shape: JSONL, one JSON object per line
- Detection signal: the first recognizable JSONL line has a Claude Code `type` (`user`, `assistant`, `system`, `progress`, `attachment`). See "Detection Contract" in `docs/specs/common-model.md`.

## Session Identity

`Transcript.session_id` is the `sessionId` of the first entry that has one. Later entries are not checked for a different value. If no entry has `sessionId`, it is `None`.

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
| `local_command` | Create message with `command_name`; `"(command output)"` when the content has no `<command-name>` | Shows slash-command activity |
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

Slash-command detection only applies when the stripped text starts with one of `<command-name>`, `<command-message>`, `<local-command-caveat>`, or `<local-command-stdout>`. A normal prompt that merely mentions one of these tags mid-text is a regular user message with its full text.

If the text starts with `<command-name>` or `<command-message>`, the value of the first `<command-name>...</command-name>` becomes `Message.command_name`.

If the text starts with `<local-command-caveat>` or `<local-command-stdout>` (or a `<command-message>` without a name), `command_name` is set to `"(command output)"`.

Messages with `command_name` are displayed but are not counted as user messages.

For `system` entries with `subtype: "local_command"`, preserve the raw `content` string in `Message.text` and store the extracted command in `Message.command_name`. When the content has no `<command-name>` (for example only `<local-command-stdout>...`), `command_name` is `"(command output)"`, as for user text. Entries with empty or whitespace-only content are skipped.

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

Assistant entries without `message.id` are merged into the current assistant message (or start one if none is open). Their `usage` is ignored, and their `model` is only used when they start a new message.

Claude Code writes `model: "<synthetic>"` on placeholder assistant entries it generates locally (interrupts, API errors). These are kept as normal assistant messages with `Message.model = "<synthetic>"`, but they are not added to `Transcript.models` and are skipped for cost estimation, since no API call was made.

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

They are recorded on the assistant message that emitted them whenever that message is closed: by a new `message.id`, a user text entry, a `compact_boundary`, a kept `local_command`, or end of file. A `tool_result` that arrives after its assistant message was closed is dropped; the call stays `no result`.

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
| string result | `FAILED: <first line, max 50 chars>` |
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
- Valid JSON lines that are not objects (for example `[1,2]`): skip with warning including line number.
- Null or wrong-typed nested fields (`message`, `usage`, `content`, block `text`/`thinking`, tool `input`, numeric usage counts): treat as missing or 0; never abort the parse.
- Non-string `tool_result.content` other than a block list is preserved as pretty-printed JSON.
- Missing timestamp: use UTC `datetime.min`.
- Missing usage: token counts default to 0.
- Multiple `tool_result` blocks in one user entry: process all blocks.
- Tool results must match by ID.
- Known metadata system subtypes are skipped silently.
- Unknown system subtypes: warn and skip.
