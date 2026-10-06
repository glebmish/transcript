"""Small helpers shared by the native-log parsers.

Native logs are untrusted input: any nested field may be missing, null, or of
an unexpected type. These coercions let parsers degrade to empty values instead
of aborting the whole parse.
"""


def as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def as_list(value) -> list:
    return value if isinstance(value, list) else []


def as_str(value) -> str:
    return value if isinstance(value, str) else ""


def as_int(value) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


# Claude Code writes this pseudo-model on placeholder assistant entries
# (interrupts, API errors). It is not a real model and made no API call.
SYNTHETIC_MODEL = "<synthetic>"


def is_real_model(model: str | None) -> bool:
    """True for a model name that should be listed and priced."""
    return bool(model) and model != SYNTHETIC_MODEL
