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


def _per_million(model):
    return estimate_cost(model, tokens_in=1_000_000, tokens_out=1_000_000, tokens_cached=0)


def test_longest_prefix_wins_for_opus():
    # claude-opus-5 is a prefix of claude-opus-5-5; the longer key must win.
    assert _per_million("claude-opus-5-5") == 4.00 + 20.00
    assert _per_million("claude-opus-5-5-20260901") == 4.00 + 20.00
    assert _per_million("claude-opus-5") == 5.00 + 25.00


def test_longest_prefix_wins_for_sonnet():
    assert _per_million("claude-sonnet-5-5-20261001") == 2.00 + 10.00
    assert _per_million("claude-sonnet-5") == 2.00 + 10.00


def test_flash_lite_not_priced_as_flash():
    assert _per_million("gemini-2.5-flash-lite") == 0.10 + 0.40
    assert _per_million("gemini-2.5-flash-lite-preview-06-17") == 0.10 + 0.40
    assert _per_million("gemini-2.5-flash") == 0.30 + 2.50


def test_dated_suffix_id():
    assert _per_million("claude-sonnet-4-5-20250929") == 3.00 + 15.00


def test_legacy_dated_ids():
    assert _per_million("claude-opus-4-20250514") == 15.00 + 75.00
    assert _per_million("claude-sonnet-4-20250514") == 3.00 + 15.00
    assert _per_million("claude-opus-4-1-20250805") == 15.00 + 75.00


def test_current_price_table():
    expected = {
        "claude-fable-5-1": (10.00, 50.00),
        "claude-fable-5": (10.00, 50.00),
        "claude-opus-4-8": (5.00, 25.00),
        "claude-opus-4-7": (5.00, 25.00),
        "claude-opus-4-5": (5.00, 25.00),
        "claude-opus-4-0": (15.00, 75.00),
        "claude-sonnet-4-0": (3.00, 15.00),
        "gemini-2.5-pro": (1.25, 10.00),
    }
    for model, (in_price, out_price) in expected.items():
        assert _per_million(model) == in_price + out_price, model


def test_openai_models_are_unknown():
    assert estimate_cost("gpt-5.5", 1000, 1000, 0) is None
    assert estimate_cost("gpt-5-codex", 1000, 1000, 0) is None
