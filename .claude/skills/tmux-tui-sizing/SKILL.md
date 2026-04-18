---
name: tmux-tui-sizing
description: Use when creating a tmux session at a specific terminal size or resizing a running session to test responsive TUI layouts.
---

# Sizing and resizing a TUI session

TUI rendering depends on terminal dimensions. Test at multiple sizes to catch layout bugs that only appear at narrow widths, short heights, or unusual aspect ratios.

## When to use

- You're testing responsive layout behavior.
- You need to reproduce a bug that only shows at a specific size.
- You want to confirm the TUI degrades gracefully when terminals are small.

## Setting size at session creation

See the `tmux-tui-sessions` skill — use `-x <cols> -y <rows>`:

```bash
tmux new-session -d -s tui-<label> -x 120 -y 40 '<command>'
```

## Resizing a running session

```bash
tmux resize-window -t tui-<label> -x <cols> -y <rows>
```

The TUI receives `SIGWINCH` and re-renders. Give it a moment to settle before capturing (see the `tmux-tui-waiting` skill).

```bash
tmux resize-window -t tui-transcript -x 60 -y 20
sleep 0.3
tmux capture-pane -t tui-transcript -p
```

## Reference sizes

| Size    | Name           | Use                                              |
| ------- | -------------- | ------------------------------------------------ |
| 80×24   | Classic VT     | Minimum — many TUIs target this as a floor       |
| 100×30  | Small laptop   | Compact but realistic                            |
| 120×40  | Default        | Sensible baseline, enough for dual-pane layouts  |
| 160×50  | Wide monitor   | Tests behavior when extra horizontal space       |
| 200×60  | Ultra-wide     | Stress test for very wide terminals              |
| 60×20   | Tight          | Edge case — layout often breaks or collapses     |

## Reading the current size

```bash
tmux display-message -t tui-<label> -p '#{pane_width} #{pane_height}'
```

Prints two integers separated by a space (cols rows).

## Common pitfalls

- **Minimum size limits** — tmux enforces a minimum pane size (usually 20×5). Attempts to go below fail silently; verify with `display-message`.
- **Session tracks the client** — if no client is attached, the session's pane size is set by `-x -y` at creation. `resize-window` changes it explicitly.
- **Re-render latency** — some TUIs take 100–300ms to fully re-render after resize. Don't capture immediately.
- **Alt-screen redraw quirks** — rapid consecutive resizes can leave artifacts. Avoid resize-capture-resize-capture sequences without brief sleeps.
