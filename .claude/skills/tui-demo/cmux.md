# Demoing in the user's cmux app

Loaded by the `tui-demo` dispatcher when `$CMUX_SOCKET` is set. `cmux` is a GUI terminal multiplexer controlled via a Unix socket.

## Preflight

```bash
[ -n "$CMUX_SOCKET" ] || { echo "CMUX_SOCKET not set — wrong branch"; exit 1; }
cmux ping
```

`cmux ping` verifies the socket is actually reachable. If it errors, stop — cmux isn't running or the socket path is stale.

## Open a visible pane (preferred)

Default: split a new pane into the user's **current** workspace so the demo sits side-by-side with their existing work. Don't hide it behind a separate tab.

```bash
SURF=$(cmux new-pane --type terminal --direction right | awk '{print $NF}')
```

Returned surface ref (e.g. `surface:5`) is used for follow-up commands — `send`, `send-key`, `read-screen` all accept `--surface`.

Run the command in that pane:

```bash
cmux send     --surface "$SURF" 'cd /path/to/repo && ./run.sh'
cmux send-key --surface "$SURF" Enter
```

### Fallback — new workspace

Only use a new workspace if the user explicitly asks for one, or the TUI genuinely needs a full tab:

```bash
cmux new-workspace --name demo --cwd /path/to/repo --command './run.sh'
# returns: workspace:N
```

## Sending input

```bash
cmux send     --surface "$SURF" 'hello'
cmux send-key --surface "$SURF" Enter
cmux send-key --surface "$SURF" C-c
```

- `send` — literal text (no key interpretation).
- `send-key` — named key: `Enter`, `Tab`, `Escape`, `Up`/`Down`/`Left`/`Right`, `C-c`, `M-x`, etc.

If you opened a workspace instead, swap `--surface "$SURF"` for `--workspace "$WS"`.

## Reading the rendered screen

```bash
cmux read-screen  --surface "$SURF"
cmux read-screen  --surface "$SURF" --lines 40
cmux capture-pane --surface "$SURF" --scrollback
```

- `read-screen` — currently visible text.
- `capture-pane --scrollback` — includes history above the viewport.
- `--lines N` — cap output to the last N lines (useful for short context).

## Waiting for the TUI to render

Poll `read-screen` until expected text appears, with a short sleep between tries. Same pattern as `tui-interact`, swap `tmux capture-pane` for `cmux read-screen`:

```bash
for i in {1..20}; do
  cmux read-screen --surface "$SURF" | grep -q 'Ready' && break
  sleep 0.25
done
```

## Cleanup

Leave the pane in place so the user can inspect it. Only close if the user explicitly asks:

```bash
cmux close-surface --surface "$SURF"
# or, for a workspace demo:
cmux close-workspace --workspace "$WS"
```

## Pitfalls specific to cmux

- **Socket auth** — if the user has a cmux password configured, set `CMUX_SOCKET_PASSWORD` (or pass `--password`) or every command will fail.
- **Remote / headless user** — cmux is a desktop GUI. If the user is on a machine without a display, they won't see anything; fall back to `tui-session` (headless) + `tui-share`.
- **Stale socket** — `$CMUX_SOCKET` can point at a path left over from a crashed cmux. `cmux ping` catches this before you try to open a workspace.
- **Command quoting** — `--command` takes a shell string. Quote it: `--command 'python -m foo --flag=bar'`.
