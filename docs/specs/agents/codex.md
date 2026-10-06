# Codex Format Mapping

This parser supports native Codex CLI and Codex Desktop JSONL session logs.

Codex logs contain both UI/runtime events and model response items. The response item stream is the authoritative source for user, assistant, reasoning, and tool content. Runtime events provide session metadata, turn metadata, token counts, and supplemental tool status. UI mirror events (`event_msg.user_message`, `event_msg.agent_message`) are ignored.

## Native Log Identity

- Parser key: `codex`
- Typical location: `~/.codex/sessions/YYYY/MM/DD/rollout-<timestamp>-<session-id>.jsonl`
- Session index: `~/.codex/session_index.jsonl`
- File shape: JSONL, one JSON object per line
- Detection signal: the first recognizable JSONL line is a Codex entry: `session_meta` with a non-empty `payload.id`, `response_item` with a non-empty `payload.type`, or any `turn_context` / `event_msg` entry whose `payload` is an object. See "Detection Contract" in `docs/specs/common-model.md`.

## Top-Level Session Fields

| Native field | Common field | Notes |
|---|---|---|
| `session_meta.payload.id` | `Transcript.session_id` | Stable Codex session/thread identifier |
| `session_meta.payload.timestamp` | `Transcript.start_time` | Fallback to the first parsed message's timestamp |
| latest of every entry `timestamp`, `session_meta.payload.timestamp`, and `event_msg.task_complete.completed_at` | `Transcript.end_time` | Fallback to the last parsed message's timestamp |
| parser key | `Transcript.source_format = "codex"` | |

`turn_context.payload.model` is the model for following assistant messages, and also replaces the model of an assistant message that is still open. `session_meta.payload.model_provider` is not used.

## Native Entry Types

| Native `type` | Common action | Presented? | Notes |
|---|---|---|---|
| `session_meta` | Populate transcript metadata | no | Session id, cwd, originator, CLI version, git metadata |
| `turn_context` | Track active model | no | Only `payload.model` is read |
| `response_item` | Create messages, reasoning, and tool calls | yes | Primary content stream |
| `event_msg` | Handle selected runtime events | no | Only `token_count`, `patch_apply_end`, and `task_complete` are read |

Unknown entry types, and entries whose `payload` is not an object, are skipped silently for forward compatibility.

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

User, developer, and system messages read `input_text`, `text`, and `output_text` blocks; a plain string `content` is also accepted. If the same native message contains multiple text blocks, block order is preserved in `Message.text`. A message with no text or placeholder produces no `Message`.

Image and file blocks become text placeholders in the same position:

| Native block `type` | Placeholder |
|---|---|
| `input_image` or `image` | `[image: <value>]` using the first present of `source`, `path`, `file_path`; `[image]` when none is present |
| `input_file` or `file` | `[file: <value>]` using `path` or `file_path`; `[file]` when neither is present |

Other image fields such as `image_url` are not shown, so a typical pasted image becomes `[image]`.

`event_msg.user_message` is a UI mirror of the user input and is ignored; the `response_item` message is the only source.

## Assistant Content

Assistant messages are response items with `payload.type == "message"` and `payload.role == "assistant"`.

| Native field | Common field |
|---|---|
| active `turn_context.payload.model` | `Message.model` |
| `payload.phase` | currently not represented; commentary/final text both map to text |
| `payload.content[].text` for `output_text` and `text` blocks, plus image/file placeholders | `Message.text[]` |
| plaintext `reasoning.content` or `reasoning.summary[].text` | `Message.thinking[]` |
| `function_call` / `custom_tool_call` | `Message.tool_calls[]` |

Assistant response items are merged into the current assistant message until the next user, developer, or system message, or an `event_msg.task_complete`. Each text, reasoning, and tool call appends to `Message.content_order` as it appears:

- `("thinking", idx)`
- `("text", idx)`
- `("tool", idx)`

`event_msg.agent_message` is a UI mirror of assistant text and is ignored.

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
5. Use supplemental `event_msg.patch_apply_end` (matched by `call_id`) for `apply_patch` status and change counts. It may arrive before or after the output; when it arrives after, the already-built tool call is re-summarized.

Unresolved tool calls become failed tool calls when their assistant message closes:

```python
ToolCall(result_summary="no result", result_full="", status=Status.FAILED)
```

An output with no pending call (unknown or empty `call_id`, or arriving after its assistant message closed) is still kept: it becomes a tool call named `?` with summary `unmatched output for call <call_id>` and its output summarized as usual.

A `function_call` or `custom_tool_call` without `call_id` cannot be matched; it is skipped with a warning.

## Tool Fields

`ToolCall.name` and `ToolCall.display_name` are both the native tool name (`?` when missing).

| Codex tool | Summary source |
|---|---|
| `exec_command` | parsed `arguments.cmd` (a list is joined with spaces), truncated to 80 chars; `workdir` is not shown |
| `write_stdin` | `{session_id}: {chars}` with `chars` stripped and truncated to 60 chars; just `session_id` when `chars` is empty |
| `apply_patch` | path from the first `*** Add File:`, `*** Update File:`, or `*** Delete File:` line of the patch input; fallback `apply patch` |
| other | first non-empty string among `url`, `query`, `ticker`, `location`, `path`, `file_path`, `selector`, `prompt`; then the first non-empty string found anywhere in the parsed arguments; then the raw input; each truncated to 80 chars; fallback `?` |

## Result Summary

Codex function outputs are often plain display strings, not structured JSON. Non-string outputs are stored as pretty-printed JSON. The result summary and status come from the first matching rule:

| # | Native output or condition | `ToolCall.result_summary` | Status |
|---|---|---|---|
| 1 | `event_msg.patch_apply_end.success == false` for this `call_id` | `FAILED: <first stderr or stdout line>`, or `FAILED` | `FAILED` |
| 2 | `event_msg.patch_apply_end.success == true` | `{n} files changed` when `changes` is a non-empty list or object, else `ok` | `PASSED` |
| 3 | output contains `Process exited with code N` or `Exit code: N`, `N == 0` | `ok` | `PASSED` |
| 4 | same, `N != 0` | `FAILED (exit N)` | `FAILED` |
| 5 | first non-empty output line starts with `cancelled` or `canceled` (case-insensitive) | `cancelled` | `CANCELLED` |
| 6 | first non-empty output line starts with `error:` or `failed` (case-insensitive) | `FAILED: <first line, max 50 chars>` (the line itself if it already starts with `FAILED`) | `FAILED` |
| 7 | whole output is `Success` or `Success.` | `ok` | `PASSED` |
| 8 | empty output | `ok` | `PASSED` |
| 9 | one line of at most 50 chars | the line | `PASSED` |
| 10 | otherwise | `{n} lines` | `PASSED` |

Rules 5 and 6 only look at the first non-empty line, so output that merely mentions `cancelled`, `0 failed`, or `error:` further down is not a cancellation or failure.

After that, the call item's own `status` overrides the status: `cancelled`/`canceled` gives `CANCELLED`, and `failed`/`error` gives `FAILED` with a `FAILED: ` prefix added to the summary if missing.

`ToolCall.result_summary` must always be a string. `ToolCall.result_full` must preserve the complete native output with no truncation.

## Token Mapping

Codex token counts are emitted in `event_msg` entries with `payload.type == "token_count"`.

| Native field | Common field |
|---|---|
| `payload.info.last_token_usage.input_tokens` | `Message.tokens_in` |
| `payload.info.last_token_usage.output_tokens` | `Message.tokens_out` |
| `payload.info.last_token_usage.cached_input_tokens` | `Message.tokens_cached` |
| `payload.info.last_token_usage.reasoning_output_tokens` | `Message.tokens_thinking` |

Each token-count event's `last_token_usage` is added to the open assistant message. If no assistant message is open, it goes to the most recent assistant message; if there is none yet, it is dropped. Multiple events on one message are summed. `payload.info.total_token_usage` is not used.

`token_count` events may carry `"info": null` or a null `last_token_usage` (for example before the first model response). These events have no usage to apply and are ignored.

Cached input tokens are treated as free by the common cost contract.

OpenAI models used by Codex are not in the pricing table, so Codex cost is always unknown (`$?`). Token counts are still shown.

## Status Mapping

| Native condition | Common status |
|---|---|
| successful patch event, zero exit code, or no failure/cancel marker (rules 2, 3, 7-10 above) | `PASSED` |
| failed patch event, non-zero exit code, or first line starting with `error:`/`failed` | `FAILED` |
| first non-empty output line starts with `cancelled`/`canceled` | `CANCELLED` |
| call item `status` is `cancelled` or `canceled` | `CANCELLED` |
| call item `status` is `failed` or `error` | `FAILED` |
| unresolved tool call | `FAILED` |

Codex logs observed so far do not expose a stable cancellation shape for all tools, so `CANCELLED` is only set from the call item's `status` or an output whose first non-empty line starts with `cancelled`/`canceled`.

## Special Native Concepts

### Turns

`event_msg.task_started`, `turn_context`, token-count events, and `event_msg.task_complete` describe one user-driven agent turn. `turn_context` sets the model and `task_complete` closes the open assistant message and extends `end_time`. No visible messages are created for task start/complete events.

### Reasoning

Codex reasoning items may contain plaintext `content`, a plaintext `summary`, and/or `encrypted_content`. Only plaintext reasoning is displayable. Encrypted reasoning should be skipped because it is not readable transcript content.

### Compaction And Summaries

Compaction is not represented: the Codex parser never produces `Message(is_compaction_marker=True)`. Compaction entries (such as top-level `compacted` entries) are skipped like any other unknown entry type, and `turn_context.payload.summary` is not read.

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
| `event_msg.user_message`, `event_msg.agent_message` | UI mirrors of response-item messages |
| other `event_msg` types | Runtime events not mapped |
| `session_meta.payload.model_provider` | Provider metadata, not a model name |
| `turn_context.payload.summary` | Turn metadata |
| compaction entries (for example top-level `compacted`) | Compaction is not represented in the Codex mapping |

Skipped metadata may be revisited if the common model gains a metadata surface.

## Edge Cases

- Malformed JSONL lines: skip with warning including line number.
- Valid JSON lines that are not objects (for example `[1,2]`): skip with warning including line number.
- Null or wrong-typed nested fields (`payload`, `info`, usage counts, `call_id`, `model`): treat as missing; never abort the parse.
- `exec_command` `cmd` may be an argument list: join it with spaces for the summary.
- Missing timestamp: use UTC `datetime.min`.
- `response_item` messages with an unknown `role`: skip with a warning.
- `function_call` / `custom_tool_call` without `call_id`: skip with a warning.
- Outputs with no pending call: kept as a `?` tool call (see "Tool Calls").
- Unknown `response_item` types: skip with a warning.
- Missing `session_meta`: parse response items and set `session_id=None`.
- Missing `turn_context`: assistant model is `None`.
- Missing token-count events: token counts default to 0.
- Multiple token-count events in one turn: sum `last_token_usage` on the current assistant message.
- `function_call.arguments` may be invalid JSON: preserve the raw argument string and summarize from it.
- Tool output may be plain terminal text, not machine-readable JSON.
- Tool outputs must match by `call_id`, not position.
- Custom/freeform tool calls may have no structured arguments.
- Response item and event-message streams may duplicate user/assistant text; only response items are used.
