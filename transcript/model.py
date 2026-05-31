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
    # Tracks interleaved content order: ("thinking", idx), ("text", idx), ("tool", idx)
    # When non-empty, renderers should iterate this instead of separate lists.
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
