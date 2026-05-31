# (input_price, output_price) per 1M tokens in USD
PRICING = {
    "claude-opus-4-6":   (5.00,  25.00),
    "claude-sonnet-4-6": (3.00,  15.00),
    "claude-haiku-4-5":  (1.00,   5.00),
    "gemini-2.5-pro":    (1.00,  10.00),
    "gemini-2.5-flash":  (0.30,   2.50),
}


def estimate_cost(model: str, tokens_in: int, tokens_out: int, tokens_cached: int) -> float | None:
    """Estimate cost in USD. Cached tokens are free. Returns None if model unknown."""
    for prefix, (in_price, out_price) in PRICING.items():
        if model == prefix or model.startswith(prefix):
            billable_input = max(0, tokens_in - tokens_cached)
            return billable_input / 1_000_000 * in_price + tokens_out / 1_000_000 * out_price
    return None
