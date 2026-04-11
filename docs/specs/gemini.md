# Gemini CLI Format & Parser

## Input

JSON file with top-level object. Located at `~/.gemini/tmp/<project-hash>/chats/session-<timestamp>-<uuid>.json`.

### Top-Level Structure

```json
{
  "sessionId": "uuid",
  "projectHash": "sha256-hex",
  "startTime": "ISO-8601",
  "lastUpdated": "ISO-8601",
  "messages": [...]
}
```

## Message Type Mapping

| `type` | Action |
|--------|--------|
| `user` | Create `Message(role=USER)` |
| `gemini` | Create `Message(role=ASSISTANT)` |
| `info` | Skip |

## User Messages

`content` is an array of `{ text: "..." }` objects. Concatenate text values, strip whitespace.

Note: `content` is sometimes a plain string — handle both forms.

## Gemini Messages

| Field | Maps to |
|-------|---------|
| `content` (string) | `Message.text[]` |
| `thoughts[].description` | `Message.thinking[]` |
| `toolCalls[]` | `Message.tool_calls[]` — see below |
| `model` | `Message.model` |

## Token Handling

From `tokens` object on gemini messages:

| Token field | Maps to |
|-------------|---------|
| `input` | `tokens_in` — see delta calculation below |
| `output` | `tokens_out` |
| `cached` | `tokens_cached` |
| `thoughts` | `tokens_thinking` |

### Input token delta

Gemini reports **cumulative** `tokens.input` — it grows with each message as the context window grows. The parser computes per-message delta:

```
message.tokens_in = current.tokens.input - previous.tokens.input
```

First message uses the raw value. This gives meaningful per-message input token counts for cost estimation.

## Tool Call Mapping

Each entry in `toolCalls[]` has 10 fields. Mapping:

| Field | Maps to |
|-------|---------|
| `name` | `ToolCall.name` |
| `displayName` | `ToolCall.display_name` |
| `args` | Used to extract `ToolCall.summary` |
| `resultDisplay` | `ToolCall.result_summary` |
| `result[0].functionResponse.response.output` | `ToolCall.result_full` |
| `status` | `ToolCall.status` |
| `id` | Not used (internal tracking) |
| `timestamp` | Not used (message timestamp is sufficient) |
| `description` | Not used (tool description text) |
| `renderOutputAsMarkdown` | Not used |

### Tool Name Mapping

Gemini has distinct internal vs display names. Mapping verified against real logs:

| Internal (`name`) | Display (`displayName`) | Summary from `args` |
|---|---|---|
| `read_file` | `ReadFile` | `absolute_path` |
| `read_many_files` | `ReadManyFiles` | `paths` (joined) |
| `write_file` | `WriteFile` | `file_path` |
| `replace` | `Edit` | `file_path` |
| `list_directory` | `ReadFolder` | `dir_path` |
| `run_shell_command` | `Shell` | `description`, fallback `command[:80]` |
| `grep_search` | `SearchText` | `pattern` |
| `search_file_content` | `SearchText` | `pattern` |
| `glob` | `FindFiles` | `pattern` |
| `google_web_search` | `GoogleSearch` | `query` |
| `web_fetch` | `WebFetch` | `url` |
| `activate_skill` | `Activate Skill` | `name` |
| `ask_user` | `Ask User` | `questions` |
| `write_todos` | `WriteTodos` | first string value from `args` |
| `enter_plan_mode` | `Enter Plan Mode` | `reason` |
| `exit_plan_mode` | `Exit Plan Mode` | `plan_path` |
| `codebase_investigator` | `Codebase Investigator Agent` | `objective` |
| `generalist` | `Generalist Agent` | `request` |
| `cli_help` | `CLI Help Agent` | `question` |
| `mcp_*` | MCP server display name | first string value from `args` |
| Other | `displayName` or `name` | First string value from `args` |

Note: Some tools have inconsistent `displayName` across sessions (e.g. `run_shell_command` sometimes shows as `"Shell"`, sometimes as `"run_shell_command"`). Always prefer `displayName` when present, fall back to `name`.

### Result Summary Fallback

If `resultDisplay` is missing, derive from `result_full`:

1. Short single-line output (<=50 chars): use as-is.
2. Multi-line output: `"{n} lines"`.
3. Empty: `"ok"`.

### Error Detection

If `result[].functionResponse.response.error` exists, override status to `FAILED` and use the error text as `result_summary`.

## Status Mapping

| `status` value | Maps to |
|---------------|---------|
| `"success"` | `PASSED` |
| `"error"` | `FAILED` |
| `"cancelled"` | `CANCELLED` |

## Transcript Metadata

- `session_id`: from top-level `sessionId`
- `start_time`: from top-level `startTime`
- `end_time`: from top-level `lastUpdated`, or last message timestamp

## Edge Cases

- Missing `thoughts`: default to empty list.
- Missing `toolCalls`: default to empty list.
- Missing `tokens`: default all counts to 0.
- Missing `displayName` on a tool call: fall back to `name`.
- `content` as string vs array on user messages: handle both (array of `{text}` objects is the common form, but plain string has been observed).
- Empty `result` array on tool call (e.g. cancelled tools): use `resultDisplay` if available, otherwise `"ok"`.
- `cancelled` tool status: tool was rejected by user at permission prompt. Result may contain an error message like `"[Operation Cancelled] Reason: User cancelled the operation."`.
