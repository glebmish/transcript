---
name: tui-workflows
description: Use when doing a multi-step task around a TUI that combines session lifecycle, interaction, capture, and sharing — reproducing a bug, comparing behaviour before/after a fix, or producing a demo recording. Points at the right per-task skills (tui-session, tui-interact, tui-share, tui-record) and orders them for the current goal.
---

# TUI workflows

Dispatcher for common multi-step TUI jobs. The per-task skills (`tui-session`, `tui-interact`, `tui-share`, `tui-record`) stay thin; this skill tells you *which to call in what order for what goal*. Load the branch that matches your task.

## Branches

- [`repro-bug.md`](repro-bug.md) — you saw a bug and need a shareable, annotated artifact (still PNG or GIF) that someone else can act on.
- [`before-after.md`](before-after.md) — you applied a fix and need to verify it visually, with before/after captures and a byte-level diff backstop.
- [`record-demo.md`](record-demo.md) — you want to show off a flow or feature as a GIF for a writeup, issue, or chat message.

All three share the same base setup:

1. **Session id** — `get-session-id` skill (or reuse `$SID` if already known). Every artifact in this conversation is named off `$SID_SHORT`.
2. **Tmux session** — see `tui-session` for `new-session`. Default 120×40 unless the bug is size-dependent.
3. **Driving** — see `tui-interact` for `send-keys` / capture. **Use the `send()` helper with 100 ms between keys**; burst send drops keystrokes.

## When not to use this skill

- One-off "show the user this one screen" — just capture and hand to `tui-share` directly, no workflow needed.
- Exploration with no specific goal — spin up a session, poke around with `tui-interact`, decide what's interesting. Don't over-structure.
- Automated regression suites / CI-style baselines — out of scope here; belongs in the project's test infrastructure.
