---
name: tui-session
description: Use when starting, listing, inspecting, resizing, or killing a headless tmux session to drive a TUI application. Covers session lifecycle end-to-end — creation at a specific terminal size, exit-code inspection, resize for responsive-layout testing, and cleanup.
---

# Driving TUI sessions with tmux

Use a detached tmux session to run any TUI application headlessly. The pane is a real PTY — it renders exactly as it would in a terminal, but nothing is shown to the user. You control the application by sending keystrokes and observing the rendered screen (see the `tui-interact` skill).

## When to use

- You want to run a TUI (Textual, Bubble Tea, Ratatui, curses, vim, etc.) and see what it renders, send input, or check output.
- You need a specific terminal size (responsive layout testing).
- You need the session to outlive a single command — subsequent tool calls will interact with it.

For a *visible* demo in the user's own multiplexer, use `tui-demo` instead.

## Naming: derive from the Codex session id

Don't invent ad-hoc labels. Obtain the current Codex session id (invoke the `get-session-id` skill if you don't already have it from earlier in the conversation) and use it as the stable identifier for every tmux session, recording, and shared artifact in this conversation.

```bash
SID=<session-uuid-from-get-session-id>     # e.g. 01234567-89ab-cdef-0123-456789abcdef
SID_SHORT=${SID:0:8}                       # e.g. 01234567 — short, readable, still unique in practice
```

tmux session name: `tui-$SID_SHORT` by default. If you need multiple tmux sessions in one conversation (rare), append a slug: `tui-$SID_SHORT-<slug>` (e.g. `tui-01234567-transcript`).

## Starting a session

```bash
tmux new-session -d -s tui-$SID_SHORT -x <cols> -y <rows> '<command>'
```

- `-d` — detached. The session runs in the background.
- `-s tui-$SID_SHORT` — session name. The `tui-` prefix + session-id segment avoids colliding with the user's own sessions and with any other agent session.
- `-x <cols> -y <rows>` — pane size in cells. Use `-x 120 -y 40` as a sensible default.
- The command is a single shell string. Quote it.

Example:

```bash
SID_SHORT=01234567
tmux new-session -d -s tui-$SID_SHORT -c /path/to/repo -x 120 -y 40 \
  '.venv/bin/transcript view tests/fixtures/claude_minimal.jsonl'
```

`-c <dir>` sets the session's working directory. Use it whenever the command depends on cwd (e.g., resolving relative paths to fixtures or venvs).

Give the app a moment to render before capturing — see the waiting strategies in `tui-interact`.

## Checking whether a session exists

```bash
tmux has-session -t tui-$SID_SHORT 2>/dev/null && echo alive || echo gone
```

`has-session` exits 0 if it exists, non-zero otherwise. Always redirect stderr — tmux prints "can't find session" when it doesn't exist.

## Listing your sessions

```bash
tmux list-sessions -F '#{session_name}' 2>/dev/null | grep "^tui-$SID_SHORT"
```

Filter by `tui-$SID_SHORT` to see only this conversation's sessions, not leftovers from other runs or the user's own sessions.

## Inspecting session state (exit code, liveness)

```bash
tmux display-message -t tui-$SID_SHORT -p '#{pane_dead} #{pane_dead_status}'
```

- `#{pane_dead}` — `0` if process is still running, `1` if it exited.
- `#{pane_dead_status}` — the exit code (empty while running).

To keep the final screen visible after the TUI exits, set `remain-on-exit` when creating the session:

```bash
tmux new-session -d -s tui-$SID_SHORT -x 120 -y 40 '<cmd>' \
  \; set-option -t tui-$SID_SHORT remain-on-exit on
```

## Swapping workloads in a running session

If you need to run the TUI against several inputs (e.g. iterating through fixtures), **don't** `kill-session` + `new-session` each time — that rebuilds the PTY, loses resize state, and forces a fresh mkdir/poller pipeline for anything tracking the session. Instead, respawn the pane:

```bash
tmux respawn-pane -k -t tui-$SID_SHORT \
  '.venv/bin/transcript view tests/fixtures/other.jsonl'
sleep 1
```

- `-k` kills the old process occupying the pane, then launches the new command in its place.
- Pane dimensions, `remain-on-exit`, and the session itself are preserved.
- The new command inherits the pane's current working directory (set at `new-session` time via `-c`).

Use `respawn-pane` for quick iteration; reserve `kill-session` + `new-session` for cases where you actually want the tmux process tree reset (different size, different cwd, stuck state).

## Resizing a running session

TUI rendering depends on terminal dimensions. Resize to reproduce layout bugs at narrow widths, short heights, or unusual aspect ratios.

```bash
tmux resize-window -t tui-$SID_SHORT -x <cols> -y <rows>
```

The TUI receives `SIGWINCH` and re-renders. Give it a moment to settle before capturing:

```bash
tmux resize-window -t tui-$SID_SHORT -x 60 -y 20
sleep 0.3
tmux capture-pane -t tui-$SID_SHORT -p
```

### Reference sizes

| Size    | Name           | Use                                              |
| ------- | -------------- | ------------------------------------------------ |
| 80×24   | Classic VT     | Minimum — many TUIs target this as a floor       |
| 100×30  | Small laptop   | Compact but realistic                            |
| 120×40  | Default        | Sensible baseline, enough for dual-pane layouts  |
| 160×50  | Wide monitor   | Tests behavior when extra horizontal space       |
| 200×60  | Ultra-wide     | Stress test for very wide terminals              |
| 60×20   | Tight          | Edge case — layout often breaks or collapses     |

### Reading the current size

```bash
tmux display-message -t tui-$SID_SHORT -p '#{pane_width} #{pane_height}'
```

Prints two integers separated by a space (cols rows).

## Killing a session

```bash
tmux kill-session -t tui-$SID_SHORT
```

This terminates the TUI process and releases the PTY. Always clean up when done — leftover sessions accumulate and can confuse subsequent runs.

### Killing all sessions for this conversation

```bash
tmux list-sessions -F '#{session_name}' 2>/dev/null \
  | grep "^tui-$SID_SHORT" \
  | xargs -I{} tmux kill-session -t {}
```

### Killing all tui- sessions (broad cleanup, including older conversations)

```bash
tmux list-sessions -F '#{session_name}' 2>/dev/null \
  | grep '^tui-' \
  | xargs -I{} tmux kill-session -t {}
```

## Common pitfalls

- **Session already exists** — `new-session` fails if a session with that name is alive. Either kill it first or use a unique label.
- **TUI exited immediately** — the session stays alive briefly (with `remain-on-exit`), then disappears. If `capture-pane` returns nothing, check `pane_dead` first.
- **Command path / cwd** — `new-session`'s command runs in the user's shell working directory unless you set `-c <dir>`. If the TUI depends on cwd (virtualenv binaries, relative fixture paths), set `-c` explicitly.
- **Minimum size limits** — tmux enforces a minimum pane size (usually 20×5). Attempts to go below fail silently; verify with `display-message`.
- **Re-render latency on resize** — some TUIs take 100–300ms to fully re-render after `SIGWINCH`. Don't capture immediately.
- **Alt-screen redraw quirks** — rapid consecutive resizes can leave artifacts. Avoid resize-capture-resize-capture sequences without brief sleeps.
