# TUI Renderer

The TUI renderer provides an interactive view over the common model using Textual and Rich.

It must follow `docs/specs/presentation.md` for meaning and visibility rules.

## Launch

```bash
transcript view <input_file>
```

## Layout

The TUI uses two panels:

- conversation panel on the left
- detail panel on the right

The conversation panel shows summary metadata followed by focusable content rows. The detail panel shows expanded tool output, full thinking, or help.

Every focusable conversation row has a fixed two-character gutter so text does not shift when focus changes.

## Navigation

| Key | Action |
|---|---|
| Up/Down, `j`/`k` | Move between conversation blocks |
| Enter | Expand focused thinking or tool call |
| `t` | Toggle all thinking blocks |
| `h` | Cycle visibility mode |
| `/` | Open search |
| `n` / `N` | Next or previous search match |
| Tab | Switch between conversation and detail panels |
| Esc | Clear detail or close search |
| `?` | Show help |
| `q` | Quit |

## Conversation Rows

Rows include:

- message headers
- message text
- thinking blocks
- tool calls
- local commands

Compaction markers are displayed as separators and are not focusable.

## Thinking

Thinking blocks are collapsed by default:

```text
Thinking (3 lines) [>]
```

Pressing Enter expands the block inline. Pressing Enter again while expanded sends the full thinking text to the detail panel.

## Tool Calls

Tool calls render in compact form in the conversation panel:

```text
Read /src/auth.py -> 84 lines [>]
Bash pytest tests/ -> FAILED (exit 1) [>]
```

Pressing Enter opens full output in the detail panel.

File-like outputs may use syntax highlighting based on extension. Markdown outputs may render as formatted Markdown.

## Status Markers

| Status | TUI signal |
|---|---|
| `PASSED` | dim neutral marker |
| `FAILED` | red failure marker/text |
| `CANCELLED` | yellow cancelled marker/text |

Focused rows show a focus indicator in the gutter.

## Visibility Modes

The `h` key cycles:

1. all content
2. messages only
3. user messages plus tool calls

The user-plus-tools mode must preserve tool chronology by using `content_order` when available.

## Search

Search matches against row `searchable_text`, including message text, thinking text, tool names, summaries, and result summaries.

If no match is found, keep search context visible enough for the user to understand that there were zero results.
