# Gemini CLI Format Mapping

This parser supports native Gemini CLI JSON session logs.

## Native Log Identity

- Parser key: `gemini`
- Typical location: `~/.gemini/tmp/<project-hash>/chats/session-<timestamp>-<uuid>.json`
- File shape: single JSON object
- Detection signal: top-level object with `sessionId` and `messages`

## Top-Level Structure

```json
{
  "sessionId": "uuid",
  "projectHash": "sha256-hex",
  "startTime": "ISO-8601",
  "lastUpdated": "ISO-8601",
  "kind": "chat",
  "messages": []
}
```

| Native field | Common field |
|---|---|
| `sessionId` | `Transcript.session_id` |
| `startTime` | `Transcript.start_time` |
| `lastUpdated` | `Transcript.end_time` |
| parser key | `Transcript.source_format = "gemini"` |

If `lastUpdated` is missing or invalid, use the last parsed message timestamp when available.

## Native Message Types

| Native `type` | Common action | Presented? |
|---|---|---|
| `user` | Create `Message(role=USER)` | yes |
| `gemini` | Create `Message(role=ASSISTANT)` | yes |
| `info` | Skip | no |

## User Content Mapping

Gemini user `content` is usually an array of objects with `text`, but may be a plain string.

Text values are concatenated, stripped, and mapped to:

```python
Message(role=Role.USER, timestamp=ts, text=[text])
```

## Assistant Content Mapping

Gemini assistant messages have `type == "gemini"`.

| Native field | Common field |
|---|---|
| `model` | `Message.model` |
| `content` string | `Message.text[]` |
| `thoughts[].description` | `Message.thinking[]` |
| `toolCalls[]` | `Message.tool_calls[]` |
| `tokens` | token fields |

Content order is built as thoughts, then text, then tool calls, matching the shape exposed by the native session entry.

## Tool Call Mapping

Each native `toolCalls[]` entry maps directly to one `ToolCall`.

| Native field | Common field |
|---|---|
| `name` | `ToolCall.name` |
| `displayName` | `ToolCall.display_name`, fallback `name` |
| `args` | source for `ToolCall.summary` |
| `resultDisplay` | preferred source for `ToolCall.result_summary`; may be string, list, or dict |
| `result[0].functionResponse.response.output` | `ToolCall.result_full` |
| `result[0].functionResponse.response.error` | error summary and failed/cancelled handling |
| `status` | `ToolCall.status` |
| `id` | not used |
| `timestamp` | not used |
| `description` | not used |
| `renderOutputAsMarkdown` | not used |

## Tool Summary Rules

| Internal name | Typical display name | Summary source |
|---|---|---|
| `read_file` | `ReadFile` | `args.absolute_path` or `args.file_path` |
| `read_many_files` | `ReadManyFiles` | first paths from `args.paths` |
| `write_file` | `WriteFile` | `args.file_path` |
| `replace` | `Edit` | `args.file_path` |
| `list_directory` | `ReadFolder` | `args.dir_path` |
| `run_shell_command` | `Shell` | `args.description`, fallback `args.command[:80]` |
| `grep_search` | `SearchText` | `args.pattern` |
| `search_file_content` | `SearchText` | `args.pattern` |
| `glob` | `FindFiles` | `args.pattern` |
| `google_web_search` | `GoogleSearch` | `args.query` |
| `web_fetch` | `WebFetch` | `args.url` or `args.prompt` |
| `activate_skill` | `Activate Skill` | `args.name` |
| `ask_user` | `Ask User` | first question from `args.questions` |
| `write_todos` | `WriteTodos` | first non-empty string arg |
| `enter_plan_mode` | `Enter Plan Mode` | `args.reason` |
| `exit_plan_mode` | `Exit Plan Mode` | `args.plan_path` |
| `codebase_investigator` | `Codebase Investigator Agent` | `args.objective` |
| `generalist` | `Generalist Agent` | `args.request` |
| `cli_help` | `CLI Help Agent` | `args.question` |
| `mcp_*` | MCP display name | first non-empty string arg |
| other | `displayName` or `name` | first non-empty string arg |

Display names can vary between sessions. Prefer native `displayName` when present.

## Result Summary

Use `resultDisplay` when present. It is not always a string:

- string display: summarize the string directly
- list display: treat as line-oriented display and summarize as `{n} lines`
- dict display: prefer string fields such as `summary`, `result`, `state`, or `terminateReason`; otherwise summarize known structured fields such as `files` or `diffStat`

The normalized `ToolCall.result_summary` must always be a string.

Fallbacks:

1. short single-line `result_full` up to 50 chars: use as-is
2. multi-line `result_full`: `{n} lines`
3. empty output: `ok`

If `result[].functionResponse.response.error` exists, use the error text as summary. Preserve `CANCELLED` when native status is cancelled; otherwise map error to `FAILED`.

## Token Mapping

Gemini reports cumulative `tokens.input`, so parser stores per-message delta.

| Native field | Common field |
|---|---|
| `tokens.input - previous tokens.input` | `tokens_in` |
| `tokens.output` | `tokens_out` |
| `tokens.cached` | `tokens_cached` |
| `tokens.thoughts` | `tokens_thinking` |

The first assistant message uses raw `tokens.input` as its delta.

Gemini also reports `tokens.tool` and `tokens.total` in observed logs. These are currently ignored because the common model does not have separate tool-token or total-token fields; `tokens_in`, `tokens_out`, `tokens_cached`, and `tokens_thinking` remain the supported cost/display fields.

## Status Mapping

| Native status or condition | Common status |
|---|---|
| `status == "success"` | `PASSED` |
| `status == "error"` | `FAILED` |
| `status == "cancelled"` | `CANCELLED` |
| response has `error` and status is not cancelled | `FAILED` |

Cancelled tools usually mean the user rejected or cancelled a permission prompt.

## Skipped Native Data

| Native data | Reason skipped |
|---|---|
| `info` messages | runtime notifications, not conversation content |
| tool `id` | no cross-entry resolution needed |
| tool timestamp | parent message timestamp is sufficient |
| tool description | static tool help text |
| `renderOutputAsMarkdown` | renderer-specific hint not part of common model |

## Edge Cases

- Top-level value that is not a JSON object: parse error.
- `messages[]` entries that are not objects: skip with warning including the entry number.
- Missing or null `thoughts`: default to empty list.
- Missing or null `toolCalls`: default to empty list.
- Missing or null `tokens`, or non-numeric token counts: token counts default to 0.
- Null or wrong-typed `content`, `args`, `functionResponse`, or `response`: treat as missing; never abort the parse.
- Missing `displayName`: fall back to `name`.
- User `content` may be an array or string.
- Empty result array: use `resultDisplay`, otherwise `ok`.
