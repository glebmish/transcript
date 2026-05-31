# Workflow: repro a TUI bug into a shareable artifact

Goal: convert "I saw X misbehave" into a named PNG or GIF with annotations, uploaded to a durable URL, plus the minimal steps for someone else to reproduce.

## Economics of verification (read first)

Screenshots and GIFs are the expensive end of the evidence stack. Before capturing pixels, burn through cheaper signals first — in this order:

1. **Read the relevant code.** Grep for the symptom, read 50 lines around it. Often the bug is obvious at source and the "capture" is only to confirm.
2. **Run existing tests.** If the area has tests, their pass/fail state is the cheapest signal you'll ever get. A pass when the bug is visible in the TUI is itself a finding — coverage gap.
3. **Add / extend a test that catches the bug.** A failing unit test is a better artifact than a screenshot for anything that's purely a logic or parsing issue — it's self-checking, diff-able, and runs in CI. Fix the test, then re-check the TUI to confirm the visible symptom is gone.
4. **Only then capture the TUI** — for things that truly live in rendering, focus, styling, or interactive behaviour. Test-first is not a virtue signal; it's a token- and time-saver.

**Explicit-ask override.** If the user asked for visuals (e.g. "capture and share repro pics"), you ship visuals. Tests first is the default when nobody specified; when the user specified, honour the ask.

## Standard shape

For a given bug:

1. **Decide the artifact type.**
   - Single settled state (a wrong label, a missing glyph, a broken layout) → still PNG.
   - Sequence or transition (keystroke → render change that's wrong) → GIF via `tui-record`.
   - Pure logic / data-shape issue with no interesting UI → not this workflow — write a test and point at the failing assertion. Ship the test diff, not a screenshot of the TUI.

2. **Spin up the TUI deterministically.** Use `tui-session` `new-session` at a specific size. If your bug needs an unusual size (narrow, very wide), encode it in the repro.

3. **Drive to the bug state.** Use `tui-interact`'s `send()` helper, sleep between keys, capture at key transitions. Keep captures to ANSI files named by the key state (`01-initial.ansi`, `02-after-search.ansi`, etc.) so the flow is inspectable later.

4. **Render + annotate.**
   - Still: `tui-share` step 1 → widen canvas recipe → `annotate.md`.
   - GIF: `tui-record` start → drive → stop → `magick ... -coalesce` with fixed annotations per `annotate.md`.
   - Compose summaries of non-TUI context (fixture excerpts, CLI output) into the same render using the ANSI-composite recipe in `tui-share`.

5. **Verify the artifact before uploading.** Read the rendered file with your image tool. Confirm the annotation lands on the claimed target. For GIFs, remember that a static preview only shows one frame — explicitly note "GIF animates at the URL" in chat.

6. **Upload** via `tui-share` step 4. Tag with `$SID_SHORT` and `tui-share` so cleanup is one command later.

7. **Write down the repro.** In whatever file the user reads bugs from (`docs/bugs.md`, an issue tracker, a PR description), include: severity, root cause pointer (file:line), a fix sketch, and the artifact URL. The URL is evidence; the written summary is what someone acts on.

## When to ship a minimal synthetic fixture

Applicable mainly to parser / data-shape bugs where "see for yourself in the TUI" is indirect. A 4-line JSONL fixture that makes the parser produce the wrong output is a great companion artifact. It is **not a substitute for a screenshot when the user asked for visuals** — ship both.

## Common failure modes

- **Capturing before the TUI settled** — see `tui-interact` waiting strategies. If your screenshot shows a half-drawn frame, you didn't wait.
- **Annotation pointing at empty sky** — computed coordinates from eyeballing instead of grep. See `annotate.md` "locate, draw, verify".
- **Claiming a GIF is animated** when the static preview only shows one frame. The animation is at the Cloudinary URL; say so explicitly.
- **Skipping the repro write-up** and shipping only URLs. The user can't grep URLs. Always include a text summary.
