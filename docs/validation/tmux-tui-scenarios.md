# TUI validation scenarios — Phase 0

## For the validating agent: read this first

You are validating whether driving a TUI via raw tmux commands is ergonomic enough that a dedicated CLI wrapper (Phase 1) is unnecessary. Work through the eight scenarios below in order, then write a synthesis report.

### Environment

- Repo: `<repo-root>`.
- transcript CLI: `.venv/bin/transcript view <file>` launches the TUI. (Bare `transcript <file>` prints markdown — not what you want.)
- Always set tmux's working directory with `-c <repo-root>` so `.venv/bin/transcript` resolves.
- Fixture: `tests/fixtures/claude_minimal.jsonl` (contains tool_use blocks for scenario 3).

### Ground rules

1. **Only use tmux commands documented in the `tmux-tui-*` skills.** No custom wrapper scripts, no helper functions, no shortcuts. Every tmux interaction is an explicit `tmux` invocation in a `Bash` tool call. Friction must be real and visible.
2. **Capture observations during execution.** For each scenario, note: did it pass, how many tmux calls it took, any retries, the approximate token cost of captures, and any specific friction (timing issues, wrong command, unclear output).
3. **Do not synthesize during execution.** Keep observations in your working memory or a scratch note. The final report is written only after all scenarios are complete.
4. **Clean up between scenarios.** Kill the tui session at the end of each scenario unless the next scenario reuses it.

### After all scenarios: write the report

Write the synthesis report to `docs/validation/phase-0-report.md` using the template at the bottom of this file.

---

## Scenario 1 — Startup and initial capture

**Preconditions:** No `tui-transcript` session exists. `tests/fixtures/claude_minimal.jsonl` is present.

**Commands:**

```bash
tmux new-session -d -s tui-transcript \
  -c <repo-root> -x 120 -y 40 \
  '.venv/bin/transcript view tests/fixtures/claude_minimal.jsonl'
sleep 1
tmux capture-pane -t tui-transcript -e -p
```

**Expected observation:** Styled capture shows the transcript TUI — a header, a left conversation panel containing messages, a right detail panel (likely empty), and a footer. One block in the conversation panel has an ANSI blue border (`\e[38;2;30;144;255m` or similar — `dodgerblue`). The inactive panel has a gray (`dimgray`) border.

**Record:** Pass/fail. Whether the initial sleep was sufficient or had to be extended. Token cost of the styled capture. Whether the active border was distinguishable in raw ANSI.

---

## Scenario 2 — Block navigation

**Preconditions:** `tui-transcript` session from scenario 1 is alive, or restart via scenario 1 commands.

**Commands:**

```bash
tmux send-keys -t tui-transcript j
sleep 0.15
tmux send-keys -t tui-transcript j
sleep 0.15
tmux send-keys -t tui-transcript j
sleep 0.3
tmux capture-pane -t tui-transcript -p
```

**Expected observation:** The plain capture shows the conversation panel with a different block highlighted than in scenario 1 — the focus has moved down by three positions. The exact block content depends on the fixture, but the cursor/focus indicator should have shifted.

**Record:** Pass/fail. How you determined the focus moved three positions from plain text alone (vs. needing styled capture). Any observed key drops.

---

## Scenario 3 — Expand tool call into detail panel

**Preconditions:** `tui-transcript` session from scenario 1/2 is alive.

Navigate to a `ToolCallWidget` block. The fixture `claude_minimal.jsonl` contains tool uses; press `j` until focus lands on one (inspect captures to confirm). Then press Enter.

**Commands (template — adjust j-count based on your captures):**

```bash
# Reset to top by restarting
tmux kill-session -t tui-transcript 2>/dev/null
tmux new-session -d -s tui-transcript \
  -c <repo-root> -x 120 -y 40 \
  '.venv/bin/transcript view tests/fixtures/claude_minimal.jsonl'
sleep 1
# Press j until focus is on a tool call (inspect after each press)
tmux send-keys -t tui-transcript j
sleep 0.15
tmux capture-pane -t tui-transcript -p | head -30
# ... iterate j + capture until a ToolCallWidget is focused ...
tmux send-keys -t tui-transcript Enter
sleep 0.3
tmux capture-pane -t tui-transcript -p
```

**Expected observation:** After Enter, the right-hand detail panel is no longer empty — it shows the tool call's name (e.g., "Read"), its input (e.g., file path), and potentially its output.

**Record:** Pass/fail. How many j-presses were needed to find a tool call, and whether identifying "this block is a tool call" from plain text was easy or required styled capture. Token cost of the iterative inspection.

---

## Scenario 4 — Panel focus switch

**Preconditions:** `tui-transcript` session alive, conversation panel active (blue border on left).

**Commands:**

```bash
tmux send-keys -t tui-transcript Tab
sleep 0.2
tmux capture-pane -t tui-transcript -e -p
```

**Expected observation:** Styled capture shows the active (blue) border on the right-hand detail panel, and the left panel's border is now gray.

**Record:** Pass/fail. Whether the border-color change was visible in the ANSI output and how you matched it (grep, eyeballing). If plain capture was sufficient to detect the switch from any text cue (e.g., a label change), note that too.

---

## Scenario 5 — Visibility cycle

**Preconditions:** `tui-transcript` session alive.

**Commands:**

```bash
tmux send-keys -t tui-transcript h
sleep 0.2
tmux send-keys -t tui-transcript h
sleep 0.2
tmux capture-pane -t tui-transcript -p
```

**Expected observation:** Plain capture footer contains `Show: user + tools`. The conversation panel shows fewer blocks than scenario 1 (hidden entries).

**Record:** Pass/fail. Whether footer grep (`grep 'Show: user + tools'`) worked cleanly. Block count change detection method.

---

## Scenario 6 — Search flow

**Preconditions:** `tui-transcript` session alive.

**Commands:**

```bash
tmux send-keys -t tui-transcript /
sleep 0.2
tmux send-keys -t tui-transcript -l 'error'
tmux send-keys -t tui-transcript Enter
sleep 0.3
tmux capture-pane -t tui-transcript -p
```

**Expected observation:** A block containing the text "error" is now focused. The search bar has closed (no visible input field at the bottom).

**Record:** Pass/fail. Whether the focused block actually contains "error" (grep for it in the capture and confirm proximity to focus indicator). Any timing issues with `-l 'error'` followed by `Enter`.

---

## Scenario 7 (stress) — Small terminal

**Preconditions:** No tui-transcript session.

**Commands:**

```bash
tmux kill-session -t tui-transcript 2>/dev/null
tmux new-session -d -s tui-transcript \
  -c <repo-root> -x 60 -y 20 \
  '.venv/bin/transcript view tests/fixtures/claude_minimal.jsonl'
sleep 1
tmux capture-pane -t tui-transcript -p
```

**Expected observation:** The TUI adapts to 60×20. Either both panels fit (narrow but functional), or the layout collapses (one panel only, or a "terminal too small" message). No broken rendering (overlapping text, garbage characters).

**Record:** Pass/fail (where "fail" = visibly broken rendering, not "layout is tight"). What actually happened — does Textual handle 60×20 gracefully? Any artifacts.

---

## Scenario 8 (stress) — Styled capture for color assertion

**Preconditions:** `tui-transcript` session at 120×40 (restart if needed).

**Goal:** Prove that styled capture is necessary (or not) by asserting something that plain capture cannot: the active panel's border is blue and the inactive is gray.

**Commands:**

```bash
tmux kill-session -t tui-transcript 2>/dev/null
tmux new-session -d -s tui-transcript \
  -c <repo-root> -x 120 -y 40 \
  '.venv/bin/transcript view tests/fixtures/claude_minimal.jsonl'
sleep 1
# Plain — try to distinguish active vs inactive border
tmux capture-pane -t tui-transcript -p > /tmp/plain.txt
# Styled — same question
tmux capture-pane -t tui-transcript -e -p > /tmp/styled.txt
```

Then inspect both:

- In plain: can you tell which panel is active? Likely not — borders are just `│` and `─` characters.
- In styled: the active border's color code (`dodgerblue`/`38;2;30;144;255`) should appear around the left panel, and `dimgray`/`38;2;105;105;105` around the right.

**Record:** Pass/fail. Whether plain capture was sufficient (if yes, styled capture may not be justifying its token cost in general). Approximate token counts for both files (`wc -c /tmp/plain.txt /tmp/styled.txt`).

---

## Cleanup

```bash
tmux kill-session -t tui-transcript 2>/dev/null
```

---

## Report template

Write your synthesis to `docs/validation/phase-0-report.md` using this template:

```markdown
# Phase 0 validation report

**Date:** <YYYY-MM-DD>
**Transcript commit:** <git rev-parse HEAD>
**Skills commit:** <git rev-parse HEAD for .claude/skills/>

## Results

| # | Scenario                      | Result | Note                              |
| - | ----------------------------- | ------ | --------------------------------- |
| 1 | Startup & initial capture     | PASS   | —                                 |
| 2 | Block navigation              | ...    | ...                               |
| 3 | Expand tool call into detail  | ...    | ...                               |
| 4 | Panel focus switch            | ...    | ...                               |
| 5 | Visibility cycle              | ...    | ...                               |
| 6 | Search flow                   | ...    | ...                               |
| 7 | Small terminal (stress)       | ...    | ...                               |
| 8 | Styled capture (stress)       | ...    | ...                               |

(Use PASS / PARTIAL / FAIL.)

## Friction observed

Top 3–5 concrete pain points. For each:

- What happened
- How often it came up across scenarios
- What a tool wrapper would have made easier

## Recommendation

One of: **BUILD** / **IMPROVE-SKILL** / **STOP**.

Two to three sentences of rationale. If BUILD, name the one or two features from the parent spec that would most address the friction. If IMPROVE-SKILL, name the specific skills and what's missing. If STOP, state what convinced you the raw workflow is enough.
```
