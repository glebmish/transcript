---
name: tui-record
description: Use when you want to record a running tmux TUI session as an animated GIF (a sequence of deduplicated frames). Covers start (spawn a background poller), stop (kill poller, encode as GIF), and hand-off to `tui-share` for upload. Use instead of a single `ansi-to-image` capture whenever the thing you want to show is a flow, not a still.
---

# Recording a TUI session as an animated GIF

Recording spans two calls: **start** spawns a background poller that samples the tmux pane every 200 ms and keeps only distinct frames; **stop** kills the poller, appends one final frame, and encodes the accumulated frames as a GIF. The two calls share state under `/tmp/tui-gif/$REC_LABEL/` — treat that directory as skill-internal; the only identifier you need to carry across the calls is `$REC_LABEL`.

## When to use

- You want to show a *flow* (keybinding sequence, animation, demo) as a GIF, not a still.
- The tmux session is already running headless (see `tui-session`) at a known size.
- Next step after stop will be `tui-share` to upload the GIF and paste a URL in chat.

Do **not** use for static screenshots — that's what `tui-share` does directly from a single ANSI capture.

## Prerequisites

- tmux session alive under the Claude-session-derived name `tui-$SID_SHORT` (see `tui-session`).
- You know the session's row count (the `-y` you passed to `new-session`; default 40).
- `textimg` on PATH. Install: `go install github.com/jiro4989/textimg/v3@latest`.
- JetBrainsMono Nerd Font installed at `~/Library/Fonts/JetBrainsMonoNerdFont-Regular.ttf`. Install: `brew install --cask font-jetbrains-mono-nerd-font`.

---

## The contract

1. Derive `$REC_LABEL` from the Claude session id (see "Naming" below). Use the **same label** for start and stop.
2. Run the **start** block.
3. Drive the TUI (use `tui-interact` — send keys, wait).
4. Run the **stop** block with the same label. Stop prints the GIF path.
5. Verify the GIF (see "Sanity checks"), then hand the path to `tui-share`.

The poll interval (`sleep 0.2` in start) and the encode delay (`-d 20` in stop) must stay in sync. Both are set to 200 ms in the scripts below — if you change one, change the other.

### Naming: derive from the Claude session id

Don't invent ad-hoc recording labels. Obtain the Claude session id (invoke `get-session-id` if needed), then:

```bash
SID_SHORT=${SID:0:8}                    # e.g. 01234567
REC_LABEL=$SID_SHORT                    # single recording in this conversation
# OR, if you need to distinguish multiple recordings in the same conversation:
REC_LABEL=$SID_SHORT-scroll-demo        # session-id prefix + short slug
```

This guarantees start/stop matching (both calls derive the same value from the same session id) and means `ls /tmp/tui-gif/` groups all recordings from one conversation together.

---

## Start: spawn the background frame poller

```bash
TMUX_SESSION=tui-$SID_SHORT             # the tmux session name (from tui-session)
REC_LABEL=$SID_SHORT                    # (or $SID_SHORT-<slug> for multi-recording)
ROWS=40                                 # match the tmux session's rows
W=/tmp/tui-gif/$REC_LABEL
mkdir -p "$W"
: > "$W/frames.ansi"
: > "$W/last-hash"
printf '%s\n' "$ROWS" > "$W/rows"
printf '%s\n' "$TMUX_SESSION" > "$W/session"

( while tmux has-session -t "$TMUX_SESSION" 2>/dev/null; do
    frame=$(tmux capture-pane -t "$TMUX_SESSION" -e -p 2>/dev/null)
    [ -z "$frame" ] && { sleep 0.2; continue; }
    h=$(printf '%s' "$frame" | md5 -q)
    if [ "$h" != "$(cat "$W/last-hash" 2>/dev/null)" ]; then
      printf '%s\n' "$frame" >> "$W/frames.ansi"
      printf '%s' "$h" > "$W/last-hash"
    fi
    sleep 0.2
  done
) </dev/null >/dev/null 2>&1 &
disown
echo $! > "$W/poller.pid"
```

### Why each part matters

- **`while tmux has-session` guard** — the poller auto-exits if the tmux session dies, so no runaway background process leaks.
- **`</dev/null >/dev/null 2>&1`** — detaches stdio from the Bash tool's shell so the poller survives after the command returns.
- **`disown`** — prevents the shell from sending SIGHUP to the background job on exit.
- **`md5 -q`** — macOS. On Linux replace with `md5sum | cut -d' ' -f1`.
- **State files** (`rows`, `session`, `last-hash`, `poller.pid`, `frames.ansi`) are consumed by stop. You don't interact with them directly.

Dedup via `last-hash` is critical — without it, a static screen produces dozens of identical frames and bloats the GIF.

---

## Stop: kill the poller and encode

```bash
REC_LABEL=$SID_SHORT                    # same value used in start
W=/tmp/tui-gif/$REC_LABEL
FONT=~/Library/Fonts/JetBrainsMonoNerdFont-Regular.ttf
ROWS=$(cat "$W/rows")
TMUX_SESSION=$(cat "$W/session")

# 1. Stop the poller.
if [ -f "$W/poller.pid" ]; then
  kill "$(cat "$W/poller.pid")" 2>/dev/null
  rm -f "$W/poller.pid"
fi

# 2. Append one final frame if distinct — guarantees the terminal state is in the GIF.
final=$(tmux capture-pane -t "$TMUX_SESSION" -e -p 2>/dev/null)
if [ -n "$final" ]; then
  h=$(printf '%s' "$final" | md5 -q)
  if [ "$h" != "$(cat "$W/last-hash" 2>/dev/null)" ]; then
    printf '%s\n' "$final" >> "$W/frames.ansi"
  fi
fi

# 3. Encode as animated GIF.
textimg -a \
        -f "$FONT" \
        -l "$ROWS" \
        -d 20 \
        -o "$W/recording.gif" \
        < "$W/frames.ansi"

echo "$W/recording.gif"
```

- `-d 20` — animation delay in centiseconds (0.2 s per frame), matching the 200 ms poll interval.
- `-l "$ROWS"` — every `ROWS` consecutive lines of input = one frame. Because `capture-pane` on a `ROWS`-tall pane always emits exactly `ROWS` lines, the boundary is clean.

Output path: `/tmp/tui-gif/$REC_LABEL/recording.gif`. Hand it to `tui-share`.

---

## End-to-end example

```bash
SID_SHORT=01234567                      # from get-session-id
# Session tui-01234567 already running at 40 rows.
# start recording (REC_LABEL defaults to $SID_SHORT)
# (run the start block with TMUX_SESSION=tui-$SID_SHORT, REC_LABEL=$SID_SHORT, ROWS=40)

# drive the TUI
for i in 1 2 3 4 5 6 7 8; do
  tmux send-keys -t tui-$SID_SHORT j
  sleep 0.15
done

# stop and encode
# (run the stop block with REC_LABEL=$SID_SHORT — prints GIF path)

# verify, then hand to tui-share for upload
```

---

## Sanity checks (before handing to tui-share)

Verification is mandatory — `superpowers:verification-before-completion` applies before uploading.

```bash
file "$W/recording.gif"       # should say "GIF image data"
ls -lh "$W/recording.gif"     # KB-MB typical, not tens of MB
echo "frames: $(( $(wc -l < "$W/frames.ansi") / $(cat "$W/rows") ))"
```

Then Read the GIF with your image tool to confirm it actually animates the expected content. Common failures caught by inspection:

- **Single-frame GIF (no animation)** — dedup was too aggressive (screen didn't change enough) or the recording captured only one settled state. Re-record with deliberate intermediate inputs.
- **Wrong session captured** — the poller grabbed a different tmux session than intended. Check the `session` state file matches what you meant.
- **Frames out of order or missing expected transitions** — the poll interval was slower than the transition. Drop both `sleep 0.2` in start and `-d 20` in stop to `sleep 0.05` / `-d 5` and re-record.
- **Tens of MB** — dedup isn't working (check `last-hash` is being written), or recorded for too long on an active UI.

---

## Cleanup

`/tmp/tui-gif/$REC_LABEL/` persists after stop. Reboot clears `/tmp`, or prune manually:

```bash
rm -rf /tmp/tui-gif/$REC_LABEL
# or prune everything from this conversation:
rm -rf /tmp/tui-gif/$SID_SHORT*
```

---

## Pitfalls

- **Start/stop label mismatch** — if you derive `$REC_LABEL` from `$SID_SHORT` both times, this is impossible by construction. If you instead hand-typed a label, reuse the exact string verbatim; `ls /tmp/tui-gif/` shows existing directories.
- **Second start with same label** overwrites state and orphans the previous poller. When recording multiple flows in one conversation, append a slug: `REC_LABEL=$SID_SHORT-<slug>`. Otherwise explicitly stop first.
- **Stop without prior start** — no PID file, no frames. The script handles missing PID gracefully but textimg fails with empty input. Always pair start/stop.
- **tmux session died mid-recording** — the poller's `while has-session` guard exits cleanly; the final-frame capture produces nothing. Encoded GIF covers everything up to the session's death, which is usually what you want.
- **Poll/delay drift** — if you lowered `sleep 0.2` to `0.05` in start but left `-d 20` in stop, playback is 4× slower than real time. Change both together.
- **Very fast animations** (<200 ms per transition) may miss frames. Drop `sleep 0.2` to `0.05` and `-d 20` to `-d 5` together.
- **Background process survival** depends on both `disown` and the stdio detach in start. If you simplify the script and drop either, the poller may die when the Bash tool call returns.
