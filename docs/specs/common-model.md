# Common Model

All parsers normalize native agent logs into one common model. Renderers and the TUI consume only this model.

This boundary is what keeps presentation standard across agents: new agent support should first prove how its native log pieces map into these types.

## Types

```python
class Status(Enum):
    PASSED = "passed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class Role(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    DEVELOPER = "developer"

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
    command_name: str | None = None
    content_order: list[tuple[str, int]] = field(default_factory=list)

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

## Field Contracts

`Transcript.messages` contains all visible conversation pieces in chronological order, including pseudo-messages such as compaction markers and local commands.

`Transcript.source_format` is the native parser key, currently `claude`, `gemini`, or `codex`.

`Transcript.session_id` is populated when the native format exposes a stable session identifier: Gemini `sessionId`, Codex `session_meta.payload.id`, and the first Claude Code entry carrying `sessionId`.

`Transcript.start_time` and `Transcript.end_time` are normalized `datetime` values. Missing timestamps use `datetime.min` with UTC timezone.

`Transcript.models` contains the set of assistant model names found in parsed messages. The pseudo-model `<synthetic>` (Claude Code placeholder entries) is excluded from `models` and from cost estimation, so it never makes cost partial; the messages themselves are kept.

`Message.text` contains user-visible message text. It preserves raw local-command XML and other session internals when the native log exposes them as message text.

`Role.SYSTEM` and `Role.DEVELOPER` preserve instruction and runtime-internal messages that are visible in native logs. They are displayed as transcript messages but are not counted as user or assistant conversation turns.

When a native format exposes media without a common media field, parsers may add a short placeholder to `Message.text` so the transcript shows that the media existed.

`Message.thinking` contains native thinking, reasoning, or thought-description blocks when available.

`Message.tool_calls` contains normalized tool calls attached to assistant messages.

`Message.command_name` marks local slash commands or command-output pseudo-messages. These messages are displayed, but are not counted as user messages.

`Message.content_order` preserves interleaving of assistant thinking, text, and tool calls. Renderers must iterate it when non-empty and fall back to thinking, then text, then tools when empty.

`ToolCall.summary` is the short human-readable identifier for the call: file path, command description, search pattern, URL, question, or first meaningful string argument.

`ToolCall.result_summary` is the compact outcome: `ok`, `{n} lines`, `{n} matches`, `HTTP {code}`, `FAILED (exit N)`, a short error, or equivalent native result display.

`ToolCall.result_summary` must always be a string, even if the native result display is structured.

`ToolCall.result_full` is the complete native output used for expansion. It must not be truncated by parsers.

## Parser Contract

Each parser exposes:

```python
def parse(path: str) -> Transcript
```

Each parser is responsible for:

- reading the native log file
- converting native entries into `Message` and `ToolCall` objects
- preserving full visible text and tool output
- computing transcript totals, model set, tool stats, and cost
- handling malformed entries gracefully when possible: native logs are untrusted input, so null or wrong-typed nested fields are treated as missing (empty string, list, dict, or 0) rather than aborting the parse
- warning to stderr for malformed entries that can be skipped, including valid JSON values that are not objects

Parsers should skip native internals only when the relevant agent mapping spec says they are intentionally out of presentation scope.

## Cost Contract

Pricing is stored in `transcript/pricing.py` as input and output USD prices per 1M tokens, keyed by model-name prefix. The prices are a snapshot of the published Anthropic and Google rates as of 2026-10-06 (sources are listed at the top of that file) and are not updated automatically.

A model name is priced by the longest key it starts with. This lets dated ids such as `claude-sonnet-4-5-20250929` resolve to `claude-sonnet-4-5`, and keeps a shorter key from capturing a longer, differently priced family (`gemini-2.5-flash` vs `gemini-2.5-flash-lite`, `claude-opus-5` vs `claude-opus-5-5`).

OpenAI/Codex models are intentionally not priced, so Codex message and transcript cost is unknown (`$?`).

Cached input tokens are treated as free. Cost is:

```text
billable_input = max(0, tokens_in - tokens_cached)
cost = billable_input / 1_000_000 * input_price + tokens_out / 1_000_000 * output_price
```

If a model is unknown, cost for that message is unknown. Transcript cost sums known message costs and sets `cost_is_partial=True` when any message had unknown cost. If all message costs are unknown, `total_cost` is `None`.

## Detection Contract

Format detection is a convenience layer. It must not contain parser-specific normalization logic.

Detection must not crash on hostile input: undecodable JSON, including JSON nested deeply enough to raise `RecursionError`, is treated as "not this format".

Detection runs in this order (`transcript/detect.py`):

1. Gemini CLI: the whole file parses as a single JSON object with `sessionId` and `messages`.
2. Otherwise the file is scanned as JSONL, line by line in order. Blank, malformed, and non-object lines are skipped. The first recognizable line decides the format:
   - Codex CLI/Desktop: `type` is `session_meta` with a non-empty `payload.id`, `response_item` with a non-empty `payload.type`, or `turn_context` / `event_msg` with an object `payload`.
   - Claude Code: `type` is one of `user`, `assistant`, `system`, `progress`, `attachment`.

   Codex types are checked before Claude types on each line. The two type sets do not overlap.
3. If no line is recognizable, detection fails with an error.

`--format claude|gemini|codex` overrides detection.
