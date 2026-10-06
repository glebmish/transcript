# Sources (prices checked 2026-10-06):
#   https://platform.claude.com/docs/en/about-claude/pricing
#   https://ai.google.dev/gemini-api/docs/pricing
#
# (input_price, output_price) per 1M tokens in USD, keyed by model-id prefix.
#
# A model id matches the LONGEST key it starts with, so dated ids such as
# "claude-sonnet-4-5-20250929" resolve to "claude-sonnet-4-5", and
# "gemini-2.5-flash-lite" is not priced as "gemini-2.5-flash".
#
# OpenAI/Codex models are deliberately absent: their cost is reported as
# unknown ("$?").
PRICING = {
    "claude-fable-5-1":         (10.00, 50.00),
    "claude-fable-5":           (10.00, 50.00),
    "claude-opus-5-5":          (4.00,  20.00),
    "claude-opus-5":            (5.00,  25.00),
    "claude-opus-4-8":          (5.00,  25.00),
    "claude-opus-4-7":          (5.00,  25.00),
    "claude-opus-4-6":          (5.00,  25.00),
    "claude-opus-4-5":          (5.00,  25.00),
    "claude-opus-4-1":          (15.00, 75.00),
    "claude-opus-4-0":          (15.00, 75.00),
    "claude-opus-4-20250514":   (15.00, 75.00),  # dated id of claude-opus-4-0
    "claude-sonnet-5-5":        (2.00,  10.00),
    "claude-sonnet-5":          (2.00,  10.00),
    "claude-sonnet-4-6":        (3.00,  15.00),
    "claude-sonnet-4-5":        (3.00,  15.00),
    "claude-sonnet-4-0":        (3.00,  15.00),
    "claude-sonnet-4-20250514": (3.00,  15.00),  # dated id of claude-sonnet-4-0
    "claude-haiku-4-5":         (1.00,   5.00),
    # Gemini 2.5 Pro: <=200k-token prompt tier. The higher >200k-token tier
    # is not modeled, so very long prompts are underestimated.
    "gemini-2.5-pro":           (1.25,  10.00),
    "gemini-2.5-flash":         (0.30,   2.50),
    "gemini-2.5-flash-lite":    (0.10,   0.40),
}

# Longest keys first so the first match is the longest matching prefix.
_PREFIXES = sorted(PRICING, key=len, reverse=True)


def _lookup(model: str) -> tuple[float, float] | None:
    for prefix in _PREFIXES:
        if model.startswith(prefix):
            return PRICING[prefix]
    return None


def estimate_cost(model: str, tokens_in: int, tokens_out: int, tokens_cached: int) -> float | None:
    """Estimate cost in USD. Cached tokens are free. Returns None if model unknown."""
    prices = _lookup(model)
    if prices is None:
        return None
    in_price, out_price = prices
    billable_input = max(0, tokens_in - tokens_cached)
    return billable_input / 1_000_000 * in_price + tokens_out / 1_000_000 * out_price
