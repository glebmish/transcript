---
name: tmux-tui-capture
description: Use when reading the current rendered screen of a tmux-driven TUI session, choosing between plain text and ANSI-styled capture, and managing capture token cost.
---

# Capturing a TUI's screen with tmux

`capture-pane` reads the current contents of a tmux pane. Choose the variant that matches your question — plain for text searching, styled for color/focus logic.

## When to use

- You need to see what the TUI is rendering right now.
- You need to search the screen for a text pattern.
- You need to verify color or style (active border, highlighted row).

## Plain text capture (default, cheap)

```bash
tmux capture-pane -t tui-<label> -p
```

- `-p` — print to stdout (instead of copying to a paste buffer).
- Produces the visible pane as plain text, no escape sequences.
- ~1,200–1,500 tokens at 120×40. Use this by default.

## Styled (ANSI-escaped) capture

```bash
tmux capture-pane -t tui-<label> -e -p
```

- `-e` — preserve ANSI escape sequences for color and text attributes.
- ~3,000–5,000 tokens at 120×40 — 2–4× the plain cost.
- Only use when you specifically need color or focus information:
  - "Which panel has the active (blue) border?"
  - "Is this row highlighted?"
  - "What color is the status indicator?"

If you can answer the question from plain text, use plain.

## Full scrollback capture

```bash
tmux capture-pane -t tui-<label> -p -S - -E -
```

- `-S -` — start at the earliest line of scrollback.
- `-E -` — end at the last line of visible output.
- Useful for TUIs that write to the main screen (not alternate buffer) and have history. Textual and most full-screen TUIs use the alternate buffer — there is no meaningful scrollback for them, so omit `-S -E`.

## Bounded range

```bash
tmux capture-pane -t tui-<label> -p -S 0 -E 10
```

- `-S 0 -E 10` — lines 0 through 10 of the visible pane.
- Useful for inspecting a header or footer without returning the whole screen.

## Token economics at a glance

| Capture                 | Typical size (120×40) | Best for                                      |
| ----------------------- | --------------------- | --------------------------------------------- |
| Plain (`-p`)            | 1,200–1,500 tokens    | Text search, pattern match, layout check      |
| Styled (`-e -p`)        | 3,000–5,000 tokens    | Color/focus assertions                        |
| Bounded (`-S N -E M`)   | proportionally less   | Header/footer-only checks                     |

## Common pitfalls

- **Stale capture after input** — tmux captures whatever the pane currently shows. If you send keys and capture immediately, you may see the pre-input state. Wait for render — see the `tmux-tui-waiting` skill.
- **Styled output is noisy** — ANSI sequences are long strings like `\e[38;2;30;144;255m`. Grep carefully; prefer plain capture unless color is the question.
- **Alternate screen buffer** — most TUIs use it. `-S -` for full scrollback will mostly return the pre-TUI terminal contents, not the TUI itself. Omit range flags for alt-buffer apps.
