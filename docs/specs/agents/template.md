# Agent Mapping Template

Use this template before implementing a new parser. The goal is to discover the native format, map it to the common model, and avoid adding renderer-specific behavior to the parser.

## Native Log Identity

- Agent name:
- Parser key:
- Typical location:
- File shape:
- Detection signal:

## Top-Level Session Fields

| Native field | Common field | Notes |
|---|---|---|
| | `Transcript.session_id` | |
| | `Transcript.start_time` | |
| | `Transcript.end_time` | |
| | `Transcript.source_format` | |

## Native Entry Types

| Native type | Common action | Presented? | Notes |
|---|---|---|---|
| | | | |

## User Content

Describe how native user text maps to:

- `Message(role=Role.USER)`
- `Message.text`
- `Message.command_name`, if applicable

## Assistant Content

Describe how native assistant content maps to:

- `Message(role=Role.ASSISTANT)`
- `Message.model`
- `Message.text`
- `Message.thinking`
- `Message.tool_calls`
- `Message.content_order`

## Tool Calls

Describe native tool-call schema, native result schema, and how calls match results.

| Native field | Common field | Notes |
|---|---|---|
| | `ToolCall.name` | |
| | `ToolCall.display_name` | |
| | `ToolCall.summary` | |
| | `ToolCall.result_summary` | |
| | `ToolCall.result_full` | |
| | `ToolCall.status` | |

## Tool Summary Rules

List native tool names and the field used for `ToolCall.summary`.

| Native tool | Display name | Summary source |
|---|---|---|
| | | |

## Tool Status Rules

| Native condition | Common status |
|---|---|
| | `PASSED` |
| | `FAILED` |
| | `CANCELLED` |

## Token Mapping

| Native token field | Common field | Notes |
|---|---|---|
| | `tokens_in` | |
| | `tokens_out` | |
| | `tokens_cached` | |
| | `tokens_thinking` | |

## Special Native Concepts

Document compaction, local commands, permission prompts, subagents, attachments, or equivalent runtime-specific concepts.

## Skipped Native Data

| Native data | Reason skipped |
|---|---|
| | |

## Edge Cases

List known malformed, missing, repeated, streamed, batched, or unresolved native shapes and the parser policy for each.
