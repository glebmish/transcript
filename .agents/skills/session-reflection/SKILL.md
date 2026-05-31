---
name: session-reflection
description: Use when the user asks about token usage, cost, latency, tool-call history, subagent cost, or context-window utilization of the current Codex session. Returns opaque JSON summaries — never dumps the raw transcript.
---

Run `python3 ${CLAUDE_SKILL_DIR}/reflect.py <command>`. The `CLAUDE_SESSION_ID` env var is populated at skill invocation, so `--session-id` is normally not needed.

All output is JSON on stdout.

## Commands

**`context`** — current context-window utilization.
Returns `{used, ceiling, pct}`.

**`cost-message [--offset N]`** — one assistant message (default: last, `offset=-1`).
Returns `{input, output, cache_read, cache_create_5m, cache_create_1h, cost_usd, latency_ms, stop_reason, tool_calls, ts}`.

**`cost-turn [--offset N]`** — all assistant work for the Nth-from-last user prompt.
Same shape as `cost-message` plus `assistant_messages` count.

**`subagents`** — per-subagent tokens, cost, wall time, returned size, status.
Returns `{subagents: [...], totals: {count, cost_usd, wall_ms}}`.

**`tools [filters]`** — per-tool-call records, sorted by timestamp ascending.
Each row: `{ts, turn, tool, args, success, tokens_in, tokens_out, latency_ms, hook_overhead_ms, truncated}`.

Filters (all optional, AND-combined):
- `--tool Bash`
- `--args-contains 'git'`
- `--success true|false`
- `--latency-gt-ms 1000`
- `--tokens-gt 5000`
- `--turn-gte -5`

## Override flags

- `--session-id <uuid>` — inspect a different session (e.g. a prior one in the same cwd).
- `--cwd <path>` — inspect a session from a different project directory.
