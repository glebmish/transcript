from typing import NamedTuple

from transcript.model import Message

# Sources (prices checked 2026-10-06):
#   https://platform.claude.com/docs/en/about-claude/pricing
#   https://ai.google.dev/gemini-api/docs/pricing
#
# USD per 1M tokens, keyed by model-id prefix. Every price is written out as a
# literal so this table can be checked line by line against the sources and
# the README.
#
# Cache rules the literals follow:
#   Anthropic: cache writes cost 1.25x input (5-minute TTL) or 2x input
#     (1-hour TTL). Cache reads cost 0.1x input, except claude-fable-5-1
#     ($0.25) and claude-opus-5-5 ($0.20).
#   Gemini 2.5: cached input costs 0.1x input. There is no write charge:
#     Gemini CLI relies on implicit caching, and storage fees apply only to
#     explicit caches, which the logs do not show.
#
# A model id matches the LONGEST key it starts with, so dated ids such as
# "claude-sonnet-4-5-20250929" resolve to "claude-sonnet-4-5", and
# "gemini-2.5-flash-lite" is not priced as "gemini-2.5-flash".
#
# OpenAI/Codex models are deliberately absent: their cost is reported as
# unknown ("$?").


class Prices(NamedTuple):
    input: float
    output: float
    cache_read: float
    cache_write_5m: float
    cache_write_1h: float


PRICING: dict[str, Prices] = {
    # Prices(input, output, cache_read, cache_write_5m, cache_write_1h)
    #                                  input  output read   5m     1h
    "claude-fable-5-1":         Prices(10.00, 50.00, 0.25,  12.50, 20.00),
    "claude-fable-5":           Prices(10.00, 50.00, 1.00,  12.50, 20.00),
    "claude-opus-5-5":          Prices(4.00,  20.00, 0.20,  5.00,  8.00),
    "claude-opus-5":            Prices(5.00,  25.00, 0.50,  6.25,  10.00),
    "claude-opus-4-8":          Prices(5.00,  25.00, 0.50,  6.25,  10.00),
    "claude-opus-4-7":          Prices(5.00,  25.00, 0.50,  6.25,  10.00),
    "claude-opus-4-6":          Prices(5.00,  25.00, 0.50,  6.25,  10.00),
    "claude-opus-4-5":          Prices(5.00,  25.00, 0.50,  6.25,  10.00),
    "claude-opus-4-1":          Prices(15.00, 75.00, 1.50,  18.75, 30.00),
    "claude-opus-4-0":          Prices(15.00, 75.00, 1.50,  18.75, 30.00),
    "claude-opus-4-20250514":   Prices(15.00, 75.00, 1.50,  18.75, 30.00),  # dated id of claude-opus-4-0
    "claude-sonnet-5-5":        Prices(2.00,  10.00, 0.20,  2.50,  4.00),
    "claude-sonnet-5":          Prices(2.00,  10.00, 0.20,  2.50,  4.00),
    "claude-sonnet-4-6":        Prices(3.00,  15.00, 0.30,  3.75,  6.00),
    "claude-sonnet-4-5":        Prices(3.00,  15.00, 0.30,  3.75,  6.00),
    "claude-sonnet-4-0":        Prices(3.00,  15.00, 0.30,  3.75,  6.00),
    "claude-sonnet-4-20250514": Prices(3.00,  15.00, 0.30,  3.75,  6.00),  # dated id of claude-sonnet-4-0
    "claude-haiku-4-5":         Prices(1.00,  5.00,  0.10,  1.25,  2.00),
    # Gemini 2.5 Pro: <=200k-token prompt tier. The higher >200k-token tier
    # is not modeled, so very long prompts are underestimated.
    "gemini-2.5-pro":           Prices(1.25,  10.00, 0.125, 0.00,  0.00),
    "gemini-2.5-flash":         Prices(0.30,  2.50,  0.03,  0.00,  0.00),
    # flash-lite's cached rate follows the same 10%-of-input rule.
    "gemini-2.5-flash-lite":    Prices(0.10,  0.40,  0.01,  0.00,  0.00),
}

# Longest keys first so the first match is the longest matching prefix.
_PREFIXES = sorted(PRICING, key=len, reverse=True)


def _lookup(model: str) -> Prices | None:
    for prefix in _PREFIXES:
        if model.startswith(prefix):
            return PRICING[prefix]
    return None


def estimate_cost(
    model: str,
    tokens_in: int,
    tokens_out: int,
    cache_read: int = 0,
    cache_write_5m: int = 0,
    cache_write_1h: int = 0,
) -> float | None:
    """Estimate cost in USD. Returns None if the model is unknown.

    tokens_in is the full input context (uncached + cache writes + cache reads).
    Negative counts are treated as 0, and the uncached part never goes below 0.
    """
    prices = _lookup(model)
    if prices is None:
        return None
    tokens_out, cache_read, cache_write_5m, cache_write_1h = (
        max(0, n) for n in (tokens_out, cache_read, cache_write_5m, cache_write_1h)
    )
    uncached = max(0, tokens_in - cache_read - cache_write_5m - cache_write_1h)
    return (
        uncached * prices.input
        + cache_write_5m * prices.cache_write_5m
        + cache_write_1h * prices.cache_write_1h
        + cache_read * prices.cache_read
        + tokens_out * prices.output
    ) / 1_000_000


def message_cost(msg: Message) -> float | None:
    """estimate_cost() for one message's model and token fields."""
    return estimate_cost(
        msg.model or "",
        msg.tokens_in,
        msg.tokens_out,
        cache_read=msg.tokens_cache_read,
        cache_write_5m=msg.tokens_cache_write_5m,
        cache_write_1h=msg.tokens_cache_write_1h,
    )
