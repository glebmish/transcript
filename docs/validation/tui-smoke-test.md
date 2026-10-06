# TUI smoke test (tmux)

A short manual check that `transcript view` starts, renders, and responds to keys in a real terminal. Run it after changing anything under `transcript/tui/`. The automated tests in `tests/test_tui.py` drive the app headlessly; this runbook covers what they don't: a real terminal, real key input, and real colours.

## Requirements

- tmux
- A dev environment: `python3 -m venv .venv` and `.venv/bin/pip install -e .`

The commands call `.venv/bin/transcript` on purpose, so they test this checkout and don't depend on what `transcript` resolves to on your `PATH`. Replace `<repo-root>` with the path to your clone.

## Setup

Run all scenarios in one shell session, in order. Each scenario lists the commands and the expected result.

```bash
cd <repo-root>
S=transcript-smoke   # tmux server name; -L keeps it apart from your own tmux sessions
OUT=$(mktemp -d)     # scratch directory for captures

# start WIDTH HEIGHT: (re)start the TUI on the fixture in a fresh tmux server
start() {
  tmux -L "$S" kill-server 2>/dev/null
  tmux -L "$S" new-session -d -s tui -c "$PWD" -x "$1" -y "$2" \
    '.venv/bin/transcript view tests/fixtures/claude_minimal.jsonl'
  sleep 1.5
}

# key K...: send keys one at a time. Keys sent in one burst can be dropped.
key() {
  for k in "$@"; do tmux -L "$S" send-keys -t tui "$k"; sleep 0.2; done
  sleep 0.3
}

# plain / styled: capture the screen without or with ANSI colours (also saved in $OUT)
plain()  { tmux -L "$S" capture-pane -t tui -p    | tee "$OUT/plain.txt"; }
styled() { tmux -L "$S" capture-pane -t tui -e -p | tee "$OUT/styled.txt"; }

# borders: foreground colours on the top border row, left panel first
borders() { styled >/dev/null; sed -n 2p "$OUT/styled.txt" | grep -o '38;2;[0-9;]*m'; }
```

The fixture `tests/fixtures/claude_minimal.jsonl` gives these focusable rows, top to bottom:

```text
 1  ## User · 10:00:00
 2  Help me refactor auth
 3  ## Assistant · 10:00:05 · ↑10,000 ↓500
 4  Thinking (1 line)  [>]
 5  I'll read the middleware.
 6  Read /src/auth.py → 84 lines  [>]
 7  ## User · 10:02:00
 8  Focus on JWT validation
 9  ## Assistant · 10:02:05 · ↑12,000 ↓300
10  I'll look at JWT handling.
11  Bash Run tests → FAILED (exit 1)  [>]
```

## 1. Startup

```bash
start 120 40
plain
borders
```

Expected:

- The title bar reads `transcript`.
- The left panel starts with `# Transcript`, `Duration: 2m 5s · claude-opus-4-6` and `Messages: 4 · Tools: 2 (1 x) · $0.04`.
- Row 1 is focused: `▶ ## User · 10:00:00`.
- The right panel reads `Select a tool call or thinking block and press Enter to view details`.
- The footer starts with `tab Panel: right  q Quit  t Thinking  h Show: all  / Search  ? Help`.
- `borders` prints `38;2;30;144;255m` (conversation panel, dodgerblue, active) and then `38;2;105;105;105m` (detail panel, dimgray).

## 2. Block navigation

```bash
key j j j
plain | grep '▶'
key k
plain | grep '▶'
```

Expected: the first grep shows `▶ Thinking (1 line)  [>]` (row 4), the second `▶ ## Assistant · 10:00:05 · ↑10,000 ↓500` (row 3).

## 3. Expand a tool call into the detail panel

```bash
start 120 40
key j j j j j
plain | grep '▶'
key Enter
plain
```

Expected: the grep shows `▶ Read /src/auth.py → 84 lines  [>]` (row 6). After Enter the right panel shows `Read: /src/auth.py`, `84 lines`, then the output `def authenticate():`, `    pass`, `# 84 lines total`.

## 4. Panel switch

Continue from scenario 3.

```bash
key Tab
borders
plain | tail -1
key Tab
borders
plain | grep '▶'
```

Expected:

- After the first Tab, `borders` prints `38;2;105;105;105m` then `38;2;30;144;255m`: the detail panel is now dodgerblue and the conversation panel dimgray. The footer starts with `tab Panel: left`.
- After the second Tab, `borders` prints `38;2;30;144;255m` then `38;2;105;105;105m` again, and focus is back on `▶ Read /src/auth.py → 84 lines  [>]`.

## 5. Visibility cycle

```bash
key h
plain
key h
plain
key h
plain | tail -1
```

Expected:

- First `h`: the footer shows `h Show: messages only`. The conversation keeps message headers and text but has no `Thinking` row and no tool rows.
- Second `h`: the footer shows `h Show: user + tools`. Only user headers and text plus the two tool rows remain: `Read /src/auth.py → 84 lines  [>]` and `✘ Bash Run tests → FAILED (exit 1)  [>]`. No `## Assistant` headers.
- Third `h`: the footer shows `h Show: all`.

## 6. Search

```bash
start 120 40
key /
tmux -L "$S" send-keys -t tui -l jwt
key Enter
plain | grep '▶'
key n
plain | grep '▶'
key N
plain | grep '▶'
```

Expected: the search bar closes and the matches are focused in turn: `▶ Focus on JWT validation` (row 8), then `▶ I'll look at JWT handling.` (row 10), then row 8 again.

Then a query with no visible match. Tool output (`result_full`) is not searchable, so `error` finds nothing in this fixture:

```bash
key /
tmux -L "$S" send-keys -t tui -l error
key Enter
plain | tail -4
key Escape
plain | grep '▶'
```

Expected: the search bar stays open with the border title `(0 results for 'error')`. Esc closes it and focus returns to `▶ ## User · 10:00:00`.

## 7. Help

```bash
key '?'
plain
```

Expected: the right panel shows `Keybindings` and lists, among others, `n / N         Next / previous search match` and `q, Ctrl+C     Quit` (long lines wrap inside the panel).

## 8. Small terminal

```bash
start 60 20
plain
```

Expected: both panels and the footer still render at 60x20. Long lines wrap inside the conversation panel (for example `Messages: 4 · Tools: 2 (1 x) ·` then `$0.04`), and there are no stray escape sequences or overlapping text.

## 9. Quit

```bash
key q
sleep 0.5
tmux -L "$S" has-session -t tui 2>/dev/null && echo still running || echo exited
```

Expected: `exited`. The TUI quit, so its tmux session closed.

## Cleanup

```bash
tmux -L "$S" kill-server 2>/dev/null
rm -rf "$OUT"
```
