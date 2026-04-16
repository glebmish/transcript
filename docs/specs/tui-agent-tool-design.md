# TUI Agent Tool — Design Spec

**Date:** 2026-04-16
**Status:** Draft

## Problem

AI coding agents (Claude Code, Codex, etc.) can drive browsers via browser-use tools but have no equivalent for terminal UI applications. When developing a TUI, the agent cannot see what it looks like, interact with it, or verify visual correctness. The feedback loop is broken — the agent writes code blind and relies on the developer to report what they see.

## Goal

A CLI tool that gives AI agents the ability to start any TUI application, see its rendered screen (with style/color information), send input, and observe the results — enabling a visual feedback loop for TUI development, testing, and debugging.

## Phased Approach

### Phase 0: Validate with a skill (no tool)

Before building anything, write a Claude Code skill that teaches the agent to use raw tmux commands for TUI interaction:

```bash
tmux new-session -d -s tui-test -x 120 -y 40 "python app.py"
sleep 1
tmux capture-pane -t tui-test -e -p        # styled capture
tmux send-keys -t tui-test j                # send input
sleep 0.3
tmux capture-pane -t tui-test -e -p        # see what changed
tmux kill-session -t tui-test
```

Use this skill for real TUI development work on the transcript project. Track:
- How often the visual feedback changed the agent's output vs. code-only reasoning
- Whether `sleep`-based waiting is sufficient or causes real problems
- Whether the raw ANSI output is useful or too noisy
- Which use cases actually arise (layout verification, glitch debugging, size testing, etc.)

**Gate:** Only proceed to Phase 1 if the skill proves genuinely useful and the raw tmux workflow has friction that justifies a wrapper.

### Phase 1: Go CLI wrapper over tmux

A thin Go CLI wrapper over tmux. tmux handles all the hard problems (PTY allocation, terminal emulation, screen capture, session management) and has been battle-tested for 15+ years. The CLI provides a clean, agent-friendly interface on top.

### Why tmux as the engine

- **Proven** — 15+ years, handles every terminal edge case, every TUI framework
- **Universal** — installed or trivially installable on every Linux/macOS system
- **Full terminal emulation** — alternate screen buffer, true color, wide characters, all VT sequences
- **Style capture** — `capture-pane -e` preserves ANSI escape sequences (colors, bold, underline, etc.)
- **Configurable size** — `new-session -x N -y N`, `resize-window -x N -y N` at runtime
- **Visible mode for free** — `split-window`, `attach-session` are native tmux concepts
- **No daemon needed** — tmux server manages its own lifecycle
- **No native compilation** — no node-pty, no C++ addons, no build toolchain issues

### Why a Go single binary

- Zero runtime dependencies beyond tmux itself
- Trivial cross-compilation for Linux/macOS
- Excellent CLI library support (cobra)
- Native JSON marshaling
- ~1,500-2,500 LOC for the full tool (CLI, tmux integration, wait/record, dirty tracking, visible mode adapters)

## Architecture

```
┌──────────────────────────────┐
│  tui-agent CLI (Go)          │
│  - arg parsing (cobra)       │
│  - output formatting         │
│  - dirty diff logic          │
│  - session tracking          │
│  - key name translation      │
└────────┬─────────────────────┘
         │ os/exec
         ▼
┌──────────────────────────────┐
│  tmux                        │
│  - PTY management            │
│  - terminal emulation        │
│  - screen capture            │
│  - session lifecycle         │
│  - split panes (visible)     │
│  - pipe-pane (PTY event tap) │
└──────────┬───────────────────┘
           │ pipe-pane
           ▼
┌──────────────────────────────┐
│  FIFO (/tmp/tui-agent-*.fifo)│
│  - raw PTY output stream     │
│  - read by wait command      │
│  - read by record daemon     │
└──────────────────────────────┘
```

Each CLI invocation shells out to tmux for actions (send-keys, capture-pane, etc.). Session state lives in tmux's server (which manages its own lifecycle automatically).

For event-driven smart wait and frame recording, the tool uses `tmux pipe-pane` to subscribe to PTY output events. On `start`, the CLI sets up a FIFO:

```
tmux pipe-pane -t <session> "cat > /tmp/tui-agent-<id>.fifo"
```

A long-lived watcher goroutine reads the FIFO. Any bytes arriving mean the screen is actively changing. This enables debounce-based settling detection without polling `capture-pane` in a tight loop.

## tmux command mapping

| CLI command | tmux equivalent |
|---|---|
| `start <cmd> --cols 120 --rows 40` | `new-session -d -s <id> -x 120 -y 40 <cmd>` |
| `snapshot --color` | `capture-pane -t <id> -e -p -S - -E -` |
| `snapshot` (plain) | `capture-pane -t <id> -p -S - -E -` |
| `press <key>` | `send-keys -t <id> <key>` |
| `type <text>` | `send-keys -t <id> -l <text>` |
| `resize --cols N --rows N` | `resize-window -t <id> -x N -y N` |
| `wait` | watch FIFO for PTY silence (debounce), then `capture-pane` to confirm |
| `wait --text <pattern>` | on each FIFO settle, `capture-pane` + regex match |
| `kill` | `kill-session -t <id>` |
| `list` | `list-sessions -F "#{session_name} #{session_created}"` |
| `info` | `display-message -t <id> -p` with format strings |

### Key mapping

tmux `send-keys` accepts key names directly: `Enter`, `Escape`, `Up`, `Down`, `Left`, `Right`, `Tab`, `BSpace`, `C-c`, `C-d`, `F1`-`F12`, etc. The CLI translates a few aliases for convenience:

| CLI key name | tmux send-keys |
|---|---|
| `enter` | `Enter` |
| `escape`, `esc` | `Escape` |
| `backspace` | `BSpace` |
| `ctrl+c` | `C-c` |
| `ctrl+d` | `C-d` |
| `up`, `down`, `left`, `right` | `Up`, `Down`, `Left`, `Right` |
| `tab` | `Tab` |
| `f1`-`f12` | `F1`-`F12` |
| `space` | `Space` |

Any unrecognized key name is passed through to tmux as-is.

## Features

### 1. Smart wait (event-driven via pipe-pane)

On `start`, the CLI creates a FIFO and attaches it to the tmux pane's output:

```bash
mkfifo /tmp/tui-agent-<id>.fifo
tmux pipe-pane -t <session> "cat > /tmp/tui-agent-<id>.fifo"
```

The `wait` command opens the FIFO and watches for activity:

```go
func wait(fifoPath, sessionID string, timeout, debounce time.Duration, pattern *regexp.Regexp) error {
    f, _ := os.Open(fifoPath)
    defer f.Close()
    buf := make([]byte, 4096)
    deadline := time.Now().Add(timeout)
    timer := time.NewTimer(debounce)

    for time.Now().Before(deadline) {
        f.SetReadDeadline(time.Now().Add(10 * time.Millisecond))
        n, _ := f.Read(buf)
        if n > 0 {
            timer.Reset(debounce) // activity — reset debounce
            continue
        }
        select {
        case <-timer.C:
            // PTY has been silent for `debounce` duration — screen settled
            if pattern != nil {
                screen := capturePane(sessionID)
                if pattern.MatchString(screen) {
                    return nil
                }
                timer.Reset(debounce) // not matched yet, keep waiting
                continue
            }
            return nil
        default:
        }
    }
    return ErrTimeout
}
```

This is truly event-driven — no polling `capture-pane` in a loop. The FIFO receives bytes the instant the TUI writes to its PTY. The debounce timer fires only after real silence.

Default: 100ms debounce, 5s timeout. Configurable via `--debounce` and `--timeout`.

**Fallback:** If the FIFO is unavailable (e.g., pipe-pane failed), fall back to poll-based wait (capture-pane + hash comparison at 50ms intervals).

### 2. Dirty tracking

The CLI caches the last snapshot per session (in a temp file or XDG_RUNTIME_DIR). On `snapshot --dirty`:

1. Capture current screen
2. Load last cached screen
3. Diff line-by-line
4. Output only changed lines with line numbers
5. Cache current screen for next call

```
$ tui-agent snapshot --dirty
[3]  ▶ Message 5: Can you fix the bug?
[4]    Message 6: Sure, let me look...
[17] Status: 6/42 messages
```

This dramatically reduces tokens when the agent is navigating — most of the screen is static, only the cursor/selection line and status bar change.

### 3. Frame recording

```
$ tui-agent record start
$ tui-agent press j
$ tui-agent press j
$ tui-agent press j
$ tui-agent record stop --format json
```

`record start` spawns a background process (same binary, internal `_record-daemon` subcommand) that watches the FIFO for PTY activity. Each time a render burst settles (debounce fires), it calls `capture-pane` and stores the timestamped snapshot. This captures exactly one frame per visual change — no blind polling.

`record stop` signals the background process to dump collected frames and exit.

Output:

```json
{
  "frames": [
    { "timestamp_ms": 0, "screen": "..." },
    { "timestamp_ms": 87, "screen": "..." },
    { "timestamp_ms": 162, "screen": "..." }
  ]
}
```

For dirty recording (`record start --dirty`), only changed lines per frame are stored (diffed against previous frame).

The FIFO-based approach means recording has near-zero overhead when the screen is idle — no CPU spent on capture-pane calls until something actually changes.

### 4. Two operating modes

#### Headless mode (default)

Always uses tmux. Sessions are created detached (`-d`). The tmux server starts automatically in the background — invisible to the user. All interaction (snapshot, send-keys, wait, record) goes through tmux.

tmux is a hard dependency. It is the only multiplexer that supports all required capabilities: headless sessions, ANSI-styled capture, absolute resize, pipe-pane for PTY event streaming, and cross-platform support (Linux, macOS).

```
tui-agent start "vim main.go" --cols 120 --rows 40
tui-agent snapshot --color
tui-agent press i
tui-agent type "hello world"
tui-agent press Escape
tui-agent wait
tui-agent snapshot --dirty --color
tui-agent kill
```

#### Visible/demo mode

Displays the TUI in a split pane inside the user's current multiplexer so they can watch the agent work. For demos and collaborative debugging.

```
tui-agent start "vim main.go" --visible
tui-agent start "vim main.go" --visible --multiplexer zellij
```

The headless tmux session still does all the real work (capture, wait, record). The visible pane is independently managed by the user's multiplexer — tmux is an invisible implementation detail. The tool opens a new pane in the user's multiplexer that shows the same underlying TUI. This means:

- All agent interaction goes through the headless tmux session (consistent behavior)
- The visible pane is purely a presentation concern — the user's multiplexer handles it natively
- No tmux UI (status bar, key bindings) leaks into the visible experience

The visible-mode adapter is minimal:

```go
type VisibleAdapter interface {
    Split(cmd string) (paneID string, err error)
    Close(paneID string) error
}
```

Built-in adapters and auto-detection:

| Multiplexer | Detection | Split command |
|---|---|---|
| tmux | `$TMUX` set | `tmux split-window -h <cmd>` |
| zellij | `$ZELLIJ` set | `zellij action new-pane -d right -- <cmd>` |
| cmux | cmux CLI available | `cmux new-split right -- <cmd>` |

If `--multiplexer` is not specified, detect from environment variables (`$TMUX`, `$ZELLIJ`). If none found and `--visible` requested, error with a clear message.

**Key constraints:**
- Headless mode requires tmux (hard dependency).
- Visible mode requires any supported multiplexer (optional).
- The visible pane is read-only — all interaction goes through the headless tmux session.

### 5. Output formats and token economics

Capture modes serve different purposes with different token costs:

| Method | Tokens (120x40) | Best for |
|---|---|---|
| Plain text | ~1,200-1,500 | Text search, pattern matching, diffing |
| Text + ANSI styles | ~3,000-5,000 | Focus/selection state, color-dependent logic |
| Dirty tracking (text) | ~200-800 | Incremental updates, token-efficient iteration |
| PNG screenshot | ~1,000-1,500 | Full visual fidelity, layout verification |

**Key insight:** Screenshots are cheaper than styled text capture and carry full visual fidelity. But they're opaque — can't be searched, diffed, or dirty-tracked. The tool should support both, used for different questions:

- **Text capture** for "what text is on screen?", "did this line change?", "find this pattern"
- **Screenshots** for "what does this look like?", "is the layout correct?", "are the colors right?"

Format flags:

```
--format pretty    # default: bordered text with header/footer
--format plain     # raw captured text, no decoration
--format json      # structured JSON with metadata
--format png       # screenshot as PNG image
```

The `--color` flag is orthogonal to text formats — controls whether ANSI escape sequences are preserved. Not applicable to `--format png`.

**Screenshot implementation:** Render ANSI capture to an image. Options include piping `capture-pane -e` through an ANSI-to-image renderer (e.g., a Go library or `aha` + headless browser). The exact approach is an implementation detail — what matters is that `snapshot --format png` produces a file path the agent can read with its image tools.

JSON output example:

```json
{
  "session": "tui-abc123",
  "cols": 120,
  "rows": 40,
  "screen": "...",
  "color": true,
  "timestamp": "2026-04-16T14:30:00Z"
}
```

### 6. Process lifecycle

When the TUI app exits:

- The session remains alive (tmux `remain-on-exit` option). This avoids losing the final screen state.
- `snapshot` continues to work — returns the last rendered screen.
- `info` reports the process as exited, including the exit code.
- `wait` resolves immediately if the process is already dead.
- `press`/`type`/`paste` return an error ("process exited").
- `kill` cleans up the session and all associated resources (FIFO, cache files).

The agent can detect exit by checking `info` or by `wait` returning immediately after a command.

### 7. Session management

Sessions are named with a prefix: `tui-agent-<label>` or `tui-agent-<random>`. This avoids collisions with the user's own tmux sessions. `list` filters to only tui-agent sessions. `kill --all` cleans up all tui-agent sessions.

## CLI Interface

```
tui-agent start <cmd> [--cols N] [--rows N] [--cwd DIR] [--label NAME]
                      [--visible] [--multiplexer NAME]
tui-agent snapshot [--color] [--dirty] [--format json|pretty|plain|png]
tui-agent wait [--timeout MS] [--text PATTERN] [--debounce MS]
tui-agent type <text>
tui-agent press <key>...
tui-agent paste <text>
tui-agent find <pattern> [--color]
tui-agent resize --cols N --rows N
tui-agent record start [--interval MS] [--dirty]
tui-agent record stop [--format json|pretty]
tui-agent list [--format json|pretty]
tui-agent info [--format json|pretty]
tui-agent kill [--all]
tui-agent session <id>          # switch active session context
```

Global flags: `--session <id>` (override active session), `--json` (shorthand for `--format json`).

## Integration: Claude Code Skill

Two skills, one per phase:

### Phase 0 skill (`using-tmux-for-tui`)

Teaches the agent the raw tmux workflow. No tool dependency. Includes:
- Session creation with size control
- `capture-pane -e -p` for styled capture
- `send-keys` for input with key name reference
- Sleep-based waiting (the simplest thing that works)
- Cleanup patterns

This skill is the validation vehicle. If it's useful, we build the tool. If not, we stop.

### Phase 1 skill (`using-tui-agent`)

Teaches the agent the CLI tool workflow:

1. **When to use it** — developing/debugging TUI apps, verifying visual changes, testing keyboard navigation
2. **The workflow pattern:**
   - Start the TUI at a reasonable size
   - `snapshot --format png` for initial visual overview (cheapest way to see the full picture)
   - `snapshot --color` when you need to search/match text content
   - Send input, wait for settle, snapshot again
   - Use `--dirty` for efficient incremental updates after the initial capture
   - Use `record` when debugging animations or transitions
   - Use `resize` to test responsive layouts
3. **Token management:**
   - Use PNG screenshots (~1k tokens) for visual verification
   - Use plain text (~1.2k tokens) for text search and pattern matching
   - Use `--dirty` (~200-800 tokens) for incremental updates
   - Avoid styled text (~3-5k tokens) unless you specifically need ANSI color information
4. **When to use visible mode** — when the user wants to watch, or for demos

## Non-Goals

- **Framework-specific testing** — this is not a Textual Pilot replacement. It works at the PTY level, not the widget level. Framework-specific tools are complementary.
- **CI visual regression** — while you could use this for snapshot testing, that's not the primary use case. Tools like pytest-textual-snapshot are better for that.
- **Mouse interaction** — TUI apps used from agents should be keyboard-driven. Mouse support may be added later but is not in scope.
- **Remote sessions** — the tool and tmux run on the same machine. No SSH/remote PTY forwarding.
- **Replacing tmux** — this is explicitly a wrapper, not a reimplementation. If tmux can do it, we shell out to tmux.

## Open Questions

1. **Name** — `tui-agent`? `tui-pilot`? `termview`? `tuictl`?
2. **MCP server** — ship an MCP server wrapper alongside the CLI? Low effort given the CLI exists, and would allow direct tool-use integration without a skill.

## Dependencies

- **tmux** — the only runtime dependency
- **Go standard library** — `os/exec`, `encoding/json`, `regexp`, `crypto/sha256`
- **cobra** — CLI framework (compiled into the binary)

## Success Criteria

1. Agent can start any TUI app headlessly, see its styled screen, send keys, and observe changes
2. Agent can test the same TUI at multiple terminal sizes without restarting
3. Agent can capture frame sequences to debug visual transitions
4. User can optionally watch the agent drive the TUI in a split pane
5. Token usage for screen capture is reasonable (dirty tracking, plain format)
6. Works on Linux and macOS
7. Single binary install, no runtime dependencies beyond tmux

## Prior Art

Evaluated during design:

- **tui-use** (onesuper) — TypeScript, headless xterm.js + node-pty daemon. Right interface, wrong engine (native compilation pain, unnecessary complexity for what tmux gives you for free). Our CLI interface is modeled on tui-use's.
- **agent-tui** (pproenca) — Rust, wezterm fork, 39k LOC hexagonal architecture. Overengineered for the problem. Good WebSocket live preview concept.
- **tmux-mcp** (nickgnd, MediocreTriumph) — MCP servers wrapping tmux. Validated the tmux-as-engine approach. No smart wait, no dirty tracking, no frame recording.
- **pyte** — Python virtual terminal emulator. Good per-cell style API but lacks alternate screen buffer support. tmux's terminal emulation is more complete.
