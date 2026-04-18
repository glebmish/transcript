---
name: tmux-tui-sessions
description: Use when starting, listing, inspecting, or killing a headless tmux session to drive a TUI application. Covers session creation with explicit size, exit-code inspection, and cleanup.
---

# Driving TUI sessions with tmux

Use a detached tmux session to run any TUI application headlessly. The pane is a real PTY — it renders exactly as it would in a terminal, but nothing is shown to the user. You control the application by sending keystrokes and observing the rendered screen.

## When to use

- You want to run a TUI (Textual, Bubble Tea, Ratatui, curses, vim, etc.) and see what it renders, send input, or check output.
- You need a specific terminal size (responsive layout testing).
- You need the session to outlive a single command — subsequent tool calls will interact with it.

## Starting a session

```bash
tmux new-session -d -s tui-<label> -x <cols> -y <rows> '<command>'
```

- `-d` — detached. The session runs in the background.
- `-s tui-<label>` — session name. Always prefix with `tui-` to avoid colliding with the user's own sessions.
- `-x <cols> -y <rows>` — pane size in cells. Use `-x 120 -y 40` as a sensible default.
- The command is a single shell string. Quote it.

Example:

```bash
tmux new-session -d -s tui-transcript -c /path/to/repo -x 120 -y 40 \
  '.venv/bin/transcript view tests/fixtures/claude_minimal.jsonl'
```

`-c <dir>` sets the session's working directory. Use it whenever the command depends on cwd (e.g., resolving relative paths to fixtures or venvs).

Give the app a moment to render before capturing — see the `tmux-tui-waiting` skill.

## Checking whether a session exists

```bash
tmux has-session -t tui-<label> 2>/dev/null && echo alive || echo gone
```

`has-session` exits 0 if it exists, non-zero otherwise. Always redirect stderr — tmux prints "can't find session" when it doesn't exist.

## Listing your sessions

```bash
tmux list-sessions -F '#{session_name}' 2>/dev/null | grep '^tui-'
```

Filter by the `tui-` prefix so you only see your own sessions, not the user's.

## Inspecting session state (exit code, liveness)

```bash
tmux display-message -t tui-<label> -p '#{pane_dead} #{pane_dead_status}'
```

- `#{pane_dead}` — `0` if process is still running, `1` if it exited.
- `#{pane_dead_status}` — the exit code (empty while running).

To keep the final screen visible after the TUI exits, set `remain-on-exit` when creating the session:

```bash
tmux new-session -d -s tui-<label> -x 120 -y 40 '<cmd>' \
  \; set-option -t tui-<label> remain-on-exit on
```

## Killing a session

```bash
tmux kill-session -t tui-<label>
```

This terminates the TUI process and releases the PTY. Always clean up when done — leftover sessions accumulate and can confuse subsequent runs.

## Killing all tui- sessions (cleanup after a run)

```bash
tmux list-sessions -F '#{session_name}' 2>/dev/null \
  | grep '^tui-' \
  | xargs -I{} tmux kill-session -t {}
```

## Common pitfalls

- **Session already exists** — `new-session` fails if a session with that name is alive. Either kill it first or use a unique label.
- **TUI exited immediately** — the session stays alive briefly (with `remain-on-exit`), then disappears. If `capture-pane` returns nothing, check `pane_dead` first.
- **Command path / cwd** — `new-session`'s command runs in the user's shell working directory unless you set `-c <dir>`. If the TUI depends on cwd (virtualenv binaries, relative fixture paths), set `-c` explicitly.
