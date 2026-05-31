# Common Presentation

This document defines every supported common log piece and how it should be presented across renderers.

Renderer docs may choose layout, color, focus behavior, and interaction details, but they should not redefine what a piece means.

## Session Metadata

Every transcript begins with summary metadata:

- duration
- models
- counted messages
- tool-call totals
- token totals
- estimated cost

Message counts include real user messages and assistant messages. Compaction markers and `command_name` messages are displayed but not counted as user messages.

Tool totals count passed, failed, and cancelled tool calls.

Cost and token display can be hidden by renderer options, but the default is to show it.

## User Messages

User messages show timestamp and text.

Text should be preserved as parsed. The tool is for full visibility into session internals, so renderers should not sanitize, summarize, or omit user text unless an explicit view option asks for less content.

## Assistant Messages

Assistant messages show timestamp, optional model/cost/token details, and the assistant content pieces in original order.

When `content_order` is populated, renderers must use it to preserve interleaving. When it is empty, renderers fall back to:

1. thinking
2. text
3. tool calls

## Thinking

Thinking represents native reasoning, thought descriptions, or equivalent hidden/planning text exposed by the log.

Default behavior:

- included in transcripts
- controlled by a show/hide option
- visually distinct from final assistant text
- expandable in interactive renderers

Renderers should not rename thinking per agent. Agent docs map native fields into `Message.thinking`; presentation then treats them uniformly.

## Tool Calls

Tool calls are presented as assistant actions. Each call has:

- display name
- summary
- result summary
- status
- optional full output

Compact form should include display name, summary, and result summary.

Expanded form should include full output with no truncation. If a renderer cannot display the full output inline, it must provide an explicit expansion surface.

## Tool Status

Statuses have common meaning:

| Status | Meaning | Standard signal |
|---|---|---|
| `PASSED` | Tool completed successfully | neutral/default |
| `FAILED` | Tool errored, returned non-zero, or had no required result | `FAILED` text or failure marker |
| `CANCELLED` | User or permission flow cancelled the tool | cancelled marker |

Failed tools should stand out in compact and expanded views. Include exit code or error reason when available.

Cancelled tools are first-class results, not parser failures.

## Tool Families

Presentation groups native tools into common families. Agent docs own the native name mapping.

### File Operations

Examples: read, write, edit, read many files, list directory.

Summary should be the relevant path or path list. Compact results should prefer structured counts such as `{n} lines`, `{n} files`, or `ok`.

Expanded detail should show full file contents, written content, or edit information when present.

### Shell Execution

Summary should prefer a human description, then command text. Compact result should be `ok`, `FAILED (exit N)`, or a short error.

Expanded detail should show full stdout/stderr.

### Search

Summary should be the pattern and optional path. Compact result should be `{n} matches` or `{n} files`.

Expanded detail should show matched lines, context, or file list when available.

### Web

Summary should be the URL or query. Compact result should prefer HTTP status, result count, or a short result display.

Expanded detail should show response body or result list when available.

### Agents And Skills

Agent-tool summaries should prefer description, request, objective, question, or prompt prefix.

Skill activation is displayed as an action, but skill internals are not expanded unless the native log exposes them as normal tool output.

Subagent internal conversations are out of scope unless a future parser explicitly models them as nested transcripts.

### Task And Plan Management

Task, todo, and plan tools are low-noise actions. Compact form is usually sufficient. Expanded detail may show todo list or updated fields when present.

### User Interaction

Ask-user tools should summarize the question and compactly show the response. Expanded detail should preserve full Q&A when available.

### MCP Tools

MCP tools follow the same summary priority as other tools: file path, command description, query/pattern, then first meaningful string argument.

Display names should include enough server/function identity to distinguish them.

## Compaction Markers

Compaction markers indicate that prior conversation context was compacted or summarized by the agent runtime.

They are represented as `Message(is_compaction_marker=True)` and displayed as a separator, not as a normal user message.

## Local Commands

Local slash commands are represented as messages with `command_name` set.

They are visible because they affect the session, but are not counted as user messages.

The full raw command text should be preserved in `Message.text`.

## Skipped Native Internals

Native entries may be skipped when they are internal runtime metadata with no stable user-facing transcript meaning. Examples include transient API retry notices, hook progress, prompt queue bookkeeping, permission-mode changes, and deferred attachment metadata.

Agent docs must list skipped native entry types and why they are skipped.

## Unknown Or Malformed Data

Malformed entries that can be skipped should produce a warning with enough location information to debug the log.

Unknown future native entry types may be skipped silently when the agent mapping spec says that is the future-proofing policy.

Unknown tools should still be represented as `ToolCall` whenever their native call/result structure is parseable.
