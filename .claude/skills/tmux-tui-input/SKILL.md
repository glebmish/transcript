---
name: tmux-tui-input
description: Use when sending keystrokes, literal text, or multi-line pastes to a tmux-driven TUI session. Covers named keys, chords, literal input, and paste buffers.
---

# Sending input to a TUI with tmux

`send-keys` writes to the pane's PTY as if a user pressed those keys. For the TUI, it's indistinguishable from real keyboard input.

## When to use

- You need to navigate (arrows, j/k, Tab).
- You need to trigger a binding (Enter, Escape, `?`, `/`).
- You need to type text into an input field.
- You need to paste multi-line content.

## Sending a named key

```bash
tmux send-keys -t tui-<label> <KeyName>
```

Common key names tmux recognizes directly:

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

## Sending single characters

```bash
tmux send-keys -t tui-<label> j
tmux send-keys -t tui-<label> /
tmux send-keys -t tui-<label> '?'
```

Quote characters the shell would interpret (`/`, `?`, `*`, backslash, space). `j` and `k` don't need quoting but quoting is always safe.

## Sending several keys in one call

```bash
tmux send-keys -t tui-<label> j j j
```

Three separate `j` keystrokes. Space-separate the arguments.

## Typing literal text (no key translation)

```bash
tmux send-keys -t tui-<label> -l 'hello world'
```

- `-l` — literal. tmux sends the exact characters without interpreting `Enter`, `Tab`, etc. as special.
- Use this for text input fields. Follow with a separate `Enter` if you need to submit.

```bash
tmux send-keys -t tui-<label> -l 'error'
tmux send-keys -t tui-<label> Enter
```

## Pasting multi-line content

For multi-line text, use a paste buffer — `send-keys -l` with embedded newlines is fiddly.

```bash
tmux set-buffer 'line one
line two
line three'
tmux paste-buffer -t tui-<label>
```

`paste-buffer` sends the buffer as bracketed-paste if the app supports it, otherwise as raw input.

## Common pitfalls

- **Unquoted special characters** — shells interpret `?`, `*`, `/` before tmux sees them. Always quote.
- **`Enter` vs newline** — `send-keys Enter` sends a real carriage return. `send-keys -l $'\n'` sends a literal `\n` which many TUIs don't treat as Enter. Use `Enter`.
- **Uppercase letters** — `send-keys -t tui-<label> A` and `send-keys -t tui-<label> 'A'` both send a capital A; tmux passes it through.
- **Rapid bursts** — sending 10+ keys in rapid succession can overrun a slow TUI's input queue. Insert a short `sleep 0.05` between bursts if you see drops.
