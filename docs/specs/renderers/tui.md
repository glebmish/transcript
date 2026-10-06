# TUI Renderer

The TUI renderer provides an interactive view over the common model using Textual and Rich.

It must follow `docs/specs/presentation.md` for meaning and visibility rules.

## Launch

```bash
transcript view <input_file>
```

## Untrusted Text

The app sanitizes the whole `Transcript` once (`sanitize_transcript`) before building any widget, so no row or detail view can emit raw control characters from the log (see "Control Characters" in `docs/specs/presentation.md`).

Log-derived strings are never interpreted as Textual markup. They are passed as plain text (`markup=False`), built with `Content.assemble` (including the summary header with model names and slash-command headers), or inserted as `Content.from_markup` template variables. A model named `bad[/nope]` displays literally.

## Layout

The header bar shows the app title `transcript`. Below it, the TUI uses two panels:

- conversation panel on the left
- detail panel on the right

The conversation panel shows summary metadata followed by focusable content rows. The detail panel shows expanded tool output, full thinking, or help.

The summary at the top of the conversation panel (`transcript view tests/fixtures/gemini_minimal.json`):

```text
  # Transcript
  Duration: 5m 0s · gemini-2.5-flash
  Messages: 4 · Tools: 2 (1 cancelled) · $0.0024
```

`Tools: N` is followed by `(F x, C cancelled)`, listing only the non-zero parts, and omitted entirely when nothing failed or was cancelled. Cost is `$?` when unknown and gets ` (partial)` when partial.

The active panel has a dodgerblue border; the inactive one is dimgray.

Every focusable conversation row has a fixed two-character gutter so text does not shift when focus changes.

## Navigation

| Key | Action |
|---|---|
| Up/Down, `j`/`k` | Move between conversation blocks; scroll the detail panel when it is active |
| Enter | Expand focused thinking or tool call |
| `t` | Toggle all thinking blocks |
| `h` | Cycle visibility mode |
| `/` | Open search |
| `n` / `N` | Next or previous search match |
| Tab | Switch between conversation and detail panels |
| Esc | Close search if open, otherwise clear the detail panel |
| `?` | Show help in the detail panel |
| `q`, `ctrl+c` | Quit |

## Conversation Rows

Rows include:

- message headers, such as `## User · 10:00:00` or `## Assistant · 10:00:05 · ↑10,000 ↓500` (tokens shown when non-zero; no per-message cost)
- message text
- thinking blocks
- tool calls
- local commands, with a `## User ('/model' command) · HH:MM:SS` or `## User (command output) · HH:MM:SS` header followed by the raw text

Compaction markers are displayed as separators and are not focusable.

## Thinking

Thinking blocks are collapsed by default:

```text
│ Thinking (3 lines)  [>]
```

A one-line block reads `Thinking (1 line)  [>]`.

Pressing Enter expands the block inline. Pressing Enter again while expanded sends the full thinking text to the detail panel.

## Tool Calls

Tool calls render in compact form in the conversation panel, as gutter marker, bold display name, summary, then a dim `→ result_summary  [>]` (`transcript view tests/fixtures/claude_minimal.jsonl`):

```text
│ Read /src/auth.py → 84 lines  [>]
✘ Bash Run tests → FAILED (exit 1)  [>]
```

Pressing Enter opens full output in the detail panel.

File-like outputs may use syntax highlighting based on extension. Markdown outputs may render as formatted Markdown.

## Status Markers

| Status | TUI signal |
|---|---|
| `PASSED` | grey `│` gutter marker |
| `FAILED` | red `✘` gutter marker and red row text |
| `CANCELLED` | yellow `~` gutter marker and yellow row text |

Focused rows show `▶` in the gutter (followed by the status marker for failed or cancelled tool calls) and a dark background.

## Visibility Modes

The `h` key cycles:

1. all content
2. messages only
3. user messages plus tool calls

The user-plus-tools mode must preserve tool chronology by using `content_order` when available.

## Search

`/` opens a search bar at the bottom. Enter runs a case-insensitive substring search over each focusable row's `searchable_text`:

| Row | Searchable text |
|---|---|
| message header | the visible header text, without markup tags |
| message text, local command text | the text |
| thinking | the full thinking text, even while collapsed |
| tool call | `display_name summary result_summary` |

Tool `result_full` is not searchable. The first match is focused and the bar closes; `n` and `N` move to the next and previous match, wrapping around.

If there is no match, the bar stays open and its border title shows `(0 results for '<query>')`. An empty query closes the bar.
