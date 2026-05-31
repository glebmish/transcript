# Workflow: before/after visual verification of a fix

Goal: confirm that a fix actually changed the rendered output in the way you intend, and produce a side-by-side artifact to prove it.

## Standard shape

1. **Start with the byte diff, not the image.** Capture the "before" ANSI once before touching code:

   ```bash
   tmux capture-pane -t tui-$SID_SHORT -e -p > /tmp/before.ansi
   ```

   After the fix and a re-render, capture "after":

   ```bash
   tmux capture-pane -t tui-$SID_SHORT -e -p > /tmp/after.ansi
   diff /tmp/before.ansi /tmp/after.ansi | head -80
   ```

   - **Empty diff** — the rendered pane didn't change. Either the fix is in non-visual code (then don't claim a visual fix), or the TUI didn't reload the edited source (restart with `tui-session` respawn-pane), or you captured at the wrong moment. Investigate before rendering any image.
   - **Diff exists** — read it. Confirm the changed bytes match the improvement you intended. Only then move to rendering.

   This pre-image diff step catches the most common self-deception: "the fix seemed to work, the screenshot looks different, ship it" when actually the difference is unrelated (a scrollbar, a timestamp, a focus change).

2. **Reload the TUI between captures.** Source edits don't hot-reload into a running TUI. After changing code:

   ```bash
   tmux respawn-pane -k -t tui-$SID_SHORT '<same command>'
   sleep 1
   # drive to the same state used for "before", then capture
   ```

   Use the same key sequence for both captures — anything that differs between before/after that isn't the fix pollutes the comparison.

3. **Render side-by-side.** Build a composite PNG:

   ```bash
   textimg -f "$FONT" -o /tmp/before.png < /tmp/before.ansi
   textimg -f "$FONT" -o /tmp/after.png  < /tmp/after.ansi
   magick /tmp/before.png /tmp/after.png +append /tmp/compare.png
   ```

   `+append` stacks horizontally (use `-append` for vertical). Add headers with the ANSI-composite recipe in `tui-share` if the captures alone don't convey which is which.

4. **Annotate only the changed regions.** Use the `diff` output to pick coordinates — annotating regions that didn't change is dishonest. The rule: one annotated rectangle per genuine diff hunk, not per "thing you hoped would change".

5. **Upload and link from the fix commit / PR.** Pair the artifact URL with the test that backs it up (there is one, right?). The image shows the symptom; the test prevents regression.

## When before/after is the wrong format

- **The fix is purely logical** (parser, data transform) — a failing test that now passes is better than any image. Ship the test diff.
- **Both states are visually subtle** (single-char colour change, 1px offset) — a crop diff (`magick compose -compose difference` then thresholded) is clearer than side-by-side captures.
- **The "before" was never captured** — don't reconstruct it. Either you have a deterministic repro of the pre-fix state (capture that fresh before applying the fix in a clean worktree) or you don't. A claimed-from-memory "before" is not evidence.

## Common failure modes

- **Byte-identical captures but an annotated "after" image** — you didn't verify the bytes changed before annotating. The annotation is a lie.
- **Captures at different states** — typo in the key sequence between runs, or focus landed in a different block. Rerun both with a scripted identical key sequence.
- **Stale TUI process** — forgot to `respawn-pane`. The old, unfixed binary is what's rendering.
