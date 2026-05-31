import pytest
from pathlib import Path
from transcript.detect import detect_format

CLAUDE_FIXTURE = str(Path(__file__).parent / "fixtures" / "claude_minimal.jsonl")
GEMINI_FIXTURE = str(Path(__file__).parent / "fixtures" / "gemini_minimal.json")
CODEX_FIXTURE = str(Path(__file__).parent / "fixtures" / "codex_minimal.jsonl")


def test_detect_claude():
    assert detect_format(CLAUDE_FIXTURE) == "claude"


def test_detect_gemini():
    assert detect_format(GEMINI_FIXTURE) == "gemini"


def test_detect_codex():
    assert detect_format(CODEX_FIXTURE) == "codex"


def test_detect_unknown(tmp_path):
    p = tmp_path / "unknown.txt"
    p.write_text("not a log file")
    with pytest.raises(ValueError, match="Could not detect format"):
        detect_format(str(p))


def test_detect_json_without_session_id(tmp_path):
    p = tmp_path / "fake.json"
    p.write_text('{"messages": []}')
    with pytest.raises(ValueError, match="Could not detect format"):
        detect_format(str(p))
