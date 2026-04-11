from transcript.pricing import estimate_cost


def test_opus_pricing():
    cost = estimate_cost("claude-opus-4-6", tokens_in=1_000_000, tokens_out=1_000_000, tokens_cached=0)
    assert cost == 5.00 + 25.00


def test_prefix_match():
    cost = estimate_cost("claude-opus-4-6-20250618", tokens_in=1_000_000, tokens_out=0, tokens_cached=0)
    assert cost == 5.00


def test_cache_aware():
    cost = estimate_cost("claude-opus-4-6", tokens_in=1_000_000, tokens_out=0, tokens_cached=800_000)
    assert cost == 200_000 / 1_000_000 * 5.00


def test_gemini_pricing():
    cost = estimate_cost("gemini-2.5-flash", tokens_in=1_000_000, tokens_out=1_000_000, tokens_cached=0)
    assert cost == 0.30 + 2.50


def test_unknown_model():
    assert estimate_cost("unknown-model", 1000, 1000, 0) is None


def test_sonnet_pricing():
    cost = estimate_cost("claude-sonnet-4-6", tokens_in=1_000_000, tokens_out=1_000_000, tokens_cached=0)
    assert cost == 3.00 + 15.00


def test_haiku_pricing():
    cost = estimate_cost("claude-haiku-4-5", tokens_in=1_000_000, tokens_out=1_000_000, tokens_cached=0)
    assert cost == 1.00 + 5.00
