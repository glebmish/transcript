---
name: tmux-tui-waiting
description: Use when synchronizing between sending input to a TUI and capturing its rendered screen. Covers sleep-based waits, polling for a stable render, and waiting for specific text to appear.
---

# Waiting for a TUI to render

tmux commands run instantly, but the TUI needs time to process input and re-render. Capturing too early returns the pre-input screen. Use one of these strategies to wait for the screen to settle.

## When to use

- You sent input and need to capture the result.
- You started a TUI and need to wait for its initial render.
- You triggered an operation and need to wait for it to complete.

## Strategy 1: fixed sleep (simplest, default)

```bash
tmux send-keys -t tui-<label> j
sleep 0.3
tmux capture-pane -t tui-<label> -p
```

Good defaults:

| Situation                          | Sleep duration |
| ---------------------------------- | -------------- |
| After a single keystroke           | `0.1`–`0.3s`   |
| After starting a TUI               | `1s`           |
| After triggering a slow operation  | `1`–`3s`       |
| After a resize                     | `0.3s`         |

Fixed sleep is the right default — it's simple and works. Only reach for polling if sleep is either wasting too much time or not enough.

## Strategy 2: poll for a stable screen

Capture, hash, wait, capture again. When two consecutive captures match, the screen has settled.

```bash
prev=""
for i in 1 2 3 4 5; do
  current=$(tmux capture-pane -t tui-<label> -p | sha256sum)
  if [ "$current" = "$prev" ] && [ -n "$prev" ]; then
    break
  fi
  prev=$current
  sleep 0.1
done
tmux capture-pane -t tui-<label> -p
```

- Total wait: up to 500ms, but exits early when stable.
- Use when the render time is unpredictable (e.g., waiting on a search result, spinner finishing, variable animation).

## Strategy 3: wait for specific text

```bash
for i in $(seq 1 30); do
  if tmux capture-pane -t tui-<label> -p | grep -q 'Show: user + tools'; then
    break
  fi
  sleep 0.1
done
```

- Total wait: up to 3 seconds.
- Use when you know exactly what text should appear (status bar update, prompt, error).
- If the text never appears, the loop exits naturally — check the final capture to confirm.

## Strategy 4: wait for a process to exit

```bash
for i in $(seq 1 50); do
  dead=$(tmux display-message -t tui-<label> -p '#{pane_dead}')
  if [ "$dead" = "1" ]; then
    break
  fi
  sleep 0.1
done
```

See the `tmux-tui-sessions` skill for `pane_dead` semantics.

## Common pitfalls

- **Sleeping too little** — a 50ms sleep looks fast but can race with slow renders (especially Textual on startup). When in doubt, double the sleep.
- **Sleeping forever** — don't just bump sleeps until things work. If you need more than 3s after a keystroke, something is wrong (app hung, binding missing, wrong session).
- **Capturing before the PTY drains** — tmux captures the current rendered state of the pane; if the TUI is mid-frame, you may see a partial render. Two consecutive identical captures (strategy 2) detect this.
- **Polling for fragile text** — don't match on cursor position or timestamps that change every render. Match on stable text (section headings, static status labels).
