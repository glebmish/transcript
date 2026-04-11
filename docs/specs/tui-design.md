# TUI Design

## Launch

```
transcript view <input_file>
```

## Framework

- `textual` for the TUI application and widgets.
- `rich` for markdown rendering and syntax highlighting within panels.

## Layout

Two-panel split: conversation on the left (2/3 width), detail on the right (1/3 width, bordered).

All content in the conversation panel has a fixed 2-character gutter on the left. The gutter shows `▶` on the focused block, status markers on tool calls, or spaces otherwise. This prevents text from shifting horizontally when focus changes.

```
+-- Conversation ------------------------------------+-- Detail ----------------+
|   # Transcript                                     |                          |
|   Duration: 12m · claude-opus-4-6                  |  (empty until            |
|   Messages: 8 · Tools: 12 (1 x) · $0.42           |   something is           |
|                                                    |   selected)              |
| ▶ ## User · 14:02:03                               |                          |
|   Help me refactor auth                            |                          |
|                                                    |                          |
|   ## Assistant · 14:02:08 · ^12k v1.2k             |                          |
|   > Thinking (3 lines)                       [>]   |                          |
|                                                    |                          |
|   I'll start by reading the middleware.            |                          |
|                                                    |                          |
|   │ Read /src/auth.py → 84 lines             [>]   |                          |
|   │ Grep session_token in src/ → 12          [>]   |                          |
|   ✘ Bash pytest tests/ → FAILED              [>]   |                          |
|                                                    |                          |
|   ## User · 14:03:15                               |                          |
|   focus on the jwt validation                      |                          |
+----------------------------------------------------+--------------------------+
 [t]hinking [/]search [q]uit [tab]panel [h]ide [?]help
```

- Left panel: scrollable conversation with summary header at top.
- Right panel: detail view for expanded tool output, file contents, thinking.
- Bottom bar: keybinding hints via Textual Footer.
- Top bar: Textual Header.

## Focus and Navigation

All content blocks (headers, text, thinking, tool calls) are individually focusable. Navigation moves between blocks, not lines.

- **Gutter**: Every block occupies a 2-char gutter column. Unfocused blocks show `  ` (spaces). Focused blocks show `▶ `.
- **Background**: Focused blocks get a `#333333` background highlight. Unfocused blocks are transparent.
- **Scroll**: `scroll_visible(top=True)` scrolls the top edge of the focused block into view, avoiding jumpy full-widget scrolling for large text blocks.

### Tab behavior

Tab switches focus between conversation and detail panels. When switching from conversation to detail, the last focused block is remembered. Tabbing back restores position instead of jumping to the top.

## Keybindings

| Key | Action |
|-----|--------|
| Up/Down, j/k | Navigate between blocks |
| Enter | Expand focused item -> detail panel |
| t | Toggle all thinking blocks collapsed/expanded |
| h | Cycle message visibility: all -> messages only -> user+tools -> all |
| / | Open search |
| Tab | Switch focus between conversation and detail panel |
| Esc | Close detail panel / close search |
| q | Quit |
| ? | Show help in detail panel |

## Thinking Blocks

Collapsed by default. Show as:

```
  > Thinking (3 lines)                         [>]
```

Press Enter to toggle inline. First Enter expands:

```
  v Thinking
  │ Let me look at the auth code first.
  │ The user wants to refactor the JWT
  │ validation middleware specifically.
```

Second Enter (when already expanded) sends full text to the detail panel.

Press `t` to toggle all thinking blocks at once.

Rendered with dim italic style and `│` left border on expanded lines.

## Tool Calls

Displayed compact in the conversation panel with bold tool name and dim result:

```
  │ Read /src/auth.py → 84 lines             [>]
  │ Grep session_token in src/ → 12           [>]
  ✘ Bash pytest tests/ → FAILED              [>]
```

### Gutter markers

| Status | Marker | Color |
|--------|--------|-------|
| Passed | `│` (dim) | default |
| Failed | `✘` | red |
| Cancelled | `~` | yellow |

When focused, the gutter marker is replaced by `▶`.

### Expansion

Selecting a tool call and pressing Enter opens its full output in the detail panel:

```
+-- Conversation -------------------------+-- Detail ---------------------+
|                                         | Bash: pytest tests/           |
| I'll start by reading the middleware.  | FAILED (exit 1)               |
|                                         |                               |
|   │ Read /src/auth.py → 84 lines [>]   | $ pytest tests/               |
|   │ Grep session_token → 12      [>]   | FAILED test_auth.py           |
| ▶ ✘ Bash pytest tests/ → FAILED  [>]   | ::test_jwt_validation         |
|                                         | AssertionError: ...           |
+-----------------------------------------+-------------------------------+
```

### File viewing

When a tool call involves a file (Read, Write, Edit), the detail panel shows file contents with syntax highlighting based on file extension (using Rich Syntax with monokai theme). Markdown files render as formatted markdown. Supported extensions: `.py`, `.js`, `.ts`, `.tsx`, `.go`, `.rs`, `.java`, `.rb`, `.sh`, `.yaml`, `.yml`, `.toml`, `.json`, `.css`, `.html`, `.md`.

## Message Visibility

`h` key cycles through visibility modes:

1. **All** (default): show everything — user messages, assistant messages, thinking, tools.
2. **Messages only**: show user and assistant headers + text. Hide thinking blocks and tool calls.
3. **User + tools**: show user messages and tool call lines only. Hide assistant text, thinking, and headers.

The footer binding label updates to show the current mode.

## Compaction Boundary

When the parser encounters a `compact_boundary` system entry, it inserts a visual separator:

```
  ─── conversation compacted ───
```

Styled dim. Not focusable.

## Search

`/` opens a search input bar docked at the bottom.

- Type a query and press Enter to jump to the first matching block.
- Search matches against `searchable_text` on all block types (message text, tool call names/summaries, thinking content).
- Esc closes search and clears the query.
- After search closes, focus returns to the first matched block.

## Colors

| Element | Style |
|---------|-------|
| User header | bold green |
| Assistant header | bold cyan |
| Thinking block | dim italic, `│` left border when expanded |
| Tool call (passed) | bold name, dim result, dim `│` gutter |
| Tool call (failed) | red text, red `✘` gutter |
| Tool call (cancelled) | yellow text, yellow `~` gutter |
| Token/cost info | dim |
| Focused block background | `#333333` |
| Detail panel file content | syntax highlighted (monokai theme) |
| Detail panel markdown | rich-rendered markdown |
