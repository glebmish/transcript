# Contributing

## Dev setup

Requires Python 3.12+.

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip          # --group needs pip >= 25.1
.venv/bin/pip install -e . --group dev       # package + pytest + ruff
.venv/bin/pytest tests/ -q
.venv/bin/ruff check .
```

CI (`.github/workflows/ci.yml`) runs the same two checks on every push to `main` and every pull request: ruff once, and pytest on Linux with Python 3.12, 3.13 and 3.14, on macOS with 3.14, and on Linux 3.12 against the lowest supported `textual`/`rich`. `ruff check --fix .` fixes most lint findings automatically.

Run the tool from the checkout with `.venv/bin/transcript <logfile>` or `.venv/bin/transcript view <logfile>`.

## Rules

- **Specs are part of the change.** Behavior is described in `docs/specs/`. When you change how a format is parsed or how something is rendered, update the spec that owns that rule in the same change (see `docs/specs/README.md` for which file owns what).
- **Synthetic fixtures only.** Test data in `tests/fixtures/` and inline test logs must be made up. Never commit a real Claude Code, Gemini CLI or Codex log, even trimmed: real sessions contain private conversations, file contents, paths, and sometimes credentials.

## Guides

- Adding a new agent log format: the checklist in `docs/specs/agents/README.md`.
- Checking the TUI in a real terminal: `docs/validation/tui-smoke-test.md`.
- The `.claude/skills/` and `.agents/skills/` trees are optional maintainer tooling for coding agents; see "Agent skill trees" in `CLAUDE.md`. You don't need them to build, test or use the tool.
