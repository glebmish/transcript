# Transcript Tool v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the transcript tool as a proper Python package with a common model, two parsers (Claude/Gemini), a markdown renderer with content control flags, a CLI entry point with auto-detection, and a TUI viewer built on textual.

**Architecture:** All parsers produce a `Transcript` dataclass. The markdown renderer and TUI consume only this model. The CLI auto-detects log format and dispatches to the right parser. The TUI is a two-panel textual app with conversation on the left and detail on the right.

**Tech Stack:** Python 3.12, textual 8.x, rich 14.x, pytest. Venv at `.venv/`.

**Run commands:** Always use `.venv/bin/python` and `.venv/bin/pytest`.

**Specs:** All specs live in `docs/specs/`. Current canonical specs are `common-model.md`, `presentation.md`, `agents/claude.md`, `agents/gemini.md`, `renderers/markdown.md`, and `renderers/tui.md`.

---

## File Structure

```
transcript/
    __init__.py           # empty
    model.py              # Status, Role, ToolCall, Message, ToolStats, Transcript
    pricing.py            # PRICING dict, estimate_cost()
    detect.py             # detect_format(path) -> "claude" | "gemini"
    parsers/
        __init__.py       # empty
        claude.py         # parse(path) -> Transcript
        gemini.py         # parse(path) -> Transcript
    renderers/
        __init__.py       # empty
        markdown.py       # render(transcript, options) -> str
    tui/
        __init__.py       # empty
        app.py            # TranscriptApp(textual.app.App)
        widgets.py        # ConversationPanel, DetailPanel, SearchBar
    cli.py                # main() entry point
tests/
    __init__.py           # empty
    test_model.py
    test_pricing.py
    test_detect.py
    test_claude_parser.py
    test_gemini_parser.py
    test_markdown.py
    test_cli.py
    fixtures/             # inline test data
        __init__.py
        claude_minimal.jsonl
        gemini_minimal.json
```

Old files to delete: `transcript.py`, `tests/test_transcript.py`

---

### Task 1: Package scaffolding + model.py

**Files:**
- Create: `transcript/__init__.py`, `transcript/model.py`
- Create: `transcript/parsers/__init__.py`, `transcript/renderers/__init__.py`, `transcript/tui/__init__.py`
- Create: `tests/test_model.py`
- Create: `pyproject.toml`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "transcript"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["textual>=0.80", "rich>=13"]

[project.scripts]
transcript = "transcript.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create package directories and __init__.py files**

Create empty `__init__.py` in: `transcript/`, `transcript/parsers/`, `transcript/renderers/`, `transcript/tui/`, `tests/`.

- [ ] **Step 3: Write tests for model.py**

```python
# tests/test_model.py
from datetime import datetime, timezone
from transcript.model import Status, Role, ToolCall, Message, ToolStats, Transcript


def test_status_values():
    assert Status.PASSED.value == "passed"
    assert Status.FAILED.value == "failed"
    assert Status.CANCELLED.value == "cancelled"


def test_role_values():
    assert Role.USER.value == "user"
    assert Role.ASSISTANT.value == "assistant"


def test_tool_call_creation():
    tc = ToolCall(
        name="Bash",
        display_name="Bash",
        summary="pytest tests/",
        result_summary="FAILED (exit 1)",
        result_full="FAILED test_auth.py::test_jwt\nAssertionError",
        status=Status.FAILED,
    )
    assert tc.name == "Bash"
    assert tc.status == Status.FAILED


def test_message_defaults():
    msg = Message(role=Role.USER, timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert msg.model is None
    assert msg.tokens_in == 0
    assert msg.tokens_out == 0
    assert msg.tokens_cached == 0
    assert msg.tokens_thinking == 0
    assert msg.thinking == []
    assert msg.text == []
    assert msg.tool_calls == []
    assert msg.is_compaction_marker is False


def test_transcript_creation():
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t = Transcript(
        messages=[],
        source_format="claude",
        session_id="abc",
        start_time=ts,
        end_time=ts,
        models=set(),
        total_tokens_in=0,
        total_tokens_out=0,
        total_cost=None,
        cost_is_partial=False,
        tool_stats=ToolStats(passed=0, failed=0, cancelled=0),
    )
    assert t.source_format == "claude"
    assert t.cost_is_partial is False
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_model.py -v`
Expected: FAIL (module not found)

- [ ] **Step 5: Implement model.py**

```python
# transcript/model.py
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Status(Enum):
    PASSED = "passed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Role(Enum):
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class ToolCall:
    name: str
    display_name: str
    summary: str
    result_summary: str
    result_full: str
    status: Status


@dataclass
class Message:
    role: Role
    timestamp: datetime
    model: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_cached: int = 0
    tokens_thinking: int = 0
    thinking: list[str] = field(default_factory=list)
    text: list[str] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    is_compaction_marker: bool = False


@dataclass
class ToolStats:
    passed: int
    failed: int
    cancelled: int


@dataclass
class Transcript:
    messages: list[Message]
    source_format: str
    session_id: str | None
    start_time: datetime
    end_time: datetime
    models: set[str]
    total_tokens_in: int
    total_tokens_out: int
    total_cost: float | None
    cost_is_partial: bool
    tool_stats: ToolStats
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_model.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add transcript/ tests/test_model.py pyproject.toml
git commit -m "feat: add package scaffolding and model.py with data classes"
```

---

### Task 2: pricing.py

**Files:**
- Create: `transcript/pricing.py`
- Create: `tests/test_pricing.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_pricing.py
from transcript.pricing import estimate_cost, PRICING


def test_opus_pricing():
    cost = estimate_cost("claude-opus-4-6", tokens_in=1_000_000, tokens_out=1_000_000, tokens_cached=0)
    assert cost == 5.00 + 25.00


def test_prefix_match():
    cost = estimate_cost("claude-opus-4-6-20250618", tokens_in=1_000_000, tokens_out=0, tokens_cached=0)
    assert cost == 5.00


def test_cache_aware():
    # 1M input, 800k cached = 200k billable
    cost = estimate_cost("claude-opus-4-6", tokens_in=1_000_000, tokens_out=0, tokens_cached=800_000)
    assert cost == 200_000 / 1_000_000 * 5.00


def test_gemini_pricing():
    cost = estimate_cost("gemini-2.5-flash", tokens_in=1_000_000, tokens_out=1_000_000, tokens_cached=0)
    assert cost == 0.30 + 2.50


def test_unknown_model():
    cost = estimate_cost("unknown-model", tokens_in=1_000, tokens_out=1_000, tokens_cached=0)
    assert cost is None


def test_sonnet_pricing():
    cost = estimate_cost("claude-sonnet-4-6", tokens_in=1_000_000, tokens_out=1_000_000, tokens_cached=0)
    assert cost == 3.00 + 15.00


def test_haiku_pricing():
    cost = estimate_cost("claude-haiku-4-5", tokens_in=1_000_000, tokens_out=1_000_000, tokens_cached=0)
    assert cost == 1.00 + 5.00
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_pricing.py -v`

- [ ] **Step 3: Implement pricing.py**

```python
# transcript/pricing.py

# (input_price, output_price) per 1M tokens in USD
PRICING = {
    "claude-opus-4-6":   (5.00,  25.00),
    "claude-sonnet-4-6": (3.00,  15.00),
    "claude-haiku-4-5":  (1.00,   5.00),
    "gemini-2.5-pro":    (1.00,  10.00),
    "gemini-2.5-flash":  (0.30,   2.50),
}


def estimate_cost(model: str, tokens_in: int, tokens_out: int, tokens_cached: int) -> float | None:
    for prefix, (in_price, out_price) in PRICING.items():
        if model == prefix or model.startswith(prefix):
            billable_input = tokens_in - tokens_cached
            return billable_input / 1_000_000 * in_price + tokens_out / 1_000_000 * out_price
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_pricing.py -v`

- [ ] **Step 5: Commit**

```bash
git add transcript/pricing.py tests/test_pricing.py
git commit -m "feat: add cache-aware pricing estimation"
```

---

### Task 3: Test fixtures

**Files:**
- Create: `tests/fixtures/__init__.py`
- Create: `tests/fixtures/claude_minimal.jsonl`
- Create: `tests/fixtures/gemini_minimal.json`

These are minimal synthetic logs for deterministic testing.

- [ ] **Step 1: Create Claude fixture**

`tests/fixtures/claude_minimal.jsonl` — a minimal Claude session with: one user message, one assistant message with thinking + text + tool_use, one tool_result, one compact_boundary system entry, and a second user message.

```jsonl
{"type":"user","timestamp":"2026-01-01T10:00:00Z","message":{"role":"user","content":[{"type":"text","text":"Help me refactor auth"}]}}
{"type":"assistant","timestamp":"2026-01-01T10:00:05Z","message":{"id":"msg_001","role":"assistant","model":"claude-opus-4-6","content":[{"type":"thinking","thinking":"Let me look at auth code."},{"type":"text","text":"I'll read the middleware."},{"type":"tool_use","id":"toolu_abc123","name":"Read","input":{"file_path":"/src/auth.py"}}],"usage":{"input_tokens":10000,"output_tokens":500,"cache_read_input_tokens":8000}}}
{"type":"user","timestamp":"2026-01-01T10:00:06Z","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"toolu_abc123","content":"def authenticate():\n    pass\n# 84 lines total"}]},"toolUseResult":{"file":{"totalLines":84}}}
{"type":"system","subtype":"compact_boundary","timestamp":"2026-01-01T10:01:00Z","content":"Conversation compacted","isMeta":false,"compactMetadata":{"trigger":"manual","preTokens":50000}}
{"type":"user","timestamp":"2026-01-01T10:02:00Z","message":{"role":"user","content":[{"type":"text","text":"Focus on JWT validation"}]}}
{"type":"assistant","timestamp":"2026-01-01T10:02:05Z","message":{"id":"msg_002","role":"assistant","model":"claude-opus-4-6","content":[{"type":"text","text":"I'll look at JWT handling."},{"type":"tool_use","id":"toolu_def456","name":"Bash","input":{"command":"pytest tests/","description":"Run tests"}}],"usage":{"input_tokens":12000,"output_tokens":300,"cache_read_input_tokens":9000}}}
{"type":"user","timestamp":"2026-01-01T10:02:10Z","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"toolu_def456","content":"FAILED test_auth.py::test_jwt\nAssertionError: expected 200 got 401","is_error":true}]},"toolUseResult":{"exitCode":1}}
```

- [ ] **Step 2: Create Gemini fixture**

`tests/fixtures/gemini_minimal.json` — a minimal Gemini session with: one user, one gemini with thinking + tools + content, a cancelled tool.

```json
{
  "sessionId": "test-session-001",
  "projectHash": "abc123",
  "startTime": "2026-01-01T10:00:00Z",
  "lastUpdated": "2026-01-01T10:05:00Z",
  "messages": [
    {
      "type": "user",
      "timestamp": "2026-01-01T10:00:00Z",
      "content": [{"text": "Help me fix the login bug"}]
    },
    {
      "type": "gemini",
      "timestamp": "2026-01-01T10:00:05Z",
      "model": "gemini-2.5-flash",
      "content": "I'll investigate the login issue.",
      "thoughts": [
        {"subject": "Analysis", "description": "Let me check the auth module.", "timestamp": "2026-01-01T10:00:04Z"}
      ],
      "toolCalls": [
        {
          "id": "read_file-123",
          "name": "read_file",
          "displayName": "ReadFile",
          "args": {"absolute_path": "/src/login.py"},
          "result": [{"functionResponse": {"id": "read_file-123", "name": "read_file", "response": {"output": "def login():\n    pass"}}}],
          "status": "success",
          "resultDisplay": "22 lines",
          "timestamp": "2026-01-01T10:00:05Z",
          "description": "Read a file",
          "renderOutputAsMarkdown": true
        },
        {
          "id": "run_shell_command-456",
          "name": "run_shell_command",
          "displayName": "Shell",
          "args": {"command": "npm test", "description": "Run tests"},
          "result": [{"functionResponse": {"id": "run_shell_command-456", "name": "run_shell_command", "response": {"error": "[Operation Cancelled] Reason: User cancelled the operation."}}}],
          "status": "cancelled",
          "resultDisplay": null,
          "timestamp": "2026-01-01T10:00:06Z",
          "description": "Run a shell command",
          "renderOutputAsMarkdown": false
        }
      ],
      "tokens": {"input": 5000, "output": 200, "cached": 3000, "thoughts": 100}
    },
    {
      "type": "info",
      "timestamp": "2026-01-01T10:00:07Z",
      "content": "Request cancelled."
    },
    {
      "type": "user",
      "timestamp": "2026-01-01T10:01:00Z",
      "content": [{"text": "Try a different approach"}]
    },
    {
      "type": "gemini",
      "timestamp": "2026-01-01T10:01:05Z",
      "model": "gemini-2.5-flash",
      "content": "Let me try another approach.",
      "toolCalls": [],
      "tokens": {"input": 8000, "output": 150, "cached": 5000, "thoughts": 50}
    }
  ]
}
```

- [ ] **Step 3: Create fixtures/__init__.py and commit**

```bash
git add tests/fixtures/
git commit -m "feat: add test fixtures for Claude and Gemini parsers"
```

---

### Task 4: Claude parser

**Files:**
- Create: `transcript/parsers/claude.py`
- Create: `tests/test_claude_parser.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_claude_parser.py
from pathlib import Path
from transcript.parsers.claude import parse
from transcript.model import Status, Role

FIXTURE = str(Path(__file__).parent / "fixtures" / "claude_minimal.jsonl")


def test_parse_message_count():
    t = parse(FIXTURE)
    # 2 user messages + 2 assistant messages + 1 compaction marker = 5
    assert len(t.messages) == 5


def test_parse_user_message():
    t = parse(FIXTURE)
    msg = t.messages[0]
    assert msg.role == Role.USER
    assert msg.text == ["Help me refactor auth"]
    assert msg.is_compaction_marker is False


def test_parse_assistant_with_thinking():
    t = parse(FIXTURE)
    msg = t.messages[1]
    assert msg.role == Role.ASSISTANT
    assert msg.model == "claude-opus-4-6"
    assert msg.thinking == ["Let me look at auth code."]
    assert msg.text == ["I'll read the middleware."]


def test_parse_tool_call_by_id():
    t = parse(FIXTURE)
    msg = t.messages[1]
    assert len(msg.tool_calls) == 1
    tc = msg.tool_calls[0]
    assert tc.name == "Read"
    assert tc.display_name == "Read"
    assert tc.summary == "/src/auth.py"
    assert tc.result_summary == "84 lines"
    assert "def authenticate" in tc.result_full
    assert tc.status == Status.PASSED


def test_parse_failed_tool():
    t = parse(FIXTURE)
    msg = t.messages[3]  # second assistant (after compaction marker)
    tc = msg.tool_calls[0]
    assert tc.name == "Bash"
    assert tc.summary == "Run tests"
    assert tc.result_summary == "FAILED (exit 1)"
    assert tc.status == Status.FAILED
    assert "AssertionError" in tc.result_full


def test_parse_compaction_marker():
    t = parse(FIXTURE)
    marker = t.messages[2]
    assert marker.is_compaction_marker is True


def test_parse_tokens_cache_aware():
    t = parse(FIXTURE)
    msg = t.messages[1]
    assert msg.tokens_in == 10000
    assert msg.tokens_out == 500
    assert msg.tokens_cached == 8000


def test_parse_transcript_metadata():
    t = parse(FIXTURE)
    assert t.source_format == "claude"
    assert "claude-opus-4-6" in t.models
    assert t.total_tokens_in == 22000  # 10000 + 12000
    assert t.total_tokens_out == 800   # 500 + 300


def test_parse_tool_stats():
    t = parse(FIXTURE)
    assert t.tool_stats.passed == 1
    assert t.tool_stats.failed == 1
    assert t.tool_stats.cancelled == 0


def test_parse_cost():
    t = parse(FIXTURE)
    # billable_in = (10000-8000) + (12000-9000) = 2000 + 3000 = 5000
    # cost = 5000/1M * 5.00 + 800/1M * 25.00 = 0.025 + 0.02 = 0.045
    assert t.total_cost is not None
    assert abs(t.total_cost - 0.045) < 0.001
    assert t.cost_is_partial is False


def test_deduplication():
    """Streaming produces multiple lines with same message.id — tokens counted once."""
    import tempfile, os
    lines = [
        '{"type":"user","timestamp":"2026-01-01T10:00:00Z","message":{"role":"user","content":[{"type":"text","text":"hi"}]}}',
        '{"type":"assistant","timestamp":"2026-01-01T10:00:01Z","message":{"id":"msg_dup","role":"assistant","model":"claude-sonnet-4-6","content":[{"type":"text","text":"hello"}],"usage":{"input_tokens":100,"output_tokens":50,"cache_read_input_tokens":0}}}',
        '{"type":"assistant","timestamp":"2026-01-01T10:00:01Z","message":{"id":"msg_dup","role":"assistant","model":"claude-sonnet-4-6","content":[{"type":"text","text":" world"}],"usage":{"input_tokens":100,"output_tokens":50,"cache_read_input_tokens":0}}}',
    ]
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    try:
        with os.fdopen(fd, "w") as f:
            f.write("\n".join(lines))
        t = parse(path)
        assistant_msgs = [m for m in t.messages if m.role == Role.ASSISTANT]
        assert len(assistant_msgs) == 1
        assert assistant_msgs[0].tokens_in == 100  # counted once, not 200
        assert assistant_msgs[0].text == ["hello", "world"]  # both accumulated
    finally:
        os.unlink(path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_claude_parser.py -v`

- [ ] **Step 3: Implement Claude parser**

See `docs/specs/agents/claude.md` for full spec. Key implementation points:

- Read JSONL line by line, skip non-user/non-assistant/non-system types
- Store tool_use blocks in a dict keyed by `id`
- Match tool_result by `tool_use_id`
- Handle `system` entries with `compact_boundary` subtype → insert compaction marker message
- Use `_claude_tool_summary(name, input)` for summary extraction per spec table
- Use `_claude_tool_result(toolUseResult)` for result_summary extraction per spec table
- Extract `result_full` from `tool_result.content`
- Deduplicate by `message.id` — accumulate content, count tokens once
- Build Transcript with computed totals, cost, tool_stats

```python
# transcript/parsers/claude.py
import json
import sys
from datetime import datetime, timezone
from transcript.model import Status, Role, ToolCall, Message, ToolStats, Transcript
from transcript.pricing import estimate_cost

_MIN_TS = datetime.min.replace(tzinfo=timezone.utc)


def _parse_ts(raw: str) -> datetime:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return _MIN_TS


def _tool_summary(name: str, input_data: dict) -> str:
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
    if name == "Agent":
        return input_data.get("description") or (input_data.get("prompt", "?")[:80])
    if name == "Skill":
        return input_data.get("skill", "?")
    if name in ("TaskCreate", "TaskUpdate"):
        return input_data.get("subject") or input_data.get("taskId") or "?"
    for v in input_data.values():
        if isinstance(v, str) and v:
            return v[:80]
    return "?"


def _tool_result_summary(tool_use_result) -> tuple[str, Status]:
    if tool_use_result is None:
        return "ok", Status.PASSED
    if isinstance(tool_use_result, str):
        short = tool_use_result.split("\n")[0][:50]
        return f"FAILED: {short}", Status.FAILED
    if isinstance(tool_use_result, dict):
        if "file" in tool_use_result:
            f = tool_use_result["file"]
            return f'{f.get("totalLines", "?")} lines', Status.PASSED
        if "filenames" in tool_use_result:
            return f'{tool_use_result.get("numFiles", "?")} files', Status.PASSED
        if "numMatches" in tool_use_result:
            return f'{tool_use_result["numMatches"]} matches', Status.PASSED
        if "url" in tool_use_result:
            return f'HTTP {tool_use_result.get("code", "?")}', Status.PASSED
        if "exitCode" in tool_use_result:
            ec = tool_use_result["exitCode"]
            if ec != 0:
                return f"FAILED (exit {ec})", Status.FAILED
            return "ok", Status.PASSED
    return "ok", Status.PASSED


def parse(path: str) -> Transcript:
    messages: list[Message] = []
    current_assistant: Message | None = None
    pending_tool_uses: dict[str, dict] = {}  # id -> tool_use block
    seen_msg_ids: set[str] = set()
    current_msg_id: str | None = None

    with open(path) as f:
        for line_num, line_str in enumerate(f, 1):
            line_str = line_str.strip()
            if not line_str:
                continue
            try:
                entry = json.loads(line_str)
            except json.JSONDecodeError:
                print(f"Warning: skipping malformed line {line_num}", file=sys.stderr)
                continue

            entry_type = entry.get("type")

            if entry_type == "system":
                subtype = entry.get("subtype", "")
                if subtype == "compact_boundary":
                    if current_assistant:
                        messages.append(current_assistant)
                        current_assistant = None
                        pending_tool_uses = {}
                    messages.append(Message(
                        role=Role.USER,
                        timestamp=_parse_ts(entry.get("timestamp", "")),
                        is_compaction_marker=True,
                        text=["Conversation compacted"],
                    ))
                elif subtype not in ("api_error", "turn_duration", "local_command", "bridge_status"):
                    print(f"Warning: unknown system subtype '{subtype}' at line {line_num}", file=sys.stderr)
                continue

            if entry_type not in ("user", "assistant"):
                continue

            content = entry.get("message", {}).get("content", [])
            ts = _parse_ts(entry.get("timestamp", ""))

            if entry_type == "user":
                if isinstance(content, list) and content and isinstance(content[0], dict):
                    block = content[0]
                    if block.get("type") == "tool_result":
                        tool_use_id = block.get("tool_use_id", "")
                        is_error = block.get("is_error", False)
                        tool_use_result = entry.get("toolUseResult")
                        result_full = block.get("content", "")
                        if isinstance(result_full, list):
                            result_full = "\n".join(
                                b.get("text", "") for b in result_full if isinstance(b, dict)
                            )

                        if tool_use_id in pending_tool_uses:
                            tu = pending_tool_uses.pop(tool_use_id)
                            summary = _tool_summary(tu["name"], tu.get("input", {}))
                            result_str, status = _tool_result_summary(tool_use_result)
                            if is_error:
                                status = Status.FAILED
                                if not result_str.startswith("FAILED"):
                                    result_str = f"FAILED: {result_str}"
                            if current_assistant:
                                current_assistant.tool_calls.append(ToolCall(
                                    name=tu["name"],
                                    display_name=tu["name"],
                                    summary=summary,
                                    result_summary=result_str,
                                    result_full=result_full,
                                    status=status,
                                ))
                        continue

                # Actual user message
                if current_assistant:
                    messages.append(current_assistant)
                    current_assistant = None
                    pending_tool_uses = {}
                    seen_msg_ids.clear()
                    current_msg_id = None

                text_content = ""
                if isinstance(content, str):
                    text_content = content
                elif isinstance(content, list):
                    text_content = " ".join(
                        b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
                    )
                if text_content.strip():
                    messages.append(Message(role=Role.USER, timestamp=ts, text=[text_content.strip()]))

            elif entry_type == "assistant":
                msg = entry.get("message", {})
                model = msg.get("model")
                usage = msg.get("usage", {})
                msg_id = msg.get("id")

                if current_assistant is None:
                    current_assistant = Message(role=Role.ASSISTANT, timestamp=ts, model=model)

                is_new_msg_id = msg_id and msg_id not in seen_msg_ids
                if is_new_msg_id:
                    seen_msg_ids.add(msg_id)
                    current_assistant.tokens_in += usage.get("input_tokens", 0)
                    current_assistant.tokens_out += usage.get("output_tokens", 0)
                    current_assistant.tokens_cached += usage.get("cache_read_input_tokens", 0)
                    if model:
                        current_assistant.model = model

                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        btype = block.get("type")
                        if btype == "thinking":
                            text = block.get("thinking", "")
                            if text.strip():
                                current_assistant.thinking.append(text.strip())
                        elif btype == "text":
                            text = block.get("text", "")
                            if text.strip():
                                current_assistant.text.append(text.strip())
                        elif btype == "tool_use":
                            tu_id = block.get("id", "")
                            pending_tool_uses[tu_id] = block

    if current_assistant:
        # Create ToolCalls for any unmatched tool_uses
        for tu_id, tu in pending_tool_uses.items():
            current_assistant.tool_calls.append(ToolCall(
                name=tu["name"],
                display_name=tu["name"],
                summary=_tool_summary(tu["name"], tu.get("input", {})),
                result_summary="no result",
                result_full="",
                status=Status.FAILED,
            ))
        messages.append(current_assistant)

    return _build_transcript(messages, "claude")


def _build_transcript(messages: list[Message], source_format: str) -> Transcript:
    models: set[str] = set()
    total_in = 0
    total_out = 0
    total_cached = 0
    passed = failed = cancelled = 0
    total_cost = 0.0
    cost_is_partial = False

    for m in messages:
        if m.is_compaction_marker:
            continue
        if m.role == Role.ASSISTANT and m.model:
            models.add(m.model)
        total_in += m.tokens_in
        total_out += m.tokens_out
        total_cached += m.tokens_cached
        for tc in m.tool_calls:
            if tc.status == Status.PASSED:
                passed += 1
            elif tc.status == Status.FAILED:
                failed += 1
            elif tc.status == Status.CANCELLED:
                cancelled += 1

    for m in messages:
        if m.role == Role.ASSISTANT and m.model:
            c = estimate_cost(m.model, m.tokens_in, m.tokens_out, m.tokens_cached)
            if c is not None:
                total_cost += c
            else:
                cost_is_partial = True

    non_marker = [m for m in messages if not m.is_compaction_marker]
    start = non_marker[0].timestamp if non_marker else _MIN_TS
    end = non_marker[-1].timestamp if non_marker else _MIN_TS

    if not models or (cost_is_partial and total_cost == 0.0):
        final_cost = None
    else:
        final_cost = total_cost

    return Transcript(
        messages=messages,
        source_format=source_format,
        session_id=None,
        start_time=start,
        end_time=end,
        models=models,
        total_tokens_in=total_in,
        total_tokens_out=total_out,
        total_cost=final_cost,
        cost_is_partial=cost_is_partial,
        tool_stats=ToolStats(passed=passed, failed=failed, cancelled=cancelled),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_claude_parser.py -v`

- [ ] **Step 5: Commit**

```bash
git add transcript/parsers/claude.py tests/test_claude_parser.py
git commit -m "feat: add Claude Code JSONL parser with ID-based tool matching"
```

---

### Task 5: Gemini parser

**Files:**
- Create: `transcript/parsers/gemini.py`
- Create: `tests/test_gemini_parser.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_gemini_parser.py
from pathlib import Path
from transcript.parsers.gemini import parse
from transcript.model import Status, Role

FIXTURE = str(Path(__file__).parent / "fixtures" / "gemini_minimal.json")


def test_parse_message_count():
    t = parse(FIXTURE)
    # 2 user + 2 gemini = 4 (info skipped)
    assert len(t.messages) == 4


def test_parse_user_message():
    t = parse(FIXTURE)
    msg = t.messages[0]
    assert msg.role == Role.USER
    assert msg.text == ["Help me fix the login bug"]


def test_parse_gemini_content():
    t = parse(FIXTURE)
    msg = t.messages[1]
    assert msg.role == Role.ASSISTANT
    assert msg.model == "gemini-2.5-flash"
    assert msg.text == ["I'll investigate the login issue."]


def test_parse_thinking():
    t = parse(FIXTURE)
    msg = t.messages[1]
    assert msg.thinking == ["Let me check the auth module."]


def test_parse_tool_call_success():
    t = parse(FIXTURE)
    msg = t.messages[1]
    tc = msg.tool_calls[0]
    assert tc.name == "read_file"
    assert tc.display_name == "ReadFile"
    assert tc.summary == "/src/login.py"
    assert tc.result_summary == "22 lines"
    assert "def login" in tc.result_full
    assert tc.status == Status.PASSED


def test_parse_tool_call_cancelled():
    t = parse(FIXTURE)
    msg = t.messages[1]
    tc = msg.tool_calls[1]
    assert tc.name == "run_shell_command"
    assert tc.display_name == "Shell"
    assert tc.summary == "Run tests"
    assert tc.status == Status.CANCELLED


def test_parse_input_token_delta():
    t = parse(FIXTURE)
    msg1 = t.messages[1]  # first gemini, raw input=5000
    msg2 = t.messages[3]  # second gemini, raw input=8000, delta=3000
    assert msg1.tokens_in == 5000
    assert msg2.tokens_in == 3000  # 8000 - 5000


def test_parse_cached_tokens():
    t = parse(FIXTURE)
    msg = t.messages[1]
    assert msg.tokens_cached == 3000
    assert msg.tokens_thinking == 100


def test_parse_transcript_metadata():
    t = parse(FIXTURE)
    assert t.source_format == "gemini"
    assert t.session_id == "test-session-001"
    assert "gemini-2.5-flash" in t.models


def test_parse_tool_stats():
    t = parse(FIXTURE)
    assert t.tool_stats.passed == 1
    assert t.tool_stats.failed == 0
    assert t.tool_stats.cancelled == 1


def test_info_messages_skipped():
    t = parse(FIXTURE)
    for m in t.messages:
        assert "Request cancelled" not in " ".join(m.text)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_gemini_parser.py -v`

- [ ] **Step 3: Implement Gemini parser**

See `docs/specs/agents/gemini.md` for full spec. Key implementation points:

- Read JSON file, iterate `messages[]`
- Skip `info` type entries
- Handle user `content` as array of `{text}` or plain string
- Compute input token delta (cumulative → per-message)
- Extract tool calls with display_name, result from functionResponse
- Map status string to Status enum
- Handle error detection via `functionResponse.response.error`

```python
# transcript/parsers/gemini.py
import json
from datetime import datetime, timezone
from transcript.model import Status, Role, ToolCall, Message, ToolStats, Transcript
from transcript.pricing import estimate_cost

_MIN_TS = datetime.min.replace(tzinfo=timezone.utc)

_STATUS_MAP = {
    "success": Status.PASSED,
    "error": Status.FAILED,
    "cancelled": Status.CANCELLED,
}


def _parse_ts(raw: str) -> datetime:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return _MIN_TS


def _tool_summary(name: str, args: dict) -> str:
    if name == "read_file":
        return args.get("absolute_path") or args.get("file_path") or "?"
    if name in ("write_file", "replace"):
        return args.get("file_path", "?")
    if name == "read_many_files":
        paths = args.get("paths", "?")
        if isinstance(paths, list):
            return ", ".join(str(p) for p in paths[:3])
        return str(paths)
    if name == "list_directory":
        return args.get("dir_path", "?")
    if name == "run_shell_command":
        return args.get("description") or (args.get("command", "?")[:80])
    if name in ("grep_search", "search_file_content"):
        return args.get("pattern", "?")
    if name == "glob":
        return args.get("pattern", "?")
    if name == "google_web_search":
        return args.get("query", "?")
    if name == "web_fetch":
        return args.get("url") or args.get("prompt") or "?"
    if name == "activate_skill":
        return args.get("name", "?")
    if name == "ask_user":
        q = args.get("questions", "?")
        if isinstance(q, list) and q:
            return str(q[0])[:80]
        return str(q)[:80]
    if name == "enter_plan_mode":
        return args.get("reason", "?")
    if name == "exit_plan_mode":
        return args.get("plan_path", "?")
    if name in ("codebase_investigator",):
        return args.get("objective", "?")[:80]
    if name in ("generalist",):
        return args.get("request", "?")[:80]
    if name == "cli_help":
        return args.get("question", "?")[:80]
    for v in args.values():
        if isinstance(v, str) and v:
            return v[:80]
    return "?"


def _extract_result(tc: dict) -> tuple[str, str, Status]:
    """Returns (result_summary, result_full, status)."""
    status = _STATUS_MAP.get(tc.get("status", "success"), Status.PASSED)
    result_display = tc.get("resultDisplay") or ""
    result_data = tc.get("result") or []

    result_full = ""
    if result_data and isinstance(result_data, list):
        fr = result_data[0]
        if isinstance(fr, dict):
            resp = fr.get("functionResponse", {}).get("response", {})
            if "error" in resp:
                return resp["error"], resp["error"], Status.FAILED
            result_full = resp.get("output", "")

    if result_display:
        if len(result_display) <= 50 and "\n" not in result_display:
            return result_display, result_full, status
        lines = result_display.strip().split("\n")
        return f"{len(lines)} lines", result_full, status

    if result_full:
        if len(result_full) <= 50 and "\n" not in result_full:
            return result_full, result_full, status
        lines = result_full.strip().split("\n")
        return f"{len(lines)} lines", result_full, status

    return "ok", result_full, status


def parse(path: str) -> Transcript:
    with open(path) as f:
        data = json.load(f)

    messages: list[Message] = []
    prev_input = 0

    for entry in data.get("messages", []):
        msg_type = entry.get("type")
        ts = _parse_ts(entry.get("timestamp", ""))

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
                messages.append(Message(role=Role.USER, timestamp=ts, text=[text.strip()]))

        elif msg_type == "gemini":
            tokens = entry.get("tokens", {})
            model = entry.get("model")
            full_input = tokens.get("input", 0)
            delta_input = full_input - prev_input if prev_input > 0 else full_input
            prev_input = full_input

            msg = Message(
                role=Role.ASSISTANT,
                timestamp=ts,
                model=model,
                tokens_in=delta_input,
                tokens_out=tokens.get("output", 0),
                tokens_cached=tokens.get("cached", 0),
                tokens_thinking=tokens.get("thoughts", 0),
            )

            content = entry.get("content", "")
            if isinstance(content, str) and content.strip():
                msg.text.append(content.strip())

            for thought in entry.get("thoughts", []):
                desc = thought.get("description", "")
                if desc.strip():
                    msg.thinking.append(desc.strip())

            for tc in entry.get("toolCalls", []):
                name = tc.get("name", "?")
                display_name = tc.get("displayName") or name
                summary = _tool_summary(name, tc.get("args", {}))
                result_summary, result_full, status = _extract_result(tc)
                msg.tool_calls.append(ToolCall(
                    name=name,
                    display_name=display_name,
                    summary=summary,
                    result_summary=result_summary,
                    result_full=result_full,
                    status=status,
                ))

            messages.append(msg)

    return _build_transcript(messages, data, "gemini")


def _build_transcript(messages: list[Message], data: dict, source_format: str) -> Transcript:
    models: set[str] = set()
    total_in = total_out = 0
    passed = failed = cancelled = 0
    total_cost = 0.0
    cost_is_partial = False

    for m in messages:
        if m.role == Role.ASSISTANT and m.model:
            models.add(m.model)
        total_in += m.tokens_in
        total_out += m.tokens_out
        for tc in m.tool_calls:
            if tc.status == Status.PASSED:
                passed += 1
            elif tc.status == Status.FAILED:
                failed += 1
            elif tc.status == Status.CANCELLED:
                cancelled += 1

    for m in messages:
        if m.role == Role.ASSISTANT and m.model:
            c = estimate_cost(m.model, m.tokens_in, m.tokens_out, m.tokens_cached)
            if c is not None:
                total_cost += c
            else:
                cost_is_partial = True

    start = _parse_ts(data.get("startTime", ""))
    end = _parse_ts(data.get("lastUpdated", ""))
    if end == _MIN_TS and messages:
        end = messages[-1].timestamp

    if not models or (cost_is_partial and total_cost == 0.0):
        final_cost = None
    else:
        final_cost = total_cost

    return Transcript(
        messages=messages,
        source_format=source_format,
        session_id=data.get("sessionId"),
        start_time=start,
        end_time=end,
        models=models,
        total_tokens_in=total_in,
        total_tokens_out=total_out,
        total_cost=final_cost,
        cost_is_partial=cost_is_partial,
        tool_stats=ToolStats(passed=passed, failed=failed, cancelled=cancelled),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_gemini_parser.py -v`

- [ ] **Step 5: Commit**

```bash
git add transcript/parsers/gemini.py tests/test_gemini_parser.py
git commit -m "feat: add Gemini CLI JSON parser with token delta calculation"
```

---

### Task 6: Format detection

**Files:**
- Create: `transcript/detect.py`
- Create: `tests/test_detect.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_detect.py
import pytest
from pathlib import Path
from transcript.detect import detect_format

CLAUDE_FIXTURE = str(Path(__file__).parent / "fixtures" / "claude_minimal.jsonl")
GEMINI_FIXTURE = str(Path(__file__).parent / "fixtures" / "gemini_minimal.json")


def test_detect_claude():
    assert detect_format(CLAUDE_FIXTURE) == "claude"


def test_detect_gemini():
    assert detect_format(GEMINI_FIXTURE) == "gemini"


def test_detect_unknown(tmp_path):
    p = tmp_path / "unknown.txt"
    p.write_text("not a log file")
    with pytest.raises(ValueError, match="Could not detect format"):
        detect_format(str(p))


def test_detect_json_without_session_id(tmp_path):
    """A JSON file with messages but no sessionId is not Gemini."""
    p = tmp_path / "fake.json"
    p.write_text('{"messages": []}')
    with pytest.raises(ValueError, match="Could not detect format"):
        detect_format(str(p))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_detect.py -v`

- [ ] **Step 3: Implement detect.py**

```python
# transcript/detect.py
import json

_CLAUDE_TYPES = {"user", "assistant", "system", "progress", "attachment"}


def detect_format(path: str) -> str:
    with open(path) as f:
        raw = f.read()

    # Try Gemini (single JSON with sessionId + messages)
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "messages" in data and "sessionId" in data:
            return "gemini"
    except json.JSONDecodeError:
        pass

    # Try Claude (JSONL with known type fields)
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            if isinstance(entry, dict) and entry.get("type") in _CLAUDE_TYPES:
                return "claude"
        except json.JSONDecodeError:
            continue

    raise ValueError(
        f"Could not detect format: {path} has no 'sessionId' field and no valid JSONL entries with known type"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_detect.py -v`

- [ ] **Step 5: Commit**

```bash
git add transcript/detect.py tests/test_detect.py
git commit -m "feat: add format auto-detection for Claude JSONL and Gemini JSON"
```

---

### Task 7: Markdown renderer

**Files:**
- Create: `transcript/renderers/markdown.py`
- Create: `tests/test_markdown.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_markdown.py
from datetime import datetime, timezone
from dataclasses import dataclass
from transcript.model import Status, Role, ToolCall, Message, ToolStats, Transcript
from transcript.renderers.markdown import render, RenderOptions


def _make_transcript(messages, **kwargs):
    defaults = dict(
        source_format="claude",
        session_id=None,
        start_time=messages[0].timestamp if messages else datetime.min.replace(tzinfo=timezone.utc),
        end_time=messages[-1].timestamp if messages else datetime.min.replace(tzinfo=timezone.utc),
        models={"claude-opus-4-6"},
        total_tokens_in=10000,
        total_tokens_out=500,
        total_cost=0.045,
        cost_is_partial=False,
        tool_stats=ToolStats(passed=1, failed=1, cancelled=0),
    )
    defaults.update(kwargs)
    return Transcript(messages=messages, **defaults)


TS1 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
TS2 = datetime(2026, 1, 1, 10, 0, 5, tzinfo=timezone.utc)


def test_render_summary_header():
    t = _make_transcript([
        Message(role=Role.USER, timestamp=TS1, text=["hello"]),
        Message(role=Role.ASSISTANT, timestamp=TS2, model="claude-opus-4-6",
                tokens_in=10000, tokens_out=500, text=["hi"]),
    ])
    md = render(t)
    assert "# Transcript" in md
    assert "Duration" in md
    assert "claude-opus-4-6" in md
    assert "2 (1 user, 1 assistant)" in md


def test_render_no_thinking():
    t = _make_transcript([
        Message(role=Role.ASSISTANT, timestamp=TS1, model="claude-opus-4-6",
                thinking=["secret thoughts"], text=["visible"]),
    ])
    md = render(t, RenderOptions(show_thinking=False))
    assert "secret thoughts" not in md
    assert "visible" in md


def test_render_no_tools():
    t = _make_transcript([
        Message(role=Role.ASSISTANT, timestamp=TS1, model="claude-opus-4-6",
                text=["visible"], tool_calls=[
                    ToolCall(name="Read", display_name="Read", summary="/f.py",
                             result_summary="10 lines", result_full="content", status=Status.PASSED)
                ]),
    ])
    md = render(t, RenderOptions(show_tools=False))
    assert "Read" not in md


def test_render_no_text():
    t = _make_transcript([
        Message(role=Role.ASSISTANT, timestamp=TS1, model="claude-opus-4-6",
                text=["hidden text"], tool_calls=[
                    ToolCall(name="Read", display_name="Read", summary="/f.py",
                             result_summary="10 lines", result_full="content", status=Status.PASSED)
                ]),
    ])
    md = render(t, RenderOptions(show_text=False))
    assert "hidden text" not in md
    assert "Read" in md


def test_render_no_cost():
    t = _make_transcript([
        Message(role=Role.ASSISTANT, timestamp=TS1, model="claude-opus-4-6",
                tokens_in=10000, tokens_out=500, text=["hi"]),
    ])
    md = render(t, RenderOptions(show_cost=False))
    assert "$" not in md
    assert "↑" not in md


def test_render_expand_tools():
    t = _make_transcript([
        Message(role=Role.ASSISTANT, timestamp=TS1, model="claude-opus-4-6",
                text=["ok"], tool_calls=[
                    ToolCall(name="Bash", display_name="Bash", summary="ls",
                             result_summary="ok", result_full="file1.py\nfile2.py", status=Status.PASSED)
                ]),
    ])
    md = render(t, RenderOptions(expand_tools=True))
    assert "file1.py" in md
    assert "file2.py" in md


def test_render_compaction_marker():
    t = _make_transcript([
        Message(role=Role.USER, timestamp=TS1, text=["before"]),
        Message(role=Role.USER, timestamp=TS1, is_compaction_marker=True, text=["Conversation compacted"]),
        Message(role=Role.USER, timestamp=TS2, text=["after"]),
    ])
    md = render(t)
    assert "conversation compacted" in md.lower()
    assert "before" in md
    assert "after" in md


def test_render_partial_cost():
    t = _make_transcript([
        Message(role=Role.ASSISTANT, timestamp=TS1, model="claude-opus-4-6",
                tokens_in=10000, tokens_out=500, text=["hi"]),
    ], total_cost=0.045, cost_is_partial=True)
    md = render(t)
    assert "partial" in md.lower()


def test_render_empty():
    t = _make_transcript([], models=set(), total_tokens_in=0, total_tokens_out=0,
                          total_cost=None, tool_stats=ToolStats(0, 0, 0))
    md = render(t)
    assert "No messages" in md
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_markdown.py -v`

- [ ] **Step 3: Implement markdown renderer**

```python
# transcript/renderers/markdown.py
from dataclasses import dataclass
from datetime import datetime
from transcript.model import Status, Role, Message, Transcript
from transcript.pricing import estimate_cost


@dataclass
class RenderOptions:
    show_thinking: bool = True
    show_tools: bool = True
    show_text: bool = True
    show_cost: bool = True
    expand_tools: bool = False


def _fmt_tokens(n: int) -> str:
    return f"{n:,}"


def _fmt_cost(cost: float | None) -> str:
    if cost is None:
        return "$?"
    if cost < 0.01:
        return f"${cost:.4f}"
    return f"${cost:.2f}"


def _fmt_duration(start: datetime, end: datetime) -> str:
    total = int((end - start).total_seconds())
    if total < 0:
        return "0s"
    h, r = divmod(total, 3600)
    m, s = divmod(r, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


def _fmt_ts(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def render(transcript: Transcript, options: RenderOptions | None = None) -> str:
    opts = options or RenderOptions()
    msgs = transcript.messages

    if not msgs:
        return "# Transcript\n\nNo messages.\n"

    lines: list[str] = []

    user_count = sum(1 for m in msgs if m.role == Role.USER and not m.is_compaction_marker)
    asst_count = sum(1 for m in msgs if m.role == Role.ASSISTANT)
    total_msgs = user_count + asst_count
    ts = transcript.tool_stats

    lines.append("# Transcript")
    lines.append("")
    lines.append(
        f"- **Duration**: {_fmt_duration(transcript.start_time, transcript.end_time)} "
        f"({_fmt_ts(transcript.start_time)} → {_fmt_ts(transcript.end_time)})"
    )
    lines.append(f"- **Model(s)**: {', '.join(sorted(transcript.models)) or 'unknown'}")
    lines.append(f"- **Messages**: {total_msgs} ({user_count} user, {asst_count} assistant)")

    if opts.show_cost:
        lines.append(f"- **Tool calls**: {ts.passed + ts.failed + ts.cancelled} ({ts.passed} passed, {ts.failed} failed)")
        cost_str = _fmt_cost(transcript.total_cost)
        if transcript.cost_is_partial and transcript.total_cost is not None:
            cost_str += " (partial)"
        lines.append(
            f"- **Tokens**: ↑{_fmt_tokens(transcript.total_tokens_in)} ↓{_fmt_tokens(transcript.total_tokens_out)} · {cost_str}"
        )

    for m in msgs:
        if m.is_compaction_marker:
            lines.append("")
            lines.append("--- conversation compacted ---")
            continue

        lines.append("")
        lines.append("---")
        lines.append("")

        if m.role == Role.USER:
            lines.append(f"## User · {_fmt_ts(m.timestamp)}")
        else:
            header = f"## Assistant · {_fmt_ts(m.timestamp)}"
            if opts.show_cost:
                msg_cost = estimate_cost(m.model or "", m.tokens_in, m.tokens_out, m.tokens_cached)
                header += (
                    f" · ↑{_fmt_tokens(m.tokens_in)} ↓{_fmt_tokens(m.tokens_out)}"
                    f" · {_fmt_cost(msg_cost)}"
                )
            lines.append(header)

        lines.append("")

        if opts.show_thinking:
            for t in m.thinking:
                for tline in t.split("\n"):
                    lines.append(f"> {tline}")
                lines.append("")

        if opts.show_text:
            for t in m.text:
                lines.append(t)
                lines.append("")

        if opts.show_tools and m.tool_calls:
            if opts.expand_tools:
                for tc in m.tool_calls:
                    marker = "x " if tc.status == Status.FAILED else "~ " if tc.status == Status.CANCELLED else "  "
                    lines.append(f"{marker}{tc.display_name}: {tc.summary} → {tc.result_summary}")
                    if tc.result_full:
                        lines.append("")
                        lines.append("```")
                        lines.append(tc.result_full)
                        lines.append("```")
                    lines.append("")
            else:
                lines.append("```")
                for tc in m.tool_calls:
                    lines.append(f"{tc.display_name}: {tc.summary} → {tc.result_summary}")
                lines.append("```")
                lines.append("")

    return "\n".join(lines).rstrip() + "\n"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_markdown.py -v`

- [ ] **Step 5: Commit**

```bash
git add transcript/renderers/markdown.py tests/test_markdown.py
git commit -m "feat: add markdown renderer with content control flags"
```

---

### Task 8: CLI entry point

**Files:**
- Create: `transcript/cli.py`
- Create: `tests/test_cli.py`
- Delete: `transcript.py`, `tests/test_transcript.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_cli.py
import subprocess
from pathlib import Path

VENV_PYTHON = str(Path(__file__).parent.parent / ".venv" / "bin" / "python")
CLI = [VENV_PYTHON, "-m", "transcript"]
CLAUDE_FIXTURE = str(Path(__file__).parent / "fixtures" / "claude_minimal.jsonl")
GEMINI_FIXTURE = str(Path(__file__).parent / "fixtures" / "gemini_minimal.json")


def _run(*args):
    return subprocess.run([*CLI, *args], capture_output=True, text=True,
                          cwd=str(Path(__file__).parent.parent))


def test_claude_auto_detect():
    r = _run(CLAUDE_FIXTURE)
    assert r.returncode == 0
    assert "# Transcript" in r.stdout
    assert "## User" in r.stdout
    assert "## Assistant" in r.stdout


def test_gemini_auto_detect():
    r = _run(GEMINI_FIXTURE)
    assert r.returncode == 0
    assert "# Transcript" in r.stdout
    assert "gemini-2.5-flash" in r.stdout


def test_format_override():
    r = _run("--format", "claude", CLAUDE_FIXTURE)
    assert r.returncode == 0
    assert "# Transcript" in r.stdout


def test_no_thinking():
    r = _run("--no-thinking", CLAUDE_FIXTURE)
    assert r.returncode == 0
    assert "Let me look at auth code" not in r.stdout


def test_no_tools():
    r = _run("--no-tools", CLAUDE_FIXTURE)
    assert r.returncode == 0
    assert "Read:" not in r.stdout


def test_no_text():
    r = _run("--no-text", CLAUDE_FIXTURE)
    assert r.returncode == 0
    assert "I'll read the middleware" not in r.stdout


def test_expand_tools():
    r = _run("--expand-tools", CLAUDE_FIXTURE)
    assert r.returncode == 0
    assert "def authenticate" in r.stdout


def test_output_file(tmp_path):
    out = tmp_path / "out.md"
    r = _run("-o", str(out), CLAUDE_FIXTURE)
    assert r.returncode == 0
    assert out.read_text().startswith("# Transcript")


def test_file_not_found():
    r = _run("/nonexistent/file.jsonl")
    assert r.returncode == 2


def test_parse_error(tmp_path):
    bad = tmp_path / "bad.txt"
    bad.write_text("not a log")
    r = _run(str(bad))
    assert r.returncode == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_cli.py -v`

- [ ] **Step 3: Create `transcript/__main__.py`**

```python
# transcript/__main__.py
from transcript.cli import main
main()
```

- [ ] **Step 4: Implement cli.py**

```python
# transcript/cli.py
import sys
import argparse
from transcript.detect import detect_format
from transcript.parsers.claude import parse as parse_claude
from transcript.parsers.gemini import parse as parse_gemini
from transcript.renderers.markdown import render, RenderOptions


def main():
    parser = argparse.ArgumentParser(
        description="Convert agent logs to readable Markdown transcripts."
    )
    parser.add_argument("input", help="Path to log file")
    parser.add_argument(
        "-f", "--format", choices=["claude", "gemini"],
        help="Log format (auto-detected if omitted)"
    )
    parser.add_argument("-o", "--output", help="Output file (default: stdout)")
    parser.add_argument("--no-thinking", action="store_true", help="Exclude thinking blocks")
    parser.add_argument("--no-tools", action="store_true", help="Exclude tool calls")
    parser.add_argument("--no-text", action="store_true", help="Exclude response text")
    parser.add_argument("--no-cost", action="store_true", help="Exclude cost/token info")
    parser.add_argument("--expand-tools", action="store_true", help="Show full tool output")

    # Handle 'view' subcommand — just strip it for now, TUI comes later
    argv = sys.argv[1:]
    if argv and argv[0] == "view":
        argv = argv[1:]
        # TUI launch will be added in Task 11

    args = parser.parse_args(argv)

    try:
        with open(args.input):
            pass
    except FileNotFoundError:
        print(f"Error: file not found: {args.input}", file=sys.stderr)
        sys.exit(2)

    fmt = args.format
    if not fmt:
        try:
            fmt = detect_format(args.input)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    try:
        if fmt == "claude":
            transcript = parse_claude(args.input)
        else:
            transcript = parse_gemini(args.input)
    except Exception as e:
        print(f"Error: failed to parse {args.input}: {e}", file=sys.stderr)
        sys.exit(1)

    options = RenderOptions(
        show_thinking=not args.no_thinking,
        show_tools=not args.no_tools,
        show_text=not args.no_text,
        show_cost=not args.no_cost,
        expand_tools=args.expand_tools,
    )
    md = render(transcript, options)

    if args.output:
        with open(args.output, "w") as f:
            f.write(md)
    else:
        sys.stdout.write(md)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_cli.py -v`

- [ ] **Step 6: Delete old v1 files**

```bash
rm transcript.py tests/test_transcript.py
```

- [ ] **Step 7: Commit**

```bash
git add transcript/cli.py transcript/__main__.py tests/test_cli.py
git rm transcript.py tests/test_transcript.py
git commit -m "feat: add CLI entry point with auto-detection and content control flags"
```

---

### Task 9: TUI — App shell + conversation panel

**Files:**
- Create: `transcript/tui/app.py`
- Create: `transcript/tui/widgets.py`

This task builds the basic TUI: two-panel layout, conversation rendering with messages/tools/thinking, scrolling, and the `q` keybinding.

- [ ] **Step 1: Implement the app and conversation panel**

`transcript/tui/app.py`:

```python
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer
from textual.containers import Horizontal
from transcript.model import Transcript
from transcript.tui.widgets import ConversationPanel, DetailPanel


class TranscriptApp(App):
    CSS = """
    Horizontal { height: 1fr; }
    ConversationPanel { width: 2fr; }
    DetailPanel { width: 1fr; }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("t", "toggle_thinking", "Thinking"),
        ("h", "cycle_visibility", "Hide"),
        ("tab", "focus_next", "Panel"),
        ("slash", "open_search", "Search"),
        ("question_mark", "show_help", "Help"),
    ]

    def __init__(self, transcript: Transcript):
        super().__init__()
        self.transcript = transcript

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield ConversationPanel(self.transcript)
            yield DetailPanel()
        yield Footer()

    def action_toggle_thinking(self):
        self.query_one(ConversationPanel).toggle_thinking()

    def action_cycle_visibility(self):
        self.query_one(ConversationPanel).cycle_visibility()

    def action_open_search(self):
        pass  # Task 12

    def action_show_help(self):
        pass  # Task 12
```

`transcript/tui/widgets.py`:

```python
from textual.widgets import Static, RichLog
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual import on
from textual.events import Key
from rich.text import Text
from rich.markdown import Markdown
from rich.syntax import Syntax
from transcript.model import Status, Role, Message, Transcript, ToolCall
from transcript.pricing import estimate_cost
from pathlib import Path


class ToolCallWidget(Static):
    """A single tool call line that can be focused and expanded."""

    def __init__(self, tool_call: ToolCall, **kwargs):
        self.tool_call = tool_call
        marker = ""
        if tool_call.status == Status.FAILED:
            marker = "[red]x[/red] "
        elif tool_call.status == Status.CANCELLED:
            marker = "[yellow]~[/yellow] "
        else:
            marker = "  "
        label = f"{marker}{tool_call.display_name}: {tool_call.summary} → {tool_call.result_summary}  [dim]\\[>][/dim]"
        super().__init__(label, **kwargs)
        self.can_focus = True
        if tool_call.status == Status.FAILED:
            self.styles.color = "red"
        elif tool_call.status == Status.CANCELLED:
            self.styles.color = "yellow"


class ThinkingWidget(Static):
    """A collapsible thinking block."""

    def __init__(self, text: str, **kwargs):
        self._full_text = text
        self._collapsed = True
        lines = text.strip().split("\n")
        self._line_count = len(lines)
        super().__init__(self._collapsed_text(), **kwargs)
        self.can_focus = True

    def _collapsed_text(self):
        return f"[dim italic]> Thinking ({self._line_count} lines)  \\[>][/dim italic]"

    def _expanded_text(self):
        lines = self._full_text.strip().split("\n")
        rendered = "\n".join(f"[dim italic]│ {line}[/dim italic]" for line in lines)
        return f"[dim italic]v Thinking[/dim italic]\n{rendered}"

    def toggle(self):
        self._collapsed = not self._collapsed
        self.update(self._collapsed_text() if self._collapsed else self._expanded_text())

    @property
    def collapsed(self):
        return self._collapsed


class ConversationPanel(VerticalScroll):
    """Left panel: scrollable conversation."""

    def __init__(self, transcript: Transcript, **kwargs):
        super().__init__(**kwargs)
        self.transcript = transcript
        self._visibility = 0  # 0=all, 1=assistant, 2=user
        self.can_focus = True

    def compose(self):
        yield self._render_header()
        for msg in self.transcript.messages:
            if msg.is_compaction_marker:
                yield Static("[dim]─── conversation compacted ───[/dim]")
                continue
            yield from self._render_message(msg)

    def _render_header(self):
        t = self.transcript
        ts = t.tool_stats
        total_tools = ts.passed + ts.failed + ts.cancelled
        failed_str = f" ({ts.failed} x)" if ts.failed else ""

        cost_str = ""
        if t.total_cost is not None:
            cost_str = f"${t.total_cost:.2f}" if t.total_cost >= 0.01 else f"${t.total_cost:.4f}"
            if t.cost_is_partial:
                cost_str += " (partial)"
        elif t.total_cost is None:
            cost_str = "$?"

        model_str = ", ".join(sorted(t.models)) or "unknown"
        delta = t.end_time - t.start_time
        total_s = int(delta.total_seconds())
        if total_s >= 3600:
            dur = f"{total_s // 3600}h {(total_s % 3600) // 60}m"
        elif total_s >= 60:
            dur = f"{total_s // 60}m {total_s % 60}s"
        else:
            dur = f"{total_s}s"

        user_c = sum(1 for m in t.messages if m.role == Role.USER and not m.is_compaction_marker)
        asst_c = sum(1 for m in t.messages if m.role == Role.ASSISTANT)

        header = (
            f"[bold]# Transcript[/bold]\n"
            f"[dim]Duration: {dur} · {model_str}\n"
            f"Messages: {user_c + asst_c} · Tools: {total_tools}{failed_str} · {cost_str}[/dim]"
        )
        return Static(header)

    def _render_message(self, msg: Message):
        if self._visibility == 1 and msg.role == Role.USER:
            return
        if self._visibility == 2 and msg.role == Role.ASSISTANT:
            return

        ts_str = msg.timestamp.strftime("%H:%M:%S")
        if msg.role == Role.USER:
            yield Static(f"\n[bold blue]## User · {ts_str}[/bold blue]")
            for t in msg.text:
                yield Static(t)
        else:
            header = f"\n[bold green]## Assistant · {ts_str}[/bold green]"
            if msg.tokens_in or msg.tokens_out:
                header += f" [dim]· ^{msg.tokens_in:,} v{msg.tokens_out:,}[/dim]"
            yield Static(header)

            for t in msg.thinking:
                yield ThinkingWidget(t)

            for t in msg.text:
                yield Static(t)

            for tc in msg.tool_calls:
                yield ToolCallWidget(tc)

    def toggle_thinking(self):
        for w in self.query(ThinkingWidget):
            w.toggle()

    def cycle_visibility(self):
        self._visibility = (self._visibility + 1) % 3
        self._refresh_content()

    def _refresh_content(self):
        # Remove all children and re-compose
        self.remove_children()
        self.mount(self._render_header())
        for msg in self.transcript.messages:
            if msg.is_compaction_marker:
                self.mount(Static("[dim]─── conversation compacted ───[/dim]"))
                continue
            for w in self._render_message(msg):
                self.mount(w)


class DetailPanel(VerticalScroll):
    """Right panel: detail view for expanded tool output or file contents."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.can_focus = True
        self.styles.border = ("solid", "gray")

    def compose(self):
        yield Static("[dim]Select a tool call or thinking block and press Enter to view details[/dim]")

    def show_tool_call(self, tc: ToolCall):
        self.remove_children()
        self.mount(Static(f"[bold]{tc.display_name}: {tc.summary}[/bold]"))
        self.mount(Static(f"{tc.result_summary}"))
        if tc.result_full:
            # Try syntax highlighting for file content
            ext = Path(tc.summary).suffix if "/" in tc.summary else ""
            if ext in (".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java", ".rb", ".sh", ".yaml", ".yml", ".toml", ".json"):
                try:
                    widget = Static(Syntax(tc.result_full, ext.lstrip("."), theme="monokai"))
                    self.mount(widget)
                    return
                except Exception:
                    pass
            if ext in (".md",):
                try:
                    widget = Static(Markdown(tc.result_full))
                    self.mount(widget)
                    return
                except Exception:
                    pass
            self.mount(Static(tc.result_full))

    def show_thinking(self, text: str):
        self.remove_children()
        self.mount(Static("[bold]Thinking[/bold]"))
        self.mount(Static(f"[dim italic]{text}[/dim italic]"))

    def clear_detail(self):
        self.remove_children()
        self.mount(Static("[dim]Select a tool call or thinking block and press Enter to view details[/dim]"))
```

- [ ] **Step 2: Wire TUI into CLI**

Update `transcript/cli.py` — add TUI launch when `view` subcommand is used:

In the section handling `argv[0] == "view"`, after parsing args, add:

```python
# In cli.py, replace the view handling block:
if argv and argv[0] == "view":
    argv = argv[1:]
    args = parser.parse_args(argv)
    # ... file check and parsing same as below ...
    from transcript.tui.app import TranscriptApp
    app = TranscriptApp(transcript)
    app.run()
    return
```

- [ ] **Step 3: Add Enter key handling for expand**

In `app.py`, add key handler to connect focused widget to detail panel:

```python
# In TranscriptApp:
def on_key(self, event: Key):
    if event.key == "enter":
        focused = self.focused
        if isinstance(focused, ToolCallWidget):
            self.query_one(DetailPanel).show_tool_call(focused.tool_call)
        elif isinstance(focused, ThinkingWidget):
            if focused.collapsed:
                focused.toggle()
            else:
                self.query_one(DetailPanel).show_thinking(focused._full_text)
    elif event.key == "escape":
        self.query_one(DetailPanel).clear_detail()
```

Import `ToolCallWidget` and `ThinkingWidget` from widgets in app.py.

- [ ] **Step 4: Manual test**

Run: `.venv/bin/python -m transcript view tests/fixtures/claude_minimal.jsonl`

Verify: two-panel layout renders, messages visible, can scroll with j/k, Enter on tool shows detail, `t` toggles thinking, `q` quits.

- [ ] **Step 5: Commit**

```bash
git add transcript/tui/ transcript/cli.py
git commit -m "feat: add TUI viewer with conversation and detail panels"
```

---

### Task 10: TUI — Search

**Files:**
- Modify: `transcript/tui/app.py`
- Modify: `transcript/tui/widgets.py`

- [ ] **Step 1: Add SearchBar widget**

In `transcript/tui/widgets.py`, add:

```python
from textual.widgets import Input
from textual.containers import Horizontal as HContainer


class SearchBar(HContainer):
    """Bottom search bar with scope selector."""

    SCOPES = ["messages", "thinking", "tools"]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._scope_idx = 0
        self.styles.height = 1
        self.styles.dock = "bottom"

    def compose(self):
        yield Input(placeholder="Search...", id="search-input")
        yield Static(self._scope_label(), id="search-scope")

    def _scope_label(self):
        parts = []
        for i, s in enumerate(self.SCOPES):
            if i == self._scope_idx:
                parts.append(f"[bold][{s}][/bold]")
            else:
                parts.append(s)
        return f"  Scope: {' '.join(parts)}"

    @property
    def scope(self):
        return self.SCOPES[self._scope_idx]

    def cycle_scope(self):
        self._scope_idx = (self._scope_idx + 1) % len(self.SCOPES)
        self.query_one("#search-scope", Static).update(self._scope_label())
```

- [ ] **Step 2: Wire search into app**

In `app.py`, implement `action_open_search` to mount/unmount the SearchBar. On input change, highlight matches in conversation. On Escape, close search.

The search iterates through ConversationPanel children, checks text content against query within the selected scope, and highlights matches using `[reverse]` markup.

- [ ] **Step 3: Manual test**

Run: `.venv/bin/python -m transcript view tests/fixtures/claude_minimal.jsonl`

Verify: `/` opens search bar, typing filters/highlights, Tab cycles scope, Esc closes.

- [ ] **Step 4: Commit**

```bash
git add transcript/tui/
git commit -m "feat: add TUI search with scope selector"
```

---

### Task 11: TUI — Polish and help overlay

**Files:**
- Modify: `transcript/tui/app.py`
- Modify: `transcript/tui/widgets.py`

- [ ] **Step 1: Add help overlay**

Create a `HelpOverlay` widget that shows all keybindings in a centered modal. Mounted on `?`, dismissed on `?` again or Escape.

- [ ] **Step 2: Add CSS polish**

Refine the app CSS for proper panel sizing, borders, colors matching the spec's color table:
- User header: bold blue
- Assistant header: bold green
- Thinking: dim italic with left border
- Failed tool: red
- Cancelled tool: yellow
- Token info: dim
- Search match: inverse

- [ ] **Step 3: Manual test**

Run the TUI against both Claude and Gemini fixtures. Test all keybindings: q, t, h, /, Tab, Enter, Esc, ?.

- [ ] **Step 4: Commit**

```bash
git add transcript/tui/
git commit -m "feat: add TUI help overlay and visual polish"
```

---

### Task 12: Final integration + .gitignore

**Files:**
- Create: `.gitignore`
- Modify: `tests/test_cli.py` (add `view` subcommand existence test)

- [ ] **Step 1: Add .gitignore**

```
__pycache__/
*.pyc
.venv/
.pytest_cache/
dist/
*.egg-info/
```

- [ ] **Step 2: Run full test suite**

Run: `.venv/bin/pytest tests/ -v`

All tests must pass.

- [ ] **Step 3: Manual smoke test with real logs**

```bash
# Claude real log
.venv/bin/python -m transcript ~/.claude/projects/<project>/<session>.jsonl | head -30

# Gemini real log
.venv/bin/python -m transcript ~/.gemini/tmp/<project-hash>/chats/session-<timestamp>.json | head -30

# TUI
.venv/bin/python -m transcript view ~/.claude/projects/<project>/<session>.jsonl
```

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore: add .gitignore and finalize project structure"
```
