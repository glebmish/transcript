# Workflow: record a TUI demo

Goal: produce a GIF or still that *shows off* a feature or flow well — for a README, an issue reply, a chat message, or a release note.

This is a presentation task, not a reproduction task. The watcher's attention is the scarce resource; the artifact has to justify theirs.

## Principles

- **One thing per demo.** A demo that shows three features shows none. Pick a single clear arc (open a file → search for something → see the result) and cut everything else.
- **Start from a clean state.** No stale detail panel, no leftover focus from exploration. Kill and relaunch the session fresh so the first frame is obviously the starting point.
- **Pace for humans.** 200 ms between keys is fast for automation; for a demo, 500–800 ms between meaningful actions gives the viewer time to see what changed. Insert an extra 1–2 s pause before anything visually surprising lands.
- **End with the payoff visible.** The last frame is what a mobile viewer sees if the GIF doesn't auto-play. Make it the answer, not the transition.
- **No annotations during the flow.** Animated annotations distract from the UI. If you need callouts, put them in a static "this is what you're about to see" still that precedes the GIF, or in the prose next to it.
- **Keep it short.** Under 10 seconds, ideally 4–6. Every extra frame is attention you're spending without buying.

## Standard shape

1. **Plan the arc.** Write down the 3–5 actions the viewer will see. If you can't summarise the demo in one sentence, it's too broad — split it.
2. **Boot deterministically.** `tui-session` `new-session`. Use the same size (default 120×40) across demos in the same project so they compose visually.
3. **Warm-up frame.** Let the initial render settle, then pause 1 s with nothing happening. This gives the first frame breathing room.
4. **Drive the arc.** Use `tui-interact`'s `send()` helper with explicit longer sleeps between logical steps, not just between keys:

   ```bash
   send /             ; sleep 0.6
   send -l 'query'    ; sleep 0.8
   send Enter         ; sleep 1.2   # let the result land and settle
   ```

5. **Capture.** Use `tui-record` start/stop. Default the encode delay (`-d 20`) for snappy playback; for demos with fewer frames you can go higher (`-d 40–60`) to slow playback.
6. **Review before sharing.** Read the GIF, watch it play in an image viewer. Check: does it loop cleanly? Is the first frame self-explanatory? Is the final frame the payoff?
7. **Wrap with context.** In the message, include: a one-sentence description of what the viewer is about to see, the GIF URL, and (optionally) the key schedule for anyone reproducing.

## Presenting the GIF well

- **Static preview** (chat, tool output) shows one frame only. Pick the frame that best communicates the feature for that preview — ideally the final state, not mid-transition. Use `magick input.gif[N] frame.png` to extract a specific frame as a still thumbnail next to the animated URL.
- **Link + thumbnail** is stronger than just a link. The thumbnail gives the mobile reader the payoff before deciding to open the full animation.
- **Caption what the reader should notice.** "Watch how the footer updates when the mode cycles" tells the viewer where to look; "here's a GIF" doesn't.

## When to use a still instead

- Single-state feature (a new panel, a new column, a styling change) — a still is simpler, faster to make, and mobile-friendlier.
- Flow is boring (e.g. a spinner animation) — the still of the end state tells the story.

## When to use a GIF

- The *transition* is the feature (smooth scroll, incremental search highlighting, animated border).
- Sequence of steps where the order is the point (onboarding, search→select→action).

## Common failure modes

- **Demo shows exploration, not a feature** — script, don't improvise. The viewer doesn't care that you had to hit `h` twice to find the right mode.
- **Too fast, can't follow** — you optimised for brevity over legibility. Add `sleep`s between logical actions.
- **Background motion** — spinners, cursor blinks, timestamps that update during the recording. Either wait for them to stabilise or crop them out.
- **Ends mid-action** — the GIF loops with the viewer left staring at a transition frame. Always stop on a settled state.
