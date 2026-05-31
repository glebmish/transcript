# Demoing in the user's tmux session

Loaded by the `tui-demo` dispatcher when `$TMUX` is set.

## Preflight

```bash
[ -n "$TMUX" ] || { echo "TMUX not set — wrong branch"; exit 1; }
```

If `$TMUX` is empty, you're in the wrong branch — go back to SKILL.md and re-dispatch.

## Open a visible pane

Pick one based on how much screen the demo needs.

### Split the current window (side-by-side, user keeps context)

```bash
PANE=$(tmux split-window -h -l 60% -P -F '#{pane_id}' '<command>')
```

- `-h` — horizontal split (panes side-by-side); use `-v` for stacked.
- `-l 60%` — new pane size.
- `-P -F '#{pane_id}'` — print the new pane's id (e.g. `%42`). Capture it for follow-up commands.

### Open a new window (TUI full-screen)

```bash
WIN=$(tmux new-window -n demo -P -F '#{window_id}' '<command>')
```

User switches to this window to watch the TUI full-screen without losing original work.

## Keeping the pane visible after the command exits

Short-lived TUIs vanish when the command ends. Enable `remain-on-exit`:

```bash
tmux set-window-option -t "$WIN" remain-on-exit on
```

Set this BEFORE running a command that may exit quickly, or use `respawn-pane` later.

## Setting the pane size

tmux panes inherit the user's terminal size. For responsive-layout demos, resize after opening:

```bash
tmux resize-pane -t "$PANE" -x 120 -y 40
```

See `tui-session` for reference sizes and common pitfalls.

## Sending input / reading output

Target by the captured pane or window id — all the operations in `tui-interact` work the same way whether the session is attached or detached:

```bash
tmux send-keys     -t "$PANE" j
tmux send-keys     -t "$PANE" -l 'hello'
tmux send-keys     -t "$PANE" Enter
tmux capture-pane  -t "$PANE" -p
```

## Cleanup

Leave the pane in place so the user can inspect it. Only remove if the user explicitly asks:

```bash
tmux kill-pane   -t "$PANE"   # specific pane
tmux kill-window -t "$WIN"    # full window
```

**NEVER `kill-session`** — that would terminate the user's entire tmux.

## Pitfalls specific to tmux

- **Running outside tmux** — `$TMUX` empty means `split-window`/`new-window` has no target session. Preflight first.
- **Command with spaces / quotes** — quote the command argument: `tmux new-window -n demo 'python -m foo --flag=bar'`.
