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
