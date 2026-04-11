# Tool Display Considerations

How each tool type is summarized, displayed, and expanded across CLI and TUI.

## File Operations

| Tool (Claude / Gemini) | Summary | Compact result | Expanded detail |
|---|---|---|---|
| Read / ReadFile | file path (`file_path` for Claude, `absolute_path` for Gemini) | `{n} lines` | Full file contents, syntax highlighted |
| Write / WriteFile | file path | `ok` or `FAILED` | Written content if available in log |
| Edit / replace (Edit) | file path | `ok` or `FAILED` | old_string -> new_string diff view |
| (none) / ReadManyFiles | paths joined | `{n} files` | Each file's contents sequentially |
| (none) / ReadFolder | dir path | `{n} items` | Directory listing |

File content in the TUI detail panel gets syntax highlighting based on extension. Markdown and plan files render as formatted markdown.

## Shell Execution

| Tool (Claude / Gemini) | Summary | Compact result | Expanded detail |
|---|---|---|---|
| Bash / Shell | `description` field, fallback `command[:80]` | `ok` or `FAILED (exit N)` | Full stdout/stderr |

Output rendered as monospace. Failed commands: stderr highlighted in red. Long output scrollable in detail panel.

## Search

| Tool (Claude / Gemini) | Summary | Compact result | Expanded detail |
|---|---|---|---|
| Grep / SearchText | `pattern` + `path` | `{n} matches` | Matched lines with context |
| Glob / FindFiles | `pattern` | `{n} files` | File list |

Expanded search results highlight the matched pattern.

## Web

| Tool (Claude / Gemini) | Summary | Compact result | Expanded detail |
|---|---|---|---|
| WebFetch / web_fetch | URL | `HTTP {code}` | Response body (truncated) |
| WebSearch / GoogleSearch | query | `{n} results` | Result titles and URLs |

## Agent & Skills

| Tool (Claude / Gemini) | Summary | Compact result | Expanded detail |
|---|---|---|---|
| Agent / (none) | `description` or `prompt[:80]` | `ok` | Agent's response text |
| (none) / Generalist Agent | `request` | `ok` | Agent's response text |
| (none) / Codebase Investigator Agent | `objective` | `ok` | Agent's response text |
| (none) / CLI Help Agent | `question` | `ok` | Agent's response text |
| Skill / Activate Skill | skill name | `ok` | Skip — skill content is system internals |

Subagent logs (Claude's `subagents/*.jsonl`) are out of scope. The Agent tool call shows dispatch and result, not the subagent's internal conversation.

## Task & Plan Management

| Tool (Claude / Gemini) | Summary | Compact result | Expanded detail |
|---|---|---|---|
| TaskCreate / (none) | subject | `ok` | Description |
| TaskUpdate / (none) | task ID | status change | Updated fields |
| (none) / WriteTodos | first arg value | `ok` | Todo list content |
| (none) / Enter Plan Mode | `reason` | `ok` | Skip |
| (none) / Exit Plan Mode | `plan_path` | `ok` | Skip |

Low-interest tools. Compact is usually sufficient, no special rendering.

## User Interaction

| Tool (Claude / Gemini) | Summary | Compact result | Expanded detail |
|---|---|---|---|
| AskUserQuestion / Ask User | question text | user's response | Full Q&A |

## MCP Server Tools

| Tool (Claude / Gemini) | Summary | Compact result | Expanded detail |
|---|---|---|---|
| `mcp__*` / `mcp_*` | first string arg value | `ok` or `FAILED` | Full output |

MCP tools follow naming convention `mcp_<server>_<function>`. Display name includes the server name in parentheses for Gemini.

## General Rules

1. **Summary extraction priority**: Use the most human-readable identifier. File path > command description > pattern > first string arg.

2. **Result summary priority**: Use structured metadata when available (`resultDisplay` for Gemini, `toolUseResult` fields for Claude). Fall back to parsing `result_full`.

3. **Failed tools stand out**: Red `x` gutter in TUI, `FAILED` prefix in CLI markdown. Always include exit code or error reason when available.

4. **Cancelled tools** (Gemini only): Yellow `~` gutter in TUI, `CANCELLED` in CLI. These represent user-rejected permission prompts.

5. **Large outputs in TUI**: Detail panel is scrollable. No truncation — the user chose to expand it.

6. **Large outputs in CLI**: With `--expand-tools`, full output is included. No truncation — incomplete outputs are not allowed.

7. **Sensitive content**: Tool outputs may contain file contents, credentials, or secrets from the original session. No sanitization -- the user is viewing their own logs.
