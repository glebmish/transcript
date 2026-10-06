"""Make terminal control characters in log-derived text visible but inert.

Logs can contain raw control characters (ESC sequences, OSC 52 clipboard
writes, title changes, C1 controls, lone CR). Writing them to a terminal would
execute them. Since the tool's goal is full visibility, they are not removed:
each one is replaced by a printable stand-in so the reader can still see that
it was there.

- ``\\r\\n`` is normalized to ``\\n`` first.
- C0 controls except ``\\n`` and ``\\t``, plus lone ``\\r``, become their Unicode
  Control Pictures (U+2400 + code), e.g. ESC -> ``␛``.
- DEL becomes ``␡`` (U+2421).
- C1 controls (U+0080-U+009F) become literal escape text such as ``\\x9b``.
"""

import dataclasses

from transcript.model import Message, ToolCall, Transcript

_KEEP = {"\n", "\t"}

_TABLE: dict[int, str] = {}
for _code in range(0x20):
    if chr(_code) not in _KEEP:
        _TABLE[_code] = chr(0x2400 + _code)
_TABLE[0x7F] = "␡"
for _code in range(0x80, 0xA0):
    _TABLE[_code] = f"\\x{_code:02x}"


def sanitize_text(text: str) -> str:
    """Return ``text`` with control characters replaced by visible, inert stand-ins."""
    return text.replace("\r\n", "\n").translate(_TABLE)


def _opt(text: str | None) -> str | None:
    return None if text is None else sanitize_text(text)


def _sanitize_tool_call(tc: ToolCall) -> ToolCall:
    return dataclasses.replace(
        tc,
        name=sanitize_text(tc.name),
        display_name=sanitize_text(tc.display_name),
        summary=sanitize_text(tc.summary),
        result_summary=sanitize_text(tc.result_summary),
        result_full=sanitize_text(tc.result_full),
    )


def _sanitize_message(msg: Message) -> Message:
    return dataclasses.replace(
        msg,
        model=_opt(msg.model),
        thinking=[sanitize_text(t) for t in msg.thinking],
        text=[sanitize_text(t) for t in msg.text],
        tool_calls=[_sanitize_tool_call(tc) for tc in msg.tool_calls],
        command_name=_opt(msg.command_name),
        content_order=list(msg.content_order),
    )


def sanitize_transcript(transcript: Transcript) -> Transcript:
    """Return a copy of ``transcript`` with every log-derived string sanitized."""
    return dataclasses.replace(
        transcript,
        messages=[_sanitize_message(m) for m in transcript.messages],
        session_id=_opt(transcript.session_id),
        models={sanitize_text(m) for m in transcript.models},
    )
