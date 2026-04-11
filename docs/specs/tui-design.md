# TUI Design

## Launch

```
transcript view <input_file>
```

## Framework

- `textual` for the TUI application and widgets.
- `rich` for markdown rendering and syntax highlighting within panels.

## Layout

Two-panel split: conversation on the left, detail on the right.

```
+-- Conversation ------------------------------------+-- Detail ----------------+
| # Transcript                                       |                          |
| Duration: 12m . claude-opus-4-6                    |  (empty until            |
| Messages: 8 . Tools: 12 (1 x) . $0.42             |   something is           |
|                                                    |   selected)              |
| -------------------------------------------------- |                          |
|                                                    |                          |
| ## User . 14:02:03                                 |                          |
| Help me refactor auth                              |                          |
|                                                    |                          |
| ## Assistant . 14:02:08 . ^12k v1.2k               |                          |
| > Thinking (3 lines)                         [>]   |                          |
|                                                    |                          |
| I'll start by reading the middleware.              |                          |
|                                                    |                          |
|   Read: /src/auth.py -> 84 lines             [>]   |                          |
|   Grep: session_token in src/ -> 12          [>]   |                          |
| x Bash: pytest tests/ -> FAILED              [>]   |                          |
|                                                    |                          |
| ## User . 14:03:15                                 |                          |
| focus on the jwt validation                        |                          |
+----------------------------------------------------+--------------------------+
 [t]hinking [/]search [q]uit [tab]panel [h]ide [?]help
```

- Left panel: scrollable conversation with summary header at top.
- Right panel: detail view for expanded tool output, file contents, plans.
- Bottom bar: keybinding hints.

## Keybindings

| Key | Action |
|-----|--------|
| Up/Down, j/k | Scroll conversation |
| Enter | Expand focused item -> detail panel |
| t | Toggle all thinking blocks collapsed/expanded |
| h | Cycle message visibility: all -> assistant only -> user only -> all |
| / | Open search |
| Tab | Switch focus between conversation and detail panel |
| Esc | Close detail panel / close search |
| q | Quit |
| ? | Show help overlay |

## Thinking Blocks

Collapsed by default. Show as:

```
> Thinking (3 lines)                         [>]
```

Press Enter on a thinking block or `t` to toggle all. Expanded:

```
v Thinking
| Let me look at the auth code first.
| The user wants to refactor the JWT
| validation middleware specifically.
```

Rendered with a left border and dim italic style, visually distinct from message text.

## Tool Calls

Displayed compact in the conversation panel:

```
  Read: /src/auth.py -> 84 lines             [>]
  Grep: session_token in src/ -> 12           [>]
x Bash: pytest tests/ -> FAILED              [>]
```

### Gutter markers

| Status | Marker | Color |
|--------|--------|-------|
| Passed | (none) | default |
| Failed | x | red |
| Cancelled | ~ | yellow |

### Expansion

Selecting a tool call and pressing Enter opens its full output in the detail panel. The conversation panel shows `[<]` on the active tool call:

```
+-- Conversation -------------------------+-- Detail ---------------------+
|                                         | Bash: pytest tests/           |
| I'll start by reading the middleware.  | ------------------------------ |
|                                         | FAILED (exit 1)               |
|   Read: /src/auth.py -> 84 lines [>]   |                               |
|   Grep: session_token -> 12      [>]   | $ pytest tests/               |
| x Bash: pytest tests/ -> FAILED  [<]   | FAILED test_auth.py           |
|                                         | ::test_jwt_validation         |
|                                         | AssertionError: ...           |
+-----------------------------------------+-------------------------------+
```

### File viewing

When a tool call involves a file (Read, Write, Edit), the detail panel shows file contents with syntax highlighting based on file extension. Markdown and plan files render as formatted markdown rather than raw text.

## Message Visibility

`h` key cycles through visibility modes:

1. **All** (default): show user and assistant messages.
2. **Assistant only**: hide user messages, focus on what the agent did.
3. **User only**: just the prompts.

## Search

`/` opens a search bar at the bottom with a scope selector:

```
+-----------------------------------------------------------------------+
| Search: jwt_validation          Scope: [messages] thinking  tools     |
+-----------------------------------------------------------------------+
```

- Tab cycles between scopes: messages, thinking, tools.
- Enter jumps to next match.
- Shift+Enter jumps to previous match.
- Matches are highlighted in the conversation panel.
- Esc closes search.

### Scope definitions

| Scope | Searches across |
|-------|----------------|
| messages | User and assistant text blocks |
| thinking | Thinking/reasoning block content |
| tools | Tool call names, summaries, result summaries, and full output |

## Colors

| Element | Style |
|---------|-------|
| User header | bold blue |
| Assistant header | bold green |
| Thinking block | dim italic, left border |
| Tool call (passed) | default |
| Tool call (failed) | red text, red x gutter |
| Tool call (cancelled) | yellow text, yellow ~ gutter |
| Token/cost info | dim |
| Search match | inverse/highlight |
| Detail panel file content | syntax highlighted by extension |
| Detail panel markdown | rich-rendered markdown |
