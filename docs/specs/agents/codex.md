# Codex Format Mapping

This parser supports native Codex CLI and Codex Desktop JSONL session logs.

Codex logs contain both UI/runtime events and model response items. The response item stream is the authoritative source for user, assistant, reasoning, and tool content. Runtime events provide session metadata, turn metadata, token counts, and supplemental tool status.

## Native Log Identity

- Parser key: `codex`
- Typical location: `~/.codex/sessions/YYYY/MM/DD/rollout-<timestamp>-<session-id>.jsonl`
- Session index: `~/.codex/session_index.jsonl`
- File shape: JSONL, one JSON object per line
- Detection signal: at least one JSONL entry with `type == "session_meta"` and `payload.id`, or at least one entry with `type == "response_item"` and `payload.type`

## Top-Level Session Fields

| Native field | Common field | Notes |
|---|---|---|
| `session_meta.payload.id` | `Transcript.session_id` | Stable Codex session/thread identifier |
| `session_meta.payload.timestamp` | `Transcript.start_time` | Fallback to first valid entry timestamp |
| last valid entry `timestamp` or `event_msg.task_complete.completed_at` | `Transcript.end_time` | Prefer latest chronological timestamp |
| parser key | `Transcript.source_format = "codex"` | |

`turn_context.payload.model` is the preferred model for following assistant messages in that turn. If unavailable, use `session_meta.payload.model_provider` only as provider metadata, not as a model name.

## Native Entry Types

| Native `type` | Common action | Presented? | Notes |
|---|---|---|---|
| `session_meta` | Populate transcript metadata | no | Session id, cwd, originator, CLI version, git metadata |
| `turn_context` | Track active turn model and environment | sometimes | Model is used for assistant messages; summary/compaction may become a marker when exposed |
| `response_item` | Create messages, reasoning, and tool calls | yes | Primary content stream |
| `event_msg` | Handle selected runtime events | sometimes | Token counts, user/agent UI messages, task status |

Unknown entry types are skipped silently for forward compatibility.

## Response Item Types

| `payload.type` | Common action | Presented? |
|---|---|---|
| `message` with `role == "user"` | Create `Message(role=USER)` | yes |
| `message` with `role == "assistant"` | Create or extend `Message(role=ASSISTANT)` | yes |
| `message` with `role == "developer"` or `role == "system"` | Create `Message(role=DEVELOPER)` or `Message(role=SYSTEM)` | yes |
| `reasoning` | Add to current assistant `Message.thinking` when plaintext exists | yes |
| `function_call` | Create pending tool call | yes, through `ToolCall` |
| `function_call_output` | Attach result to pending tool call by `call_id` | yes, through `ToolCall` |
| `custom_tool_call` | Create pending custom/freeform tool call | yes, through `ToolCall` |
| `custom_tool_call_output` | Attach result to pending custom tool call by `call_id` | yes, through `ToolCall` |

Unknown response item types are skipped with a warning.

## User Content

Codex user messages are response items:

```json
{"type": "response_item", "payload": {"type": "message", "role": "user", "content": []}}
```

Content blocks with `type == "input_text"` map to:

```python
Message(role=Role.USER, timestamp=ts, text=[text])
```

If the same native message contains multiple text blocks, preserve block order in `Message.text`. Native image or file blocks that cannot be represented directly should become visible placeholders such as `[image: local path]`, `[image: base64]`, or `[file: path]`.

`event_msg.user_message` is a UI event mirror of the user input. It should be used only when the corresponding `response_item` message is absent.

## Assistant Content

Assistant messages are response items with `payload.type == "message"` and `payload.role == "assistant"`.

| Native field | Common field |
|---|---|
| active `turn_context.payload.model` | `Message.model` |
| `payload.phase` | currently not represented; commentary/final text both map to text |
| `payload.content[].text` for `output_text` blocks | `Message.text[]` |
| plaintext `reasoning.content` or `reasoning.summary[].text` | `Message.thinking[]` |
| `function_call` / `custom_tool_call` | `Message.tool_calls[]` |

Assistant response items in one turn should be merged into the current assistant message until the next user message or task boundary. Each text, reasoning, and tool call appends to `Message.content_order` as it appears:

- `("thinking", idx)`
- `("text", idx)`
- `("tool", idx)`

`event_msg.agent_message` is a UI event mirror of assistant text. It should be used only when the corresponding `response_item` assistant message is absent.

## Developer And System Instructions

Codex may log developer or system messages as `response_item` messages before the user turn. These are visible session internals and map to `Role.DEVELOPER` or `Role.SYSTEM`.

Instruction messages are displayed, but they are not counted as user or assistant messages.

## Tool Calls

Codex tool calls are emitted as response items and matched by `call_id`.

| Native response item | Native id field | Native input field | Native output item |
|---|---|---|---|
| `function_call` | `call_id` | JSON string in `arguments` | `function_call_output` |
| `custom_tool_call` | `call_id` | freeform string in `input` | `custom_tool_call_output` |

Resolution:

1. Store each `function_call` or `custom_tool_call` as pending by `call_id`.
2. Parse `function_call.arguments` as JSON when possible; preserve the raw string on parse failure.
3. Match output where output `call_id == call.call_id`.
4. Use output string as `ToolCall.result_full`.
5. Use supplemental `event_msg.patch_apply_end` for `apply_patch` status and change counts when present.

Unresolved tool calls become failed tool calls:

```python
ToolCall(result_summary="no result", result_full="", status=Status.FAILED)
```

## Tool Fields

Use the native tool name for `ToolCall.name`. `ToolCall.display_name` should be the native name unless a stable prettier name exists.

| Codex tool | Summary source |
|---|---|
| `exec_command` | parsed `arguments.cmd`; append `workdir` only when needed to disambiguate |
| `write_stdin` | `session_id`, plus first meaningful `chars` text when non-empty |
| `apply_patch` | first changed file from patch input; fallback `apply patch` |
| browser tools | URL, selector, or action summary from arguments |
| image tools | prompt prefix or target file path |
| web tools | query, URL, or ticker/location from arguments |
| MCP tools | first meaningful string argument, with server/function identity in display name when available |
| other | first non-empty string value from parsed arguments or raw input, truncated to 80 chars |

## Result Summary

Codex function outputs are often plain display strings, not structured JSON. Result summary should be derived in this order:

| Native output or condition | `ToolCall.result_summary` |
|---|---|
| `event_msg.patch_apply_end.success == true` | `ok` or `{n} files changed` when changes are available |
| `event_msg.patch_apply_end.success == false` | `FAILED` plus first stderr/stdout line when present |
| output contains `Process exited with code N` and `N != 0` | `FAILED (exit N)` |
| output contains `Process exited with code 0` | `ok` |
| output contains `Exit code: N` and `N != 0` | `FAILED (exit N)` |
| output contains `Exit code: 0` | `ok` |
| output contains `Wall time` and no failure marker | `ok` |
| short single-line output | output text |
| multi-line output | `{n} lines` |
| empty output | `ok` |

`ToolCall.result_summary` must always be a string. `ToolCall.result_full` must preserve the complete native output with no truncation.

## Token Mapping

Codex token counts are emitted in `event_msg` entries with `payload.type == "token_count"`.

| Native field | Common field |
|---|---|
| `payload.info.last_token_usage.input_tokens` | `Message.tokens_in` |
| `payload.info.last_token_usage.output_tokens` | `Message.tokens_out` |
| `payload.info.last_token_usage.cached_input_tokens` | `Message.tokens_cached` |
| `payload.info.last_token_usage.reasoning_output_tokens` | `Message.tokens_thinking` |

Attach each token-count event to the current assistant message for the turn. If a turn emits multiple token-count events, sum their `last_token_usage` values on that assistant message. `payload.info.total_token_usage` is cumulative and should be used for transcript totals only when per-message attachment is impossible.

`token_count` events may carry `"info": null` or a null `last_token_usage` (for example before the first model response). These events have no usage to apply and are ignored.

Cached input tokens are treated as free by the common cost contract.

## Status Mapping

| Native condition | Common status |
|---|---|
| output has zero exit code or successful completion marker | `PASSED` |
| output has non-zero exit code, failed patch event, or error marker | `FAILED` |
| permission/user cancellation is explicitly logged | `CANCELLED` |
| unresolved tool call | `FAILED` |

Codex logs observed so far do not expose a stable cancellation shape for all tools. Preserve `CANCELLED` only when a native status or event clearly indicates cancellation.

## Special Native Concepts

### Turns

`event_msg.task_started`, `turn_context`, token-count events, and `event_msg.task_complete` describe one user-driven agent turn. Use turns to attach model and token metadata, but do not create visible messages solely for task start/complete events.

### Reasoning

Codex reasoning items may contain plaintext `content`, a plaintext `summary`, and/or `encrypted_content`. Only plaintext reasoning is displayable. Encrypted reasoning should be skipped because it is not readable transcript content.

### Compaction And Summaries

`turn_context.payload.summary` may contain carried-forward context. If Codex exposes an explicit compaction boundary or summarized-prior-conversation marker, represent it as `Message(is_compaction_marker=True)`. A normal turn summary without a boundary is metadata and should not become transcript text.

### Session Index

`~/.codex/session_index.jsonl` maps session ids to thread names and update times. It is useful for discovery but is not required to parse a single session log.

## Skipped Native Data

| Native data | Reason skipped |
|---|---|
| `session_meta.payload.base_instructions` | May duplicate developer response items and can be very large |
| `session_meta.payload.dynamic_tools` | Tool schema metadata, not a performed action |
| `session_meta.payload.git` | Repository metadata, not conversation content |
| `turn_context` sandbox and approval fields | Runtime environment metadata |
| `event_msg.task_started` | Turn lifecycle metadata |
| `event_msg.task_complete.duration_ms` | Runtime timing metadata |
| `event_msg.token_count.rate_limits` | Rate-limit metadata |
| `reasoning.encrypted_content` | Not readable transcript content |

Skipped metadata may be revisited if the common model gains a metadata surface.

## Edge Cases

- Malformed JSONL lines: skip with warning including line number.
- Valid JSON lines that are not objects (for example `[1,2]`): skip with warning including line number.
- Null or wrong-typed nested fields (`payload`, `info`, usage counts, `call_id`, `model`): treat as missing; never abort the parse.
- `exec_command` `cmd` may be an argument list: join it with spaces for the summary.
- Missing timestamp: use UTC `datetime.min`.
- Missing `session_meta`: parse response items and set `session_id=None`.
- Missing `turn_context`: assistant model is `None`.
- Missing token-count events: token counts default to 0.
- Multiple token-count events in one turn: sum `last_token_usage` on the current assistant message.
- `function_call.arguments` may be invalid JSON: preserve the raw argument string and summarize from it.
- Tool output may be plain terminal text, not machine-readable JSON.
- Tool outputs must match by `call_id`, not position.
- Custom/freeform tool calls may have no structured arguments.
- Response item and event-message streams may duplicate user/assistant text; prefer response items and use events only as fallback.
