# Markdown Renderer

The Markdown renderer converts the common model into a readable static transcript.

It must follow `docs/specs/presentation.md` for meaning and visibility rules.

## Entry Point

```python
render(transcript: Transcript, options: RenderOptions | None = None) -> str
```

## Options

| Option | Default | Effect |
|---|---|---|
| `show_thinking` | true | Include thinking blocks |
| `show_tools` | true | Include tool calls |
| `show_text` | true | Include message text |
| `show_cost` | true | Include token and cost metadata |
| `expand_tools` | false | Include full tool output |

## Layout

Examples in this file are real output for the fixtures in `tests/fixtures/`. `→` is U+2192, `↑`/`↓` are U+2191/U+2193, and `·` is U+00B7.

The document starts with a summary header (`transcript tests/fixtures/gemini_minimal.json`):

```markdown
# Transcript

- **Duration**: 5m 0s (2026-01-01 10:00:00 → 2026-01-01 10:05:00)
- **Model(s)**: gemini-2.5-flash
- **Messages**: 4 (2 user, 2 assistant)
- **Tool calls**: 2 (1 passed, 0 failed, 1 cancelled)
- **Tokens**: ↑13,000 ↓350 · $0.0024
```

- `Model(s)` is `unknown` when `Transcript.models` is empty.
- `Messages` counts user and assistant messages only. Developer/system messages, local commands, and compaction markers are shown but not counted.
- `Tool calls` is `N (P passed, F failed)`, with `, C cancelled` appended only when `C > 0`.
- `Tokens` shows `$?` when `total_cost` is `None`, and appends ` (partial)` when `cost_is_partial` is true and a cost is known.
- Tool-call and token lines are hidden when `show_cost` is false.

A transcript with no messages renders only:

```markdown
# Transcript

No messages.
```

Each message after the header is preceded by a blank line and a `---` horizontal rule.

User messages render as:

```markdown
## User · 2026-01-01 10:00:00

Help me refactor auth
```

Developer and system messages use the same layout with `## Developer` or `## System`.

Assistant messages render as:

```markdown
## Assistant · 2026-01-01 10:00:05 · ↑10,000 ↓500 · $0.02
```

Token and cost suffixes are hidden when `show_cost` is false. The `· $cost` segment is also omitted for messages without a real model (no model, or Claude Code's `<synthetic>` placeholder), since no API call was priced. An unpriced real model shows `$?`.

## Content Ordering

For assistant messages, use `Message.content_order` when non-empty. This preserves native interleaving (`transcript tests/fixtures/claude_minimal.jsonl`):

```markdown
> Let me look at auth code.

I'll read the middleware.

`Read: /src/auth.py → 84 lines`
```

When `content_order` is empty, render thinking, then text, then tool calls.

## Thinking

Thinking blocks render as Markdown blockquotes, one `> ` per line:

```markdown
> thinking line
> next line
```

They are omitted when `show_thinking` is false.

## Tool Calls

Each tool call is `display_name: summary → result_summary`.

With `content_order`, collapsed tool calls render one inline code span per call:

```markdown
`Read: /src/auth.py → 84 lines`
```

When `content_order` is empty, all tool calls of the message render as one fenced batch after the text (a `claude_thinking.jsonl` message with `content_order` cleared):

````markdown
```
Read: /requirements.txt → ok
Read: /tests/test_auth.py → ok
```
````

With `expand_tools`, each call renders as a line with a status prefix, then the full output in a fence when `result_full` is non-empty (`transcript tests/fixtures/claude_minimal.jsonl --expand-tools`):

````markdown
x Bash: Run tests → FAILED (exit 1)

```
FAILED test_auth.py::test_jwt
AssertionError: expected 200 got 401
```
````

The prefix is `x ` for `FAILED`, `~ ` for `CANCELLED`, and two spaces for `PASSED`. Expanded calls follow `content_order` when present, otherwise they follow the text in list order.

With `expand_tools`, output must not be truncated.

Log content must never be able to close a code span or fence early and break the rest of the document:

- Fences (expanded output and batched compact lines) use one backtick more than the longest backtick run in the content, minimum 3. Output containing a ```` ``` ```` block gets a ```` ```` ```` fence.
- Inline code spans use one backtick more than the longest backtick run in the content. When the content starts or ends with a backtick, it is padded with one space on each side, per CommonMark.

## Control Characters

The final rendered string is passed through `sanitize_text` (see "Control Characters" in `docs/specs/presentation.md`), so stdout, `-o` files, and `--pretty` output never contain raw control characters from the log.

Fenced and inline code spans are sized so log content cannot close them early; see "Tool Calls".

## Special Messages

Compaction markers render as:

```markdown
--- conversation compacted ---
```

Local commands render as a timestamped italic line and are not counted as user messages. Their raw text is not repeated:

```markdown
*`/model` · 2026-01-01 10:00:00*
```
