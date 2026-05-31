import json

_CLAUDE_TYPES = {"user", "assistant", "system", "progress", "attachment"}
_CODEX_TYPES = {"session_meta", "turn_context", "response_item", "event_msg"}


def detect_format(path: str) -> str:
    """Auto-detect log format. Returns 'claude', 'gemini', or 'codex'. Raises ValueError if unknown."""
    with open(path) as f:
        raw = f.read()

    # Try Gemini (single JSON with sessionId + messages)
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "messages" in data and "sessionId" in data:
            return "gemini"
    except json.JSONDecodeError:
        pass

    # Try JSONL formats with known type fields
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            if not isinstance(entry, dict):
                continue
            entry_type = entry.get("type")
            payload = entry.get("payload")
            if entry_type in _CODEX_TYPES and isinstance(payload, dict):
                if entry_type == "session_meta" and payload.get("id"):
                    return "codex"
                if entry_type == "response_item" and payload.get("type"):
                    return "codex"
                if entry_type in ("turn_context", "event_msg"):
                    return "codex"
            if entry_type in _CLAUDE_TYPES:
                return "claude"
        except json.JSONDecodeError:
            continue

    raise ValueError(
        f"Could not detect format: {path} has no 'sessionId' field and no valid JSONL entries with known type"
    )
