#!/usr/bin/env python3
"""Opaque reflection tools over a Claude Code session transcript.

Commands:
  context                       current context-window utilization
  cost-message [--offset N]     cost of one assistant message (negative offset = from end)
  cost-turn    [--offset N]     cost of all assistant work for one user turn
  subagents                     per-subagent token/cost/timing
  tools [filters...]            per-tool-call records, sorted by ts asc

All numbers are returned as JSON to stdout. Model identity is used internally
for pricing and context-ceiling lookup but is not surfaced.
"""

import argparse
import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECTS_DIR = Path.home() / ".claude" / "projects"

# USD per million tokens: (input, output, cache_create_5m, cache_create_1h, cache_read).
# Approximate Claude 4-family rates; adjust as needed.
_PRICING = {
    "claude-opus-4-7":       (15.0, 75.0, 18.75, 30.0, 1.50),
    "claude-opus-4-7[1m]":   (15.0, 75.0, 18.75, 30.0, 1.50),
    "claude-sonnet-4-6":     (3.0,  15.0, 3.75,  6.0,  0.30),
    "claude-sonnet-4-6[1m]": (3.0,  15.0, 3.75,  6.0,  0.30),
    "claude-haiku-4-5":      (1.0,  5.0,  1.25,  2.0,  0.10),
}
_DEFAULT_RATES = _PRICING["claude-opus-4-7"]

_CEILING_OVERRIDE = {
    "claude-opus-4-7": 1_000_000,  # 4.7 is always 1M
}


def _ceiling(model: str) -> int:
    if model in _CEILING_OVERRIDE:
        return _CEILING_OVERRIDE[model]
    if model.endswith("[1m]"):  # explicit 1M variant of older models
        return 1_000_000
    return 200_000


# ---------- file discovery ----------

def _session_path(session_id: Optional[str], cwd: Optional[str]) -> Path:
    sid = session_id or os.environ.get("CLAUDE_SESSION_ID")
    if not sid:
        raise SystemExit(
            "error: session id required. Set CLAUDE_SESSION_ID or pass --session-id"
        )
    cwd_abs = Path(cwd or os.getcwd()).resolve()
    pdir = PROJECTS_DIR / str(cwd_abs).replace("/", "-")
    p = pdir / f"{sid}.jsonl"
    if not p.exists():
        raise SystemExit(f"error: session transcript not found at {p}")
    return p


def _load(jsonl: Path) -> list[dict]:
    return [json.loads(l) for l in jsonl.read_text().splitlines() if l.strip()]


# ---------- helpers ----------

def _dedup_assistant(entries: list[dict]) -> list[dict]:
    """Keep the last entry per message.id (handles streaming-duplicate writes)."""
    by_id: dict[str, int] = {}
    out: list[dict] = []
    for e in entries:
        if e.get("type") != "assistant":
            continue
        mid = e["message"].get("id")
        if mid in by_id:
            out[by_id[mid]] = e
        else:
            by_id[mid] = len(out)
            out.append(e)
    return out


def _cost_usd(model: str, u: dict) -> float:
    inp, out, cc5, cc1, cr = _PRICING.get(model, _DEFAULT_RATES)
    cc = u.get("cache_creation", {}) or {}
    return (
        u.get("input_tokens", 0)               * inp / 1e6 +
        u.get("output_tokens", 0)              * out / 1e6 +
        cc.get("ephemeral_5m_input_tokens", 0) * cc5 / 1e6 +
        cc.get("ephemeral_1h_input_tokens", 0) * cc1 / 1e6 +
        u.get("cache_read_input_tokens", 0)    * cr  / 1e6
    )


def _msg_summary(e: dict) -> dict:
    msg = e["message"]
    u = msg.get("usage", {}) or {}
    cc = u.get("cache_creation", {}) or {}
    return {
        "input": u.get("input_tokens", 0),
        "output": u.get("output_tokens", 0),
        "cache_read": u.get("cache_read_input_tokens", 0),
        "cache_create_5m": cc.get("ephemeral_5m_input_tokens", 0),
        "cache_create_1h": cc.get("ephemeral_1h_input_tokens", 0),
        "cost_usd": round(_cost_usd(msg.get("model", ""), u), 6),
        "stop_reason": msg.get("stop_reason"),
        "tool_calls": [
            c.get("name") for c in msg.get("content", [])
            if c.get("type") == "tool_use"
        ],
        "ts": e.get("timestamp"),
    }


def _is_real_user_turn(e: dict) -> bool:
    """User entry that's an actual prompt, not a wrapper around tool_results."""
    if e.get("type") != "user":
        return False
    c = e["message"].get("content")
    if isinstance(c, str):
        return True
    if isinstance(c, list):
        return any(b.get("type") != "tool_result" for b in c)
    return False


def _parse_ts(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _ms_between(a: Optional[str], b: Optional[str]) -> Optional[int]:
    ta, tb = _parse_ts(a), _parse_ts(b)
    if ta is None or tb is None:
        return None
    return int((tb - ta).total_seconds() * 1000)


# ---------- public commands ----------

def context(session_id=None, cwd=None) -> dict:
    asst = _dedup_assistant(_load(_session_path(session_id, cwd)))
    if not asst:
        return {"used": 0, "ceiling": 0, "pct": 0.0}
    msg = asst[-1]["message"]
    u = msg.get("usage", {}) or {}
    used = (
        u.get("input_tokens", 0)
        + u.get("cache_creation_input_tokens", 0)
        + u.get("cache_read_input_tokens", 0)
    )
    ceiling = _ceiling(msg.get("model", ""))
    return {"used": used, "ceiling": ceiling, "pct": round(100 * used / ceiling, 2)}


def cost_message(offset: int = -1, session_id=None, cwd=None) -> dict:
    entries = _load(_session_path(session_id, cwd))
    asst = _dedup_assistant(entries)
    if not asst or abs(offset) > len(asst):
        return {}
    e = asst[offset]
    s = _msg_summary(e)
    # latency = gap between this assistant entry and the prior user/assistant entry
    idx = entries.index(e)
    prior_ts = next(
        (entries[i].get("timestamp") for i in range(idx - 1, -1, -1)
         if entries[i].get("type") in ("user", "assistant") and entries[i].get("timestamp")),
        None,
    )
    s["latency_ms"] = _ms_between(prior_ts, e.get("timestamp"))
    return s


def cost_turn(offset: int = -1, session_id=None, cwd=None) -> dict:
    entries = _load(_session_path(session_id, cwd))
    user_idxs = [i for i, e in enumerate(entries) if _is_real_user_turn(e)]
    if not user_idxs or abs(offset) > len(user_idxs):
        return {}
    pos = len(user_idxs) + offset if offset < 0 else offset
    start = user_idxs[pos]
    end = user_idxs[pos + 1] if pos + 1 < len(user_idxs) else len(entries)
    span_asst = _dedup_assistant(entries[start:end])
    totals = {
        "input": 0, "output": 0, "cache_read": 0,
        "cache_create_5m": 0, "cache_create_1h": 0,
        "cost_usd": 0.0, "tool_calls": [],
    }
    for e in span_asst:
        s = _msg_summary(e)
        for k in ("input", "output", "cache_read", "cache_create_5m", "cache_create_1h"):
            totals[k] += s[k]
        totals["cost_usd"] += s["cost_usd"]
        totals["tool_calls"].extend(s["tool_calls"])
    totals["cost_usd"] = round(totals["cost_usd"], 6)
    totals["assistant_messages"] = len(span_asst)
    return totals


def _result_size(tool_use_id: str, inline_content, session_dir: Path) -> tuple[int, bool]:
    """(approx_tokens, truncated_to_disk)."""
    spill = session_dir / "tool-results" / f"{tool_use_id}.txt"
    if spill.exists():
        return spill.stat().st_size // 4, True
    if inline_content is None:
        return 0, False
    if isinstance(inline_content, str):
        return len(inline_content) // 4, False
    if isinstance(inline_content, list):
        return sum(
            (len(json.dumps(c)) if isinstance(c, dict) else len(str(c)))
            for c in inline_content
        ) // 4, False
    return len(str(inline_content)) // 4, False


def tool_calls(
    session_id=None, cwd=None,
    tool: Optional[str] = None,
    args_contains: Optional[str] = None,
    success: Optional[bool] = None,
    latency_gt_ms: Optional[int] = None,
    tokens_gt: Optional[int] = None,
    turn_gte: Optional[int] = None,
) -> list[dict]:
    spath = _session_path(session_id, cwd)
    entries = _load(spath)
    sdir = spath.parent / spath.stem  # subagents/, tool-results/ live here

    # Map tool_use_id -> (inline_content, is_error, ts)
    results: dict[str, tuple] = {}
    for e in entries:
        if e.get("type") != "user":
            continue
        c = e["message"].get("content")
        if not isinstance(c, list):
            continue
        for b in c:
            if b.get("type") == "tool_result":
                results[b["tool_use_id"]] = (
                    b.get("content"),
                    bool(b.get("is_error")),
                    e.get("timestamp"),
                )

    # Hook overhead per tool_use_id
    hook_ms: dict[str, int] = defaultdict(int)
    for e in entries:
        if e.get("type") == "attachment":
            a = e["attachment"]
            if a.get("type") == "hook_success" and a.get("toolUseID"):
                hook_ms[a["toolUseID"]] += a.get("durationMs", 0) or 0

    # Track current user-turn index as we walk
    total_user_turns = sum(1 for e in entries if _is_real_user_turn(e))
    rows: list[dict] = []
    user_seen = 0
    for e in entries:
        if _is_real_user_turn(e):
            user_seen += 1
        if e.get("type") != "assistant":
            continue
        ats = e.get("timestamp")
        for c in e["message"].get("content", []):
            if c.get("type") != "tool_use":
                continue
            tid = c["id"]
            inline, is_err, rts = results.get(tid, (None, False, None))
            tokens_out, truncated = _result_size(tid, inline, sdir)
            tokens_in = len(json.dumps(c.get("input", {}))) // 4
            turn_off = -(total_user_turns - user_seen + 1) if user_seen else None
            rows.append({
                "ts": ats,
                "turn": turn_off,
                "tool": c.get("name"),
                "args": c.get("input"),
                "success": (tid in results) and (not is_err),
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "latency_ms": _ms_between(ats, rts),
                "hook_overhead_ms": hook_ms.get(tid, 0),
                "truncated": truncated,
            })

    def keep(r: dict) -> bool:
        if tool and r["tool"] != tool: return False
        if args_contains and args_contains not in json.dumps(r["args"]): return False
        if success is not None and r["success"] != success: return False
        if latency_gt_ms is not None and (r["latency_ms"] or 0) <= latency_gt_ms: return False
        if tokens_gt is not None and r["tokens_out"] <= tokens_gt: return False
        if turn_gte is not None and (r["turn"] is None or r["turn"] < turn_gte): return False
        return True

    rows = [r for r in rows if keep(r)]
    rows.sort(key=lambda r: r["ts"] or "")
    return rows


def subagents(session_id=None, cwd=None) -> dict:
    spath = _session_path(session_id, cwd)
    sdir = spath.parent / spath.stem / "subagents"
    main = _load(spath)

    # Dispatching Task/Agent tool_uses, with the user-turn they were dispatched in
    dispatches = []
    user_seen = 0
    for e in main:
        if _is_real_user_turn(e):
            user_seen += 1
        if e.get("type") != "assistant":
            continue
        for c in e["message"].get("content", []):
            if c.get("type") == "tool_use" and c.get("name") in ("Task", "Agent"):
                dispatches.append({
                    "tool_use_id": c["id"],
                    "description": (c.get("input") or {}).get("description", ""),
                    "dispatch_turn": user_seen,
                })
    total_user_turns = user_seen

    completed = {
        b.get("tool_use_id")
        for e in main if e.get("type") == "user" and isinstance(e["message"].get("content"), list)
        for b in e["message"]["content"] if b.get("type") == "tool_result"
    }

    out: list[dict] = []
    if sdir.exists():
        used_dispatch_ids: set[str] = set()
        for meta in sorted(sdir.glob("*.meta.json")):
            agent_filename = meta.stem.replace(".meta", "")  # "agent-<id>"
            agent_id = agent_filename.replace("agent-", "")
            meta_data = json.loads(meta.read_text())
            jsonl = sdir / f"{agent_filename}.jsonl"

            tokens_in = tokens_out = cc5 = cc1 = cr = 0
            cost = 0.0
            returned_chars = 0
            wall_ms = 0
            if jsonl.exists():
                sub_asst = _dedup_assistant(_load(jsonl))
                ts_first = ts_last = None
                for se in sub_asst:
                    u = se["message"].get("usage", {}) or {}
                    tokens_in += u.get("input_tokens", 0)
                    tokens_out += u.get("output_tokens", 0)
                    cr += u.get("cache_read_input_tokens", 0)
                    ccc = u.get("cache_creation", {}) or {}
                    cc5 += ccc.get("ephemeral_5m_input_tokens", 0)
                    cc1 += ccc.get("ephemeral_1h_input_tokens", 0)
                    cost += _cost_usd(se["message"].get("model", ""), u)
                    t = se.get("timestamp")
                    if t:
                        ts_first = ts_first or t
                        ts_last = t
                if sub_asst:
                    for c in sub_asst[-1]["message"].get("content", []):
                        if c.get("type") == "text":
                            returned_chars += len(c.get("text", ""))
                wall_ms = _ms_between(ts_first, ts_last) or 0

            # Match dispatch by description; prefer one not yet claimed
            match = next(
                (d for d in dispatches
                 if d["description"] == meta_data.get("description")
                 and d["tool_use_id"] not in used_dispatch_ids),
                None,
            )
            if match:
                used_dispatch_ids.add(match["tool_use_id"])

            status = (
                "done" if (match and match["tool_use_id"] in completed)
                else "running" if match
                else "unknown"
            )
            out.append({
                "agent_id": agent_id,
                "agent_type": meta_data.get("agentType"),
                "description": meta_data.get("description"),
                "dispatch_turn": (
                    -(total_user_turns - match["dispatch_turn"] + 1)
                    if match else None
                ),
                "status": status,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cache_read": cr,
                "cache_create_5m": cc5,
                "cache_create_1h": cc1,
                "cost_usd": round(cost, 6),
                "wall_ms": wall_ms,
                "returned_chars": returned_chars,
            })

    return {
        "subagents": out,
        "totals": {
            "count": len(out),
            "cost_usd": round(sum(s["cost_usd"] for s in out), 6),
            "wall_ms": sum(s["wall_ms"] for s in out),
        },
    }


# ---------- CLI ----------

def _emit(obj):
    print(json.dumps(obj, indent=2))


def main():
    p = argparse.ArgumentParser(prog="reflect")
    p.add_argument("--session-id")
    p.add_argument("--cwd")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("context")

    cm = sub.add_parser("cost-message")
    cm.add_argument("--offset", type=int, default=-1)

    ct = sub.add_parser("cost-turn")
    ct.add_argument("--offset", type=int, default=-1)

    sub.add_parser("subagents")

    tc = sub.add_parser("tools")
    tc.add_argument("--tool")
    tc.add_argument("--args-contains")
    tc.add_argument("--success", type=lambda x: x.lower() in ("1", "true", "yes"))
    tc.add_argument("--latency-gt-ms", type=int)
    tc.add_argument("--tokens-gt", type=int)
    tc.add_argument("--turn-gte", type=int)

    args = p.parse_args()
    common = {"session_id": args.session_id, "cwd": args.cwd}

    if args.cmd == "context":
        _emit(context(**common))
    elif args.cmd == "cost-message":
        _emit(cost_message(args.offset, **common))
    elif args.cmd == "cost-turn":
        _emit(cost_turn(args.offset, **common))
    elif args.cmd == "subagents":
        _emit(subagents(**common))
    elif args.cmd == "tools":
        _emit(tool_calls(
            tool=args.tool,
            args_contains=args.args_contains,
            success=args.success,
            latency_gt_ms=args.latency_gt_ms,
            tokens_gt=args.tokens_gt,
            turn_gte=args.turn_gte,
            **common,
        ))


if __name__ == "__main__":
    main()
