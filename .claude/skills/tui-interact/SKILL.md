---
name: tui-interact
description: Use when driving a running tmux TUI session — sending keystrokes, literal text, or multi-line paste; waiting for the TUI to render; and capturing the rendered screen (plain text or ANSI-styled). Covers the full send→wait→capture loop that is the core of TUI automation.
---

# Interacting with a running TUI session

Assumes a tmux session already exists, named `tui-$SID_SHORT` where `$SID_SHORT` is the first 8 chars of the current Claude session id (see `tui-session` for how to start one and `get-session-id` for the session id). The core loop is: send input, wait for the TUI to settle, capture the screen, decide what to do next.

## When to use

- You have a running TUI session and need to drive it.
- You need to navigate (arrows, j/k, Tab), trigger a binding (Enter, Escape), type into an input field, or paste multi-line content.
- You need to read the TUI's current rendered state to decide the next action.

---

## 1. Sending input

`tmux send-keys` writes to the pane's PTY as if a user pressed those keys. For the TUI, it's indistinguishable from real keyboard input.

### Named keys

```bash
tmux send-keys -t tui-$SID_SHORT <KeyName>
```

| Key                      | tmux name           |
| ------------------------ | ------------------- |
| Enter / Return           | `Enter`             |
| Escape                   | `Escape`            |
| Tab                      | `Tab`               |
| Backspace                | `BSpace`            |
| Space                    | `Space`             |
| Arrow keys               | `Up`, `Down`, `Left`, `Right` |
| Function keys            | `F1` through `F12`  |
| Ctrl-C                   | `C-c`               |
| Ctrl-D                   | `C-d`               |
| Ctrl-<X>                 | `C-<x>` (lowercase) |
| Alt-<X>                  | `M-<x>`             |
| Page Up / Page Down      | `PageUp`, `PageDown`|
| Home / End               | `Home`, `End`       |

Case matters for modifiers (`C-c` not `c-c`); tmux is forgiving on the key letter.

### Single characters

```bash
tmux send-keys -t tui-$SID_SHORT j
tmux send-keys -t tui-$SID_SHORT /
tmux send-keys -t tui-$SID_SHORT '?'
```

Quote characters the shell would interpret (`/`, `?`, `*`, backslash, space). `j`/`k` don't need quoting but quoting is always safe.

### Multiple keys in one call

```bash
tmux send-keys -t tui-$SID_SHORT j j j
```

Three separate `j` keystrokes, space-separated — but **avoid this form**. Textual and other Python-based TUIs frequently coalesce bursts that arrive faster than one render cycle; three `j`s land as a single move. Space the keystrokes out:

```bash
for k in j j j; do
  tmux send-keys -t tui-$SID_SHORT "$k"
  sleep 0.1
done
```

A 100 ms gap between keys is the reliable minimum. Cheap helper to put at the top of a driving script:

```bash
send() { for k in "$@"; do tmux send-keys -t "tui-$SID_SHORT" "$k"; sleep 0.1; done; }
send j j j              # three real moves, not one
send Down Down Enter    # mixed named keys too
```

### Literal text (no key translation)

```bash
tmux send-keys -t tui-$SID_SHORT -l 'hello world'
```

- `-l` — literal. tmux sends the exact characters without interpreting `Enter`, `Tab`, etc. as special.
- Use this for text input fields. Follow with a separate `Enter` if you need to submit.

```bash
tmux send-keys -t tui-$SID_SHORT -l 'error'
tmux send-keys -t tui-$SID_SHORT Enter
```

### Multi-line paste

For multi-line text, use a paste buffer — `send-keys -l` with embedded newlines is fiddly.

```bash
tmux set-buffer 'line one
line two
line three'
tmux paste-buffer -t tui-$SID_SHORT
```

`paste-buffer` sends the buffer as bracketed-paste if the app supports it, otherwise as raw input.

---

## 2. Waiting for the TUI to render

tmux commands run instantly, but the TUI needs time to process input and re-render. Capturing too early returns the pre-input screen. Pick the strategy that matches what you're waiting for.

### Fixed sleep (simplest, default)

```bash
tmux send-keys -t tui-$SID_SHORT j
sleep 0.3
tmux capture-pane -t tui-$SID_SHORT -p
```

Good defaults:

| Situation                          | Sleep duration |
| ---------------------------------- | -------------- |
| After a single keystroke           | `0.1`–`0.3s`   |
| After starting a TUI               | `1s`           |
| After triggering a slow operation  | `1`–`3s`       |
| After a resize                     | `0.3s`         |

Fixed sleep is the right default — it's simple and works. Only reach for polling if sleep is wasting too much time or isn't enough.

### Poll for a stable screen

Capture, hash, wait, capture again. When two consecutive captures match, the screen has settled.

```bash
prev=""
for i in 1 2 3 4 5; do
  current=$(tmux capture-pane -t tui-$SID_SHORT -p | sha256sum)
  if [ "$current" = "$prev" ] && [ -n "$prev" ]; then
    break
  fi
  prev=$current
  sleep 0.1
done
tmux capture-pane -t tui-$SID_SHORT -p
```

Use when render time is unpredictable (search results, spinner finishing, variable animation). Total wait up to 500ms but exits early.

### Wait for specific text

```bash
for i in $(seq 1 30); do
  if tmux capture-pane -t tui-$SID_SHORT -p | grep -q 'Show: user + tools'; then
    break
  fi
  sleep 0.1
done
```

Use when you know exactly what text should appear. Total wait up to 3s; if the text never appears, the loop exits naturally — check the final capture to confirm.

### Wait for the process to exit

```bash
for i in $(seq 1 50); do
  dead=$(tmux display-message -t tui-$SID_SHORT -p '#{pane_dead}')
  if [ "$dead" = "1" ]; then
    break
  fi
  sleep 0.1
done
```

See `tui-session` for `pane_dead` semantics.

---

## 3. Capturing the rendered screen

`tmux capture-pane` reads the current contents of a tmux pane. Choose the variant that matches your question — plain for text searching, styled for color/focus logic.

### Plain text (default, cheap)

```bash
tmux capture-pane -t tui-$SID_SHORT -p
```

- `-p` — print to stdout (instead of copying to a paste buffer).
- Plain text, no escape sequences.
- ~1,200–1,500 tokens at 120×40. Use this by default.

### Styled (ANSI-escaped)

```bash
tmux capture-pane -t tui-$SID_SHORT -e -p
```

- `-e` — preserve ANSI escape sequences for color and text attributes.
- ~3,000–5,000 tokens at 120×40 — 2–4× the plain cost.
- Only use when you specifically need color or focus information:
  - "Which panel has the active (blue) border?"
  - "Is this row highlighted?"
  - "What color is the status indicator?"

If you can answer the question from plain text, use plain.

### Full scrollback

```bash
tmux capture-pane -t tui-$SID_SHORT -p -S - -E -
```

- `-S -` — start at the earliest line of scrollback.
- `-E -` — end at the last line of visible output.
- Useful for TUIs that write to the main screen (not alternate buffer). Textual and most full-screen TUIs use the alternate buffer — there is no meaningful scrollback for them, so omit `-S -E`.

### Bounded range

```bash
tmux capture-pane -t tui-$SID_SHORT -p -S 0 -E 10
```

- Lines 0 through 10 of the visible pane.
- Useful for inspecting a header or footer without returning the whole screen.

### Token economics

| Capture                 | Typical size (120×40) | Best for                                      |
| ----------------------- | --------------------- | --------------------------------------------- |
| Plain (`-p`)            | 1,200–1,500 tokens    | Text search, pattern match, layout check      |
| Styled (`-e -p`)        | 3,000–5,000 tokens    | Color/focus assertions                        |
| Bounded (`-S N -E M`)   | proportionally less   | Header/footer-only checks                     |

### Verification via capture vs. image

When the question is "did the fix change the pane?" or "which row has the selection bg?", stay in the ANSI — `diff`, `grep`, `awk`. Rendering to an image to eyeball it costs 10× the tokens for an inferior answer. Vision is for perceptual questions ("does this look right") where a focused crop of the rendered image is the right tool — see `tui-share`.

---

## Common pitfalls

- **Unquoted special characters** — shells interpret `?`, `*`, `/` before tmux sees them. Always quote.
- **`Enter` vs newline** — `send-keys Enter` sends a real carriage return. `send-keys -l $'\n'` sends a literal `\n` which many TUIs don't treat as Enter. Use `Enter`.
- **Rapid bursts** — covered in "Sending input" above; always use the `send()` helper with a 100 ms gap rather than `tmux send-keys j j j`. The single-call form is in tmux's manual but is wrong for almost every TUI.
- **Sleeping too little** — a 50ms sleep looks fast but can race with slow renders (especially Textual on startup). When in doubt, double the sleep.
- **Sleeping forever** — don't just bump sleeps until things work. If you need more than 3s after a keystroke, something is wrong (app hung, binding missing, wrong session).
- **Capturing before the PTY drains** — if the TUI is mid-frame, you may see a partial render. The stable-screen poll strategy detects this.
- **Polling on fragile text** — don't match on cursor position or timestamps that change every render. Match on stable text (section headings, static status labels).
- **Styled output is noisy** — ANSI sequences are long strings like `\e[38;2;30;144;255m`. Grep carefully; prefer plain capture unless color is the question.
- **Alternate screen buffer** — most TUIs use it. `-S -` for full scrollback will mostly return the pre-TUI terminal contents, not the TUI itself. Omit range flags for alt-buffer apps.
