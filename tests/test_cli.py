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
