import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))
from transcript import estimate_cost, parse_claude, parse_gemini, render_markdown, Message, ToolCall

CLAUDE_LOG = (
    "~/.claude/projects/"
    "<project>/"
    "<session>.jsonl"
)
GEMINI_LOG = (
    "~/projects/<project>/chats/"
    "session-<timestamp>.json"
)


# --- Cost estimation ---

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


# --- Claude parser ---

def test_parse_claude_real():
    msgs = parse_claude(CLAUDE_LOG)
    assert len(msgs) > 0
    assert msgs[0].role == "user"
    assert len(msgs[0].text) > 0
    assistant_msgs = [m for m in msgs if m.role == "assistant"]
    assert len(assistant_msgs) > 0
    has_tools = any(m.tool_calls for m in assistant_msgs)
    assert has_tools
    for m in assistant_msgs:
        for tc in m.tool_calls:
            assert tc.name
            assert tc.result
            assert isinstance(tc.passed, bool)


# --- Gemini parser ---

def test_parse_gemini_real():
    msgs = parse_gemini(GEMINI_LOG)
    assert len(msgs) > 0
    first_user = next(m for m in msgs if m.role == "user")
    assert len(first_user.text) > 0
    assistant_msgs = [m for m in msgs if m.role == "assistant"]
    assert len(assistant_msgs) > 0
    has_tools = any(m.tool_calls for m in assistant_msgs)
    assert has_tools
    has_thinking = any(m.thinking for m in assistant_msgs)
    assert has_thinking
    assert all(m.model for m in assistant_msgs)


# --- Renderer ---

def test_render_basic():
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
    assert "# Transcript" in md
    assert "Duration" in md
    assert "claude-opus-4-6" in md
    assert "2 (1 user, 1 assistant)" in md
    assert "2 (1 passed, 1 failed)" in md
    assert "## User" in md
    assert "Hello, help me refactor auth" in md
    assert "## Assistant" in md
    assert "↑12,000" in md
    assert "↓1,200" in md
    assert "> Let me look at the auth code first." in md
    assert "Read: /src/auth.py → 84 lines" in md
    assert "Bash: pytest tests/ → FAILED (exit 1)" in md
    assert "---" in md


# --- CLI e2e ---

def test_cli_claude_e2e():
    result = subprocess.run(
        ["python", "transcript.py", "--format", "claude", CLAUDE_LOG],
        capture_output=True, text=True, cwd=str(Path(__file__).parent.parent)
    )
    assert result.returncode == 0
    md = result.stdout
    assert "# Transcript" in md
    assert "## User" in md
    assert "## Assistant" in md
    assert "---" in md

def test_cli_gemini_e2e():
    result = subprocess.run(
        ["python", "transcript.py", "--format", "gemini", GEMINI_LOG],
        capture_output=True, text=True, cwd=str(Path(__file__).parent.parent)
    )
    assert result.returncode == 0
    md = result.stdout
    assert "# Transcript" in md
    assert "## User" in md
    assert "## Assistant" in md
    assert "gemini-3-flash-preview" in md
