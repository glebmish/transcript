# Common Model & Representation

## Overview

All parsers normalize raw log data into a common model. All renderers and the TUI consume only this model. This is the single boundary between input formats and output modes.

## Data Model

```python
class Status(Enum):
    PASSED = "passed"
    FAILED = "failed"
    CANCELLED = "cancelled"  # Gemini only — user rejected permission

class Role(Enum):
    USER = "user"
    ASSISTANT = "assistant"

@dataclass
class ToolCall:
    name: str              # internal tool name (e.g. "read_file", "Bash")
    display_name: str      # user-facing name (e.g. "ReadFile", "Bash")
    summary: str           # key param (file path, command, pattern)
    result_summary: str    # compact result ("84 lines", "ok", "FAILED (exit 1)")
    result_full: str       # full tool output for TUI expansion
    status: Status
    duration_ms: int | None

@dataclass
class Message:
    role: Role
    timestamp: datetime
    model: str | None      # only on assistant messages
    tokens_in: int
    tokens_out: int
    tokens_cached: int     # cache read hits
    tokens_thinking: int   # thinking token count (Gemini tracks separately)
    thinking: list[str]    # thinking/reasoning text blocks
    text: list[str]        # response text blocks
    tool_calls: list[ToolCall]

@dataclass
class ToolStats:
    passed: int
    failed: int
    cancelled: int

@dataclass
class Transcript:
    messages: list[Message]
    source_format: str     # "claude" or "gemini"
    session_id: str | None
    start_time: datetime
    end_time: datetime
    models: set[str]       # deduplicated model names
    total_tokens_in: int
    total_tokens_out: int
    total_cost: float | None
    tool_stats: ToolStats
```

## Parsing Contract

Each parser exposes a single function:

```python
def parse(path: str) -> Transcript
```

The parser is responsible for:
- Reading the raw log file
- Normalizing all entries into `Message` objects
- Filling `result_full` from raw tool output data
- Computing `Transcript`-level summaries (totals, models, cost)
- Handling malformed entries gracefully (skip with warning to stderr)

## Cost Estimation

Cost is computed per-message and aggregated on the `Transcript`. Pricing is a simple dict of `(input_price, output_price)` per 1M tokens, keyed by model name prefix:

```python
PRICING = {
    "claude-opus-4-6":        (15.00, 75.00),
    "claude-sonnet-4-6":      (3.00,  15.00),
    "claude-haiku-4-5":       (0.80,   4.00),
    "gemini-2.5-pro":         (1.25,  10.00),
    "gemini-2.5-flash":       (0.15,   0.60),
    "gemini-3-flash-preview": (0.15,   0.60),
}
```

Model names are matched by prefix (e.g. `"claude-opus-4-6-20250618"` matches `"claude-opus-4-6"`). If any message has an unknown model, `total_cost` is `None` (partial cost would be misleading).

## Format Detection

Auto-detection for CLI convenience:

1. Try `json.load()` — if it succeeds and has a top-level `messages` array, it's Gemini.
2. Otherwise try reading line-by-line as JSONL — if first valid line has `type` field with `"user"` or `"assistant"`, it's Claude.
3. If neither works, raise an error.

A `--format` flag overrides auto-detection.

## Package Structure

```
transcript/
    model.py          # Status, Role, ToolCall, Message, ToolStats, Transcript
    pricing.py        # PRICING dict and estimate_cost()
    detect.py         # format auto-detection
    parsers/
        claude.py     # parse(path) -> Transcript
        gemini.py     # parse(path) -> Transcript
    renderers/
        markdown.py   # render(transcript, options) -> str
    tui/
        app.py        # textual Application
        widgets/      # conversation panel, detail panel, search
    cli.py            # entry point, argparse
```
