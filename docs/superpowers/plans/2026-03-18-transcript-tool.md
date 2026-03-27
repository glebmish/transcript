# Transcript Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single-file Python script that converts Claude Code (JSONL) and Gemini CLI (JSON) agent logs into compact, readable Markdown transcripts.

**Architecture:** Single file `transcript.py` with three sections: Claude parser, Gemini parser, Markdown renderer. Both parsers produce a common intermediate message format consumed by the renderer. CLI uses argparse with `--format` flag and optional `-o` output.

**Tech Stack:** Python 3.10+, standard library only (json, argparse, datetime, sys, dataclasses)

**Spec:** `docs/superpowers/specs/2026-03-18-transcript-tool-design.md`

**Test data:**
- Claude: `~/.claude/projects/<project>/<session>.jsonl`
- Gemini: `~/projects/<project>/chats/session-<timestamp>.json`

---

### Task 1: Data model and cost estimation

**Files:**
- Create: `transcript.py`
- Create: `tests/test_transcript.py`

- [ ] **Step 1: Write test for pricing lookup**

```python
# tests/test_transcript.py
from transcript import estimate_cost, PRICING

def test_exact_model_cost():
    cost = estimate_cost("claude-opus-4-6", tokens_in=1000000, tokens_out=1000000)
    assert cost == 15.00 + 75.00

def test_prefix_match_cost():
    cost = estimate_cost("claude-opus-4-6-20250618", tokens_in=1000000, tokens_out=0)
    assert cost == 15.00

def test_unknown_model_cost():
    cost = estimate_cost("unknown-model", tokens_in=1000, tokens_out=1000)
    assert cost is None

def test_gemini_cost():
    cost = estimate_cost("gemini-3-flash-preview", tokens_in=1000000, tokens_out=1000000)
    assert cost == 0.15 + 0.60
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd <repo-root> && python -m pytest tests/test_transcript.py -v`
Expected: FAIL — `transcript` module doesn't exist

- [ ] **Step 3: Write data model and pricing**

```python
# transcript.py
"""Convert agent conversation logs to readable Markdown transcripts."""

import json
import sys
import argparse
from dataclasses import dataclass, field
from datetime import datetime

# (input_price, output_price) per 1M tokens in USD
PRICING = {
    "claude-opus-4-6":        (15.00, 75.00),
    "claude-sonnet-4-6":      (3.00,  15.00),
    "claude-haiku-4-5":       (0.80,   4.00),
    "gemini-2.5-pro":         (1.25,  10.00),
    "gemini-2.5-flash":       (0.15,   0.60),
    "gemini-3-flash-preview": (0.15,   0.60),
}


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float | None:
    """Estimate cost in USD. Returns None if model is unknown."""
    for prefix, (in_price, out_price) in PRICING.items():
        if model == prefix or model.startswith(prefix):
            return tokens_in / 1_000_000 * in_price + tokens_out / 1_000_000 * out_price
    return None


@dataclass
class ToolCall:
    name: str
    summary: str       # key param, e.g. file path or command
    result: str        # compact result, e.g. "84 lines"
    passed: bool


@dataclass
class Message:
    role: str          # "user" or "assistant"
    timestamp: datetime
    model: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    thinking: list[str] = field(default_factory=list)
    text: list[str] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd <repo-root> && python -m pytest tests/test_transcript.py -v`
Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add transcript.py tests/test_transcript.py
git commit -m "feat: add data model and cost estimation"
```

---

### Task 2: Claude Code parser

**Files:**
- Modify: `transcript.py`
- Modify: `tests/test_transcript.py`

**Key parsing details (from real log analysis):**
- Claude JSONL has **one content block per JSONL line**. An assistant "turn" is split across multiple lines (thinking, text, tool_use — each its own line). These must be merged into a single `Message`.
- A new user text message (not a `tool_result`) signals the end of the previous assistant turn.
- `tool_use` lines (type=assistant) are followed by `tool_result` lines (type=user with `toolUseResult`). Match them by position.
- `toolUseResult` is a `dict` on success (keys vary by tool: `file`, `filenames`, `bytes`, etc.) or a `str` on error.
- `is_error: True` on `tool_result` content block indicates failure.
- `message.usage` has `input_tokens` and `output_tokens` but is repeated on every assistant line in a turn — only count once per turn.
- `message.content` can be a plain string (user text) or an array of content blocks.

- [ ] **Step 1: Write test for Claude parser using real log file**

```python
# Add to tests/test_transcript.py
from transcript import parse_claude

def test_parse_claude_real():
    """Parse a real Claude log and check basic structure."""
    msgs = parse_claude(
        "~/.claude/projects/"
        "<project>/"
        "<session>.jsonl"
    )
    assert len(msgs) > 0
    # First message should be from user
    assert msgs[0].role == "user"
    assert len(msgs[0].text) > 0
    # Should have at least one assistant message with tool calls
    assistant_msgs = [m for m in msgs if m.role == "assistant"]
    assert len(assistant_msgs) > 0
    has_tools = any(m.tool_calls for m in assistant_msgs)
    assert has_tools
    # Check a tool call has required fields
    for m in assistant_msgs:
        for tc in m.tool_calls:
            assert tc.name
            assert tc.result
            assert isinstance(tc.passed, bool)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd <repo-root> && python -m pytest tests/test_transcript.py::test_parse_claude_real -v`
Expected: FAIL — `parse_claude` not defined

- [ ] **Step 3: Implement Claude parser**

Add to `transcript.py`:

```python
def _claude_tool_summary(name: str, input_data: dict) -> str:
    """Extract key param from a Claude tool_use input."""
    if name in ("Read", "Write", "Edit"):
        return input_data.get("file_path", "?")
    if name == "Bash":
        return input_data.get("description") or (input_data.get("command", "?")[:80])
    if name == "Grep":
        pat = input_data.get("pattern", "?")
        path = input_data.get("path", "")
        return f"{pat} in {path}" if path else pat
    if name == "Glob":
        return input_data.get("pattern", "?")
    if name in ("WebFetch", "WebSearch"):
        return input_data.get("url") or input_data.get("query") or "?"
    # Unknown tool: first string value
    for v in input_data.values():
        if isinstance(v, str) and v:
            return v[:80]
    return "?"


def _claude_tool_result(tool_use_result) -> tuple[str, bool]:
    """Extract compact result string and pass/fail from toolUseResult."""
    if isinstance(tool_use_result, str):
        # Error case — toolUseResult is an error string
        short = tool_use_result.split("\n")[0][:50]
        return f"FAILED: {short}", False
    if isinstance(tool_use_result, dict):
        # Read tool
        if "file" in tool_use_result:
            f = tool_use_result["file"]
            return f'{f.get("totalLines", "?")} lines', True
        # Glob tool
        if "filenames" in tool_use_result:
            return f'{tool_use_result.get("numFiles", "?")} files', True
        # Grep tool
        if "numMatches" in tool_use_result:
            return f'{tool_use_result["numMatches"]} matches', True
        # WebFetch
        if "url" in tool_use_result:
            code = tool_use_result.get("code", "?")
            return f"HTTP {code}", True
        # Bash — check for exitCode in the result
        if "exitCode" in tool_use_result:
            ec = tool_use_result["exitCode"]
            if ec != 0:
                return f"FAILED (exit {ec})", False
            return "ok", True
    return "ok", True


def parse_claude(path: str) -> list[Message]:
    """Parse a Claude Code JSONL log into a list of Messages."""
    messages: list[Message] = []
    current_assistant: Message | None = None
    pending_tool_uses: list[dict] = []  # tool_use blocks waiting for results
    seen_msg_id: str | None = None  # track assistant message id to avoid double-counting tokens

    with open(path) as f:
        for line_str in f:
            line_str = line_str.strip()
            if not line_str:
                continue
            try:
                entry = json.loads(line_str)
            except json.JSONDecodeError:
                print(f"Warning: skipping malformed line", file=sys.stderr)
                continue

            entry_type = entry.get("type")
            content = entry.get("message", {}).get("content", [])
            timestamp = entry.get("timestamp", "")

            try:
                ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                ts = datetime.min

            if entry_type == "user":
                # Check if this is a tool_result or actual user message
                if isinstance(content, list) and content and isinstance(content[0], dict):
                    block = content[0]
                    if block.get("type") == "tool_result":
                        # Match with pending tool_use
                        is_error = block.get("is_error", False)
                        tool_use_result = entry.get("toolUseResult")
                        if pending_tool_uses:
                            tu = pending_tool_uses.pop(0)
                            summary = _claude_tool_summary(tu["name"], tu.get("input", {}))
                            result_str, passed = _claude_tool_result(tool_use_result)
                            if is_error:
                                passed = False
                                if not result_str.startswith("FAILED"):
                                    result_str = f"FAILED: {result_str}"
                            if current_assistant:
                                current_assistant.tool_calls.append(
                                    ToolCall(name=tu["name"], summary=summary, result=result_str, passed=passed)
                                )
                        continue

                # Actual user message — finalize current assistant
                if current_assistant:
                    messages.append(current_assistant)
                    current_assistant = None
                    pending_tool_uses = []
                    seen_msg_id = None

                text_content = ""
                if isinstance(content, str):
                    text_content = content
                elif isinstance(content, list):
                    text_content = " ".join(
                        b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
                    )
                if text_content.strip():
                    messages.append(Message(role="user", timestamp=ts, text=[text_content.strip()]))

            elif entry_type == "assistant":
                msg = entry.get("message", {})
                model = msg.get("model")
                usage = msg.get("usage", {})
                msg_id = msg.get("id")

                if current_assistant is None:
                    current_assistant = Message(role="assistant", timestamp=ts, model=model)
                    seen_msg_id = None

                # Only count tokens once per assistant API message
                if msg_id and msg_id != seen_msg_id:
                    current_assistant.tokens_in += usage.get("input_tokens", 0)
                    current_assistant.tokens_out += usage.get("output_tokens", 0)
                    if model:
                        current_assistant.model = model
                    seen_msg_id = msg_id

                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        btype = block.get("type")
                        if btype == "thinking":
                            thinking_text = block.get("thinking", "")
                            if thinking_text.strip():
                                current_assistant.thinking.append(thinking_text.strip())
                        elif btype == "text":
                            text = block.get("text", "")
                            if text.strip():
                                current_assistant.text.append(text.strip())
                        elif btype == "tool_use":
                            pending_tool_uses.append(block)

    # Finalize last message
    if current_assistant:
        messages.append(current_assistant)

    return messages
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd <repo-root> && python -m pytest tests/test_transcript.py -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add transcript.py tests/test_transcript.py
git commit -m "feat: add Claude Code JSONL parser"
```

---

### Task 3: Gemini CLI parser

**Files:**
- Modify: `transcript.py`
- Modify: `tests/test_transcript.py`

**Key parsing details (from real log analysis):**
- Single JSON file with top-level `messages[]` array
- Message types: `"user"`, `"gemini"`, `"info"` — skip `"info"` messages
- User `content` is an array of `{text: str}` objects
- Gemini `content` is a plain string
- `thoughts[]` array: use `description` field for blockquotes
- `toolCalls[]` has `name`, `args`, `result`, `status`, `displayName`, `description`, `resultDisplay`
- `status` can be `"success"` even when command fails (exit code != 0) — need to check `result[0].functionResponse.response.output` for `"Exit Code:"` pattern
- `tokens` object: `{input, output, cached, thoughts, tool, total}`
- Tool names differ from Claude: `list_directory`, `run_shell_command`, `read_file`, `write_file`, etc.

- [ ] **Step 1: Write test for Gemini parser using real log file**

```python
# Add to tests/test_transcript.py
from transcript import parse_gemini

def test_parse_gemini_real():
    """Parse a real Gemini log and check basic structure."""
    msgs = parse_gemini(
        "~/projects/<project>/chats/"
        "session-<timestamp>.json"
    )
    assert len(msgs) > 0
    # First non-info message should be from user
    first_user = next(m for m in msgs if m.role == "user")
    assert len(first_user.text) > 0
    # Should have assistant messages with tool calls
    assistant_msgs = [m for m in msgs if m.role == "assistant"]
    assert len(assistant_msgs) > 0
    has_tools = any(m.tool_calls for m in assistant_msgs)
    assert has_tools
    # Should have thinking blocks
    has_thinking = any(m.thinking for m in assistant_msgs)
    assert has_thinking
    # Check model is set
    assert all(m.model for m in assistant_msgs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd <repo-root> && python -m pytest tests/test_transcript.py::test_parse_gemini_real -v`
Expected: FAIL — `parse_gemini` not defined

- [ ] **Step 3: Implement Gemini parser**

Add to `transcript.py`:

```python
def _gemini_tool_summary(name: str, args: dict) -> str:
    """Extract key param from a Gemini tool call."""
    if name in ("read_file", "write_file", "edit_file", "read_many_files"):
        return args.get("file_path") or args.get("path") or args.get("paths", "?")
    if name in ("list_directory",):
        return args.get("dir_path", "?")
    if name == "run_shell_command":
        return args.get("description") or (args.get("command", "?")[:80])
    if name in ("search_files", "grep_search"):
        pat = args.get("pattern") or args.get("query") or "?"
        path = args.get("dir_path") or args.get("path") or ""
        return f"{pat} in {path}" if path else pat
    if name == "glob":
        return args.get("pattern", "?")
    if name in ("web_fetch", "web_search"):
        return args.get("url") or args.get("query") or "?"
    # Unknown: first string value
    for v in args.values():
        if isinstance(v, str) and v:
            return v[:80]
    return "?"


def _gemini_tool_result(tc: dict) -> tuple[str, bool]:
    """Extract compact result and pass/fail from a Gemini toolCall."""
    result_display = tc.get("resultDisplay", "")
    result_data = tc.get("result", [])

    # Try to get the actual output from functionResponse
    output = ""
    if result_data and isinstance(result_data, list):
        fr = result_data[0]
        if isinstance(fr, dict):
            resp = fr.get("functionResponse", {}).get("response", {})
            output = resp.get("output", "")

    # Check for exit code in shell command output
    if "Exit Code:" in output:
        import re
        ec_match = re.search(r"Exit Code:\s*(\d+)", output)
        if ec_match and ec_match.group(1) != "0":
            return f"FAILED (exit {ec_match.group(1)})", False

    # Use resultDisplay if available and short
    if result_display:
        if len(result_display) <= 50 and "\n" not in result_display:
            return result_display, True
        # Count lines
        lines = result_display.strip().split("\n")
        return f"{len(lines)} lines", True

    # Check status field
    status = tc.get("status", "success")
    if status != "success":
        return f"FAILED", False

    return "ok", True


def parse_gemini(path: str) -> list[Message]:
    """Parse a Gemini CLI JSON log into a list of Messages."""
    with open(path) as f:
        data = json.load(f)

    messages: list[Message] = []

    for entry in data.get("messages", []):
        msg_type = entry.get("type")
        timestamp = entry.get("timestamp", "")

        try:
            ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            ts = datetime.min

        if msg_type == "info":
            continue

        if msg_type == "user":
            content = entry.get("content", [])
            text = ""
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = " ".join(
                    item.get("text", "") for item in content if isinstance(item, dict)
                )
            if text.strip():
                messages.append(Message(role="user", timestamp=ts, text=[text.strip()]))

        elif msg_type == "gemini":
            tokens = entry.get("tokens", {})
            model = entry.get("model")
            msg = Message(
                role="assistant",
                timestamp=ts,
                model=model,
                tokens_in=tokens.get("input", 0),
                tokens_out=tokens.get("output", 0),
            )

            # Content text
            content = entry.get("content", "")
            if isinstance(content, str) and content.strip():
                msg.text.append(content.strip())

            # Thinking
            for thought in entry.get("thoughts", []):
                desc = thought.get("description", "")
                if desc.strip():
                    msg.thinking.append(desc.strip())

            # Tool calls
            for tc in entry.get("toolCalls", []):
                name = tc.get("displayName") or tc.get("name", "?")
                summary = _gemini_tool_summary(tc.get("name", ""), tc.get("args", {}))
                result_str, passed = _gemini_tool_result(tc)
                msg.tool_calls.append(ToolCall(name=name, summary=summary, result=result_str, passed=passed))

            messages.append(msg)

    return messages
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd <repo-root> && python -m pytest tests/test_transcript.py -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add transcript.py tests/test_transcript.py
git commit -m "feat: add Gemini CLI JSON parser"
```

---

### Task 4: Markdown renderer

**Files:**
- Modify: `transcript.py`
- Modify: `tests/test_transcript.py`

- [ ] **Step 1: Write test for renderer**

```python
# Add to tests/test_transcript.py
from transcript import render_markdown, Message, ToolCall
from datetime import datetime, timezone

def test_render_basic():
    """Test renderer produces expected markdown structure."""
    msgs = [
        Message(
            role="user",
            timestamp=datetime(2026, 3, 18, 14, 0, 0, tzinfo=timezone.utc),
            text=["Hello, help me refactor auth"],
        ),
        Message(
            role="assistant",
            timestamp=datetime(2026, 3, 18, 14, 0, 5, tzinfo=timezone.utc),
            model="claude-opus-4-6",
            tokens_in=12000,
            tokens_out=1200,
            thinking=["Let me look at the auth code first."],
            text=["I'll start by reading the middleware."],
            tool_calls=[
                ToolCall(name="Read", summary="/src/auth.py", result="84 lines", passed=True),
                ToolCall(name="Bash", summary="pytest tests/", result="FAILED (exit 1)", passed=False),
            ],
        ),
    ]
    md = render_markdown(msgs)
    # Summary header
    assert "# Transcript" in md
    assert "Duration" in md
    assert "claude-opus-4-6" in md
    assert "2 (1 user, 1 assistant)" in md  # message count
    assert "2 (1 passed, 1 failed)" in md   # tool call count
    # User message
    assert "## User" in md
    assert "Hello, help me refactor auth" in md
    # Assistant message with tokens
    assert "## Assistant" in md
    assert "↑12,000" in md
    assert "↓1,200" in md
    # Thinking as blockquote
    assert "> Let me look at the auth code first." in md
    # Tool calls in code block
    assert "Read: /src/auth.py → 84 lines" in md
    assert "Bash: pytest tests/ → FAILED (exit 1)" in md
    # Separator
    assert "---" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd <repo-root> && python -m pytest tests/test_transcript.py::test_render_basic -v`
Expected: FAIL — `render_markdown` not defined

- [ ] **Step 3: Implement renderer**

Add to `transcript.py`:

```python
def _format_tokens(n: int) -> str:
    """Format token count with comma separators."""
    return f"{n:,}"


def _format_cost(cost: float | None) -> str:
    """Format cost as dollar string."""
    if cost is None:
        return "$?"
    if cost < 0.01:
        return f"${cost:.4f}"
    return f"${cost:.2f}"


def _format_duration(start: datetime, end: datetime) -> str:
    """Format duration as human readable string."""
    delta = end - start
    total_seconds = int(delta.total_seconds())
    if total_seconds < 0:
        return "0s"
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes > 0:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def _format_ts(ts: datetime) -> str:
    """Format timestamp for display (no timezone)."""
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def render_markdown(messages: list[Message]) -> str:
    """Render messages to Markdown transcript."""
    if not messages:
        return "# Transcript\n\nNo messages.\n"

    lines: list[str] = []

    # Collect stats
    models = set()
    total_in = 0
    total_out = 0
    user_count = 0
    assistant_count = 0
    tool_passed = 0
    tool_failed = 0
    start_ts = messages[0].timestamp
    end_ts = messages[-1].timestamp

    for m in messages:
        if m.role == "user":
            user_count += 1
        else:
            assistant_count += 1
            total_in += m.tokens_in
            total_out += m.tokens_out
            if m.model:
                models.add(m.model)
        for tc in m.tool_calls:
            if tc.passed:
                tool_passed += 1
            else:
                tool_failed += 1

    total_cost = 0.0
    cost_known = True
    for m in messages:
        if m.role == "assistant" and m.model:
            c = estimate_cost(m.model, m.tokens_in, m.tokens_out)
            if c is not None:
                total_cost += c
            else:
                cost_known = False

    total_msgs = user_count + assistant_count
    total_tools = tool_passed + tool_failed

    # Summary header
    lines.append("# Transcript")
    lines.append("")
    lines.append(
        f"- **Duration**: {_format_duration(start_ts, end_ts)} "
        f"({_format_ts(start_ts)} → {_format_ts(end_ts)})"
    )
    lines.append(f"- **Model(s)**: {', '.join(sorted(models)) or 'unknown'}")
    lines.append(f"- **Messages**: {total_msgs} ({user_count} user, {assistant_count} assistant)")
    lines.append(f"- **Tool calls**: {total_tools} ({tool_passed} passed, {tool_failed} failed)")
    lines.append(
        f"- **Tokens**: ↑{_format_tokens(total_in)} ↓{_format_tokens(total_out)} · "
        f"{_format_cost(total_cost) if cost_known else '$?'}"
    )

    # Messages
    for m in messages:
        lines.append("")
        lines.append("---")
        lines.append("")

        if m.role == "user":
            lines.append(f"## User · {_format_ts(m.timestamp)}")
        else:
            msg_cost = estimate_cost(m.model or "", m.tokens_in, m.tokens_out)
            lines.append(
                f"## Assistant · {_format_ts(m.timestamp)} · "
                f"↑{_format_tokens(m.tokens_in)} ↓{_format_tokens(m.tokens_out)} · "
                f"{_format_cost(msg_cost)}"
            )

        lines.append("")

        # Thinking blocks
        for t in m.thinking:
            for tline in t.split("\n"):
                lines.append(f"> {tline}")
            lines.append("")

        # Text blocks
        for t in m.text:
            lines.append(t)
            lines.append("")

        # Tool calls — group consecutive into fenced blocks
        if m.tool_calls:
            lines.append("```")
            for tc in m.tool_calls:
                lines.append(f"{tc.name}: {tc.summary} → {tc.result}")
            lines.append("```")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd <repo-root> && python -m pytest tests/test_transcript.py -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add transcript.py tests/test_transcript.py
git commit -m "feat: add Markdown renderer"
```

---

### Task 5: CLI entry point and end-to-end test

**Files:**
- Modify: `transcript.py`
- Modify: `tests/test_transcript.py`

- [ ] **Step 1: Write end-to-end test**

```python
# Add to tests/test_transcript.py
import subprocess

def test_cli_claude_e2e():
    """Run transcript.py on a real Claude log and check output structure."""
    result = subprocess.run(
        ["python", "transcript.py", "--format", "claude",
         "~/.claude/projects/"
         "<project>/"
         "<session>.jsonl"],
        capture_output=True, text=True, cwd="<repo-root>"
    )
    assert result.returncode == 0
    md = result.stdout
    assert "# Transcript" in md
    assert "## User" in md
    assert "## Assistant" in md
    assert "---" in md

def test_cli_gemini_e2e():
    """Run transcript.py on a real Gemini log and check output structure."""
    result = subprocess.run(
        ["python", "transcript.py", "--format", "gemini",
         "~/projects/<project>/chats/"
         "session-<timestamp>.json"],
        capture_output=True, text=True, cwd="<repo-root>"
    )
    assert result.returncode == 0
    md = result.stdout
    assert "# Transcript" in md
    assert "## User" in md
    assert "## Assistant" in md
    assert "gemini-3-flash-preview" in md
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd <repo-root> && python -m pytest tests/test_transcript.py::test_cli_claude_e2e tests/test_transcript.py::test_cli_gemini_e2e -v`
Expected: FAIL — no CLI entry point

- [ ] **Step 3: Implement CLI**

Add to the bottom of `transcript.py`:

```python
def main():
    parser = argparse.ArgumentParser(
        description="Convert agent logs to readable Markdown transcripts."
    )
    parser.add_argument(
        "-f", "--format", required=True, choices=["claude", "gemini"],
        help="Log format: claude (JSONL) or gemini (JSON)"
    )
    parser.add_argument("input", help="Path to log file")
    parser.add_argument("-o", "--output", help="Output file (default: stdout)")

    args = parser.parse_args()

    if args.format == "claude":
        messages = parse_claude(args.input)
    else:
        messages = parse_gemini(args.input)

    md = render_markdown(messages)

    if args.output:
        with open(args.output, "w") as f:
            f.write(md)
    else:
        sys.stdout.write(md)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run all tests**

Run: `cd <repo-root> && python -m pytest tests/test_transcript.py -v`
Expected: all tests PASS

- [ ] **Step 5: Manual smoke test — generate both transcripts and eyeball them**

```bash
cd <repo-root>
python transcript.py -f claude ~/.claude/projects/<project>/<session>.jsonl -o sample_claude.md
python transcript.py -f gemini ~/projects/<project>/chats/session-<timestamp>.json -o sample_gemini.md
```

Review both output files for correctness: proper headers, thinking blocks as `>`, tool calls in code blocks, cost estimates, etc.

- [ ] **Step 6: Commit**

```bash
git add transcript.py tests/test_transcript.py
git commit -m "feat: add CLI entry point and end-to-end tests"
```
