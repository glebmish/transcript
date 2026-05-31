import json

_CLAUDE_TYPES = {"user", "assistant", "system", "progress", "attachment"}


def detect_format(path: str) -> str:
    """Auto-detect log format. Returns 'claude' or 'gemini'. Raises ValueError if unknown."""
    with open(path) as f:
        raw = f.read()

    # Try Gemini (single JSON with sessionId + messages)
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "messages" in data and "sessionId" in data:
            return "gemini"
    except json.JSONDecodeError:
        pass

    # Try Claude (JSONL with known type fields)
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            if isinstance(entry, dict) and entry.get("type") in _CLAUDE_TYPES:
                return "claude"
        except json.JSONDecodeError:
            continue

    raise ValueError(
        f"Could not detect format: {path} has no 'sessionId' field and no valid JSONL entries with known type"
    )
