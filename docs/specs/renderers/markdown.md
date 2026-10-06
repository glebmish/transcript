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

The document starts with:

```markdown
# Transcript

- **Duration**: ...
- **Model(s)**: ...
- **Messages**: ...
- **Tool calls**: ...
- **Tokens**: ...
```

Tool-call and token lines are hidden when `show_cost` is false.

Messages are separated by horizontal rules.

User messages render as:

```markdown
## User · YYYY-MM-DD HH:MM:SS

message text
```

Assistant messages render as:

```markdown
## Assistant · YYYY-MM-DD HH:MM:SS · ↑in ↓out · $cost
```

Token and cost suffixes are hidden when `show_cost` is false.

## Content Ordering

For assistant messages, use `Message.content_order` when non-empty. This preserves native interleaving:

```markdown
assistant text

`Read: /file.py -> 10 lines`

more assistant text
```

When `content_order` is empty, render thinking, then text, then tool calls.

## Thinking

Thinking blocks render as Markdown blockquotes:

```markdown
> thinking line
> next line
```

They are omitted when `show_thinking` is false.

## Tool Calls

Collapsed tool calls render compactly:

```markdown
`Read: /src/auth.py -> 84 lines`
```

When `content_order` is unavailable and tools are rendered as a batch, they may appear in a fenced block:

```markdown
Read: /src/auth.py -> 84 lines
Bash: pytest tests/ -> FAILED (exit 1)
```

Expanded tool calls render the compact line followed by full output:

````markdown
Bash: pytest tests/ -> FAILED (exit 1)

```
full output
```
````

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

Local commands render as timestamped italic command entries and are not counted as user messages.
