import subprocess
import sys
from pathlib import Path

# Run the CLI with the interpreter running pytest, so the tests work in any
# venv (local .venv, CI, tox) rather than only in ./.venv.
CLI = [sys.executable, "-m", "transcript"]
CLAUDE_FIXTURE = str(Path(__file__).parent / "fixtures" / "claude_minimal.jsonl")
GEMINI_FIXTURE = str(Path(__file__).parent / "fixtures" / "gemini_minimal.json")
CODEX_FIXTURE = str(Path(__file__).parent / "fixtures" / "codex_minimal.jsonl")


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


def test_codex_auto_detect():
    r = _run(CODEX_FIXTURE)
    assert r.returncode == 0
    assert "# Transcript" in r.stdout
    assert "## Developer" in r.stdout
    assert "gpt-5.5" in r.stdout


def test_format_override():
    r = _run("--format", "claude", CLAUDE_FIXTURE)
    assert r.returncode == 0
    assert "# Transcript" in r.stdout


def test_codex_format_override():
    r = _run("--format", "codex", CODEX_FIXTURE)
    assert r.returncode == 0
    assert "exec_command" in r.stdout


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


def test_deeply_nested_json_reports_clean_error(tmp_path):
    deep = tmp_path / "deep.json"
    deep.write_text("[" * 200_000)
    r = _run(str(deep))
    assert r.returncode == 1
    assert "Traceback" not in r.stderr
    assert "Error" in r.stderr


def test_stdout_has_no_terminal_escapes(tmp_path):
    import json as _json
    osc52 = "\x1b]52;c;ZWNobyBwd25lZAo=\x1b\\"
    log = tmp_path / "evil.jsonl"
    log.write_text("\n".join(_json.dumps(e) for e in [
        {"type": "user", "timestamp": "2026-01-01T10:00:00Z", "message": {"role": "user", "content": f"hi {osc52}"}},
        {"type": "assistant", "timestamp": "2026-01-01T10:00:01Z", "message": {
            "id": "m1", "role": "assistant", "model": "claude-sonnet-4-6",
            "content": [{"type": "thinking", "thinking": f"t {osc52}"}, {"type": "text", "text": f"a {osc52}"}],
            "usage": {"input_tokens": 1, "output_tokens": 1}}},
    ]))
    for extra in ([], ["--pretty"], ["--expand-tools"]):
        r = _run(*extra, str(log))
        assert r.returncode == 0
        assert "\x1b]52" not in r.stdout
    out = tmp_path / "out.md"
    r = _run("-o", str(out), str(log))
    assert r.returncode == 0
    assert "\x1b" not in out.read_text()


def test_utf8_input_and_output_under_non_utf8_locale(tmp_path):
    import json as _json
    import os
    text = "café → 日本"
    log = tmp_path / "unicode.jsonl"
    log.write_text(_json.dumps({
        "type": "user", "timestamp": "2026-01-01T10:00:00Z",
        "message": {"role": "user", "content": text},
    }, ensure_ascii=False), encoding="utf-8")
    env = {**os.environ, "PYTHONUTF8": "0", "LC_ALL": "en_US.ISO8859-1", "LANG": "en_US.ISO8859-1"}
    env.pop("PYTHONIOENCODING", None)

    r = subprocess.run([*CLI, str(log)], capture_output=True, env=env,
                       cwd=str(Path(__file__).parent.parent))
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert text in r.stdout.decode("utf-8")

    out = tmp_path / "out.md"
    r = subprocess.run([*CLI, "-o", str(out), str(log)], capture_output=True, env=env,
                       cwd=str(Path(__file__).parent.parent))
    assert r.returncode == 0
    assert text in out.read_text(encoding="utf-8")


def test_directory_input_reports_clean_error(tmp_path):
    r = _run(str(tmp_path))
    assert r.returncode == 2
    assert "Traceback" not in r.stderr
    assert "Error" in r.stderr


def test_unwritable_output_reports_clean_error(tmp_path):
    r = _run("-o", str(tmp_path / "missing-dir" / "out.md"), CLAUDE_FIXTURE)
    assert r.returncode == 1
    assert "Traceback" not in r.stderr
    assert "Error" in r.stderr


def test_help_mentions_view_subcommand():
    r = _run("--help")
    assert r.returncode == 0
    assert "transcript view" in r.stdout
