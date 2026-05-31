---
name: tui-demo
description: Use when you want to show/demo a TUI to the user in a visible pane they can watch live — inside their running tmux or cmux multiplexer. This skill dispatches to the correct multiplexer based on environment and then loads the branch-specific flow. Do NOT use for headless automation (use `tui-session` instead).
---

# Demoing a TUI in the user's live multiplexer

Two multiplexers are supported: **tmux** (terminal app, signaled by `$TMUX`) and **cmux** (GUI app, signaled by `$CMUX_SOCKET`). They have different CLIs, so the detailed flow lives in per-multiplexer sub-files.

## Dispatch

Run the check first. Load the matching sub-file for the actual commands.

```bash
if [ -n "$TMUX" ]; then
  echo "using tmux — load tmux.md"
elif [ -n "$CMUX_SOCKET" ]; then
  echo "using cmux — load cmux.md"
else
  echo "neither multiplexer is active"
  exit 1
fi
```

- **`$TMUX` set** → user is attached to a tmux session. Load `tmux.md` in this skill directory.
- **`$CMUX_SOCKET` set** → user has cmux running and the Unix socket is reachable. Load `cmux.md` in this skill directory.
- **Neither set** → there is no live multiplexer to render into. This skill is the wrong tool — use `tui-session` for headless automation and `tui-share` if the user needs to see an artifact remotely.
- **Both set** (unusual — usually means the user is running cmux *inside* a tmux pane or vice versa) → prefer the outer one. tmux first, because cmux-in-tmux is the common direction and rendering in the outer tmux pane is what the user actually sees on screen.

## What both branches share

Regardless of multiplexer, the shape is:

1. **Preflight** — verify the env var is actually pointing at something live (not a stale socket, not a killed session).
2. **Open a visible pane/surface** — default to splitting alongside the user's current work so they keep context. Only use a new window/workspace if the demo genuinely needs the full screen or the user asks.
3. **Run the TUI command** in that pane.
4. **Drive it** — named keys, literal text, screen reads. Same logical operations as `tui-interact`, just different CLIs.
5. **Cleanup** — leave the pane in place by default so the user can inspect it. Only close if they explicitly ask. **Never** kill the root session/workspace — that would tear down the user's own work.

Load the matching sub-file for the exact commands.

## Pitfalls that apply to both branches

- **Nested multiplexers** — if the user runs tmux-in-tmux or cmux-in-tmux, env vars point at whichever was entered most recently. Behavior is usually fine; mention it if the demo shows up in an unexpected window.
- **Never `kill-session` / `close-workspace` on the user's root** — scope kills to the pane/surface you created.
- **Command quoting** — the command you pass is a shell string; quote it: `'python -m foo --flag=bar'`.
- **Remote user with no display** (cmux case especially) — if the user is on a headless machine, they won't see anything. Fall back to `tui-session` + `tui-share`.
