from datetime import datetime, timezone

import pytest

from transcript.model import Message, Role
from transcript.pricing import PRICING, estimate_cost, message_cost


def test_opus_pricing():
    cost = estimate_cost("claude-opus-4-6", tokens_in=1_000_000, tokens_out=1_000_000)
    assert cost == 5.00 + 25.00


def test_prefix_match():
    cost = estimate_cost("claude-opus-4-6-20250618", tokens_in=1_000_000, tokens_out=0)
    assert cost == 5.00


def test_anthropic_heavy_cache_session():
    # 208 uncached + 274,000 5m cache writes + 18.2M cache reads, 79,000 output.
    # claude-opus-4-6: $5 in, $6.25 5m write, $0.50 read, $25 out.
    uncached, write_5m, read, out = 208, 274_000, 18_200_000, 79_000
    cost = estimate_cost(
        "claude-opus-4-6",
        tokens_in=uncached + write_5m + read,
        tokens_out=out,
        cache_read=read,
        cache_write_5m=write_5m,
    )
    expected = (208 * 5 + 274_000 * 6.25 + 18_200_000 * 0.5 + 79_000 * 25) / 1e6
    assert cost == pytest.approx(expected)
    assert round(cost, 2) == 12.79


def test_cache_write_1h_costs_more_than_5m():
    five_min = estimate_cost("claude-opus-4-6", tokens_in=100_000, tokens_out=0, cache_write_5m=100_000)
    one_hour = estimate_cost("claude-opus-4-6", tokens_in=100_000, tokens_out=0, cache_write_1h=100_000)
    assert five_min == pytest.approx(100_000 * 5.00 * 1.25 / 1e6)  # $0.625
    assert one_hour == pytest.approx(100_000 * 5.00 * 2.0 / 1e6)  # $1.00


def _read_cost(model):
    """Cost of 1M tokens that were all cache reads."""
    return estimate_cost(model, tokens_in=1_000_000, tokens_out=0, cache_read=1_000_000)


def test_cache_read_rates():
    assert _read_cost("claude-opus-4-6") == pytest.approx(0.50)
    assert _read_cost("claude-opus-5") == pytest.approx(0.50)
    assert _read_cost("claude-sonnet-5-5") == pytest.approx(0.20)
    assert _read_cost("claude-fable-5") == pytest.approx(1.00)
    assert _read_cost("claude-haiku-4-5") == pytest.approx(0.10)


def test_cache_read_exceptions_opus_5_5_and_fable_5_1():
    assert _read_cost("claude-opus-5-5") == pytest.approx(0.20)
    assert _read_cost("claude-opus-5-5-20260901") == pytest.approx(0.20)
    assert _read_cost("claude-fable-5-1") == pytest.approx(0.25)


def test_gemini_cached_input_is_ten_percent():
    assert _read_cost("gemini-2.5-pro") == pytest.approx(0.125)
    assert _read_cost("gemini-2.5-flash") == pytest.approx(0.03)
    assert _read_cost("gemini-2.5-flash-lite") == pytest.approx(0.01)
    # 800k cached + 200k uncached on gemini-2.5-pro: 0.8 * 0.125 + 0.2 * 1.25
    cost = estimate_cost("gemini-2.5-pro", tokens_in=1_000_000, tokens_out=0, cache_read=800_000)
    assert cost == pytest.approx(0.35)


def test_gemini_has_no_cache_write_charge():
    for model in ("gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"):
        prices = PRICING[model]
        assert prices.cache_write_5m == 0
        assert prices.cache_write_1h == 0


def test_uncached_input_never_negative():
    # Cache counts larger than tokens_in (inconsistent log) must not credit input.
    cost = estimate_cost("claude-opus-4-6", tokens_in=100, tokens_out=0, cache_read=1_000_000)
    assert cost == pytest.approx(0.50)
    cost = estimate_cost("claude-opus-4-6", tokens_in=0, tokens_out=0, cache_write_5m=1_000_000)
    assert cost == pytest.approx(6.25)


def test_negative_counts_are_not_billed():
    cost = estimate_cost("claude-opus-4-6", tokens_in=1_000_000, tokens_out=-5, cache_read=-1_000_000)
    assert cost == pytest.approx(5.00)


def test_anthropic_cache_multipliers_are_consistent():
    """The literal table follows Anthropic's rules: 5m write 1.25x, 1h write 2x, read 0.1x."""
    read_exceptions = {"claude-fable-5-1": 0.25, "claude-opus-5-5": 0.20}
    for model, p in PRICING.items():
        if not model.startswith("claude-"):
            continue
        assert p.cache_write_5m == pytest.approx(p.input * 1.25), model
        assert p.cache_write_1h == pytest.approx(p.input * 2.0), model
        assert p.cache_read == pytest.approx(read_exceptions.get(model, p.input * 0.1)), model


def test_gemini_cache_read_is_ten_percent_of_input():
    for model, p in PRICING.items():
        if model.startswith("gemini-"):
            assert p.cache_read == pytest.approx(p.input * 0.1), model


def test_gemini_pricing():
    cost = estimate_cost("gemini-2.5-flash", tokens_in=1_000_000, tokens_out=1_000_000)
    assert cost == 0.30 + 2.50


def test_unknown_model():
    assert estimate_cost("unknown-model", 1000, 1000) is None
    assert estimate_cost("unknown-model", 1000, 1000, cache_read=500) is None


def test_sonnet_pricing():
    cost = estimate_cost("claude-sonnet-4-6", tokens_in=1_000_000, tokens_out=1_000_000)
    assert cost == 3.00 + 15.00


def test_haiku_pricing():
    cost = estimate_cost("claude-haiku-4-5", tokens_in=1_000_000, tokens_out=1_000_000)
    assert cost == 1.00 + 5.00


def _per_million(model):
    return estimate_cost(model, tokens_in=1_000_000, tokens_out=1_000_000)


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
    assert estimate_cost("gpt-5.5", 1000, 1000, cache_read=800) is None
    assert estimate_cost("gpt-5-codex", 1000, 1000) is None


def test_message_cost_uses_cache_fields():
    msg = Message(
        role=Role.ASSISTANT,
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        model="claude-opus-4-6",
        tokens_in=1_000_000 + 100_000 + 100_000 + 1_000_000,
        tokens_out=0,
        tokens_cache_read=1_000_000,
        tokens_cache_write_5m=100_000,
        tokens_cache_write_1h=100_000,
    )
    # 1M uncached @5 + 1M read @0.5 + 100k 5m @6.25 + 100k 1h @10
    assert message_cost(msg) == pytest.approx(5.00 + 0.50 + 0.625 + 1.00)


def test_message_cost_unknown_model():
    msg = Message(role=Role.ASSISTANT, timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc), model="gpt-5.5")
    assert message_cost(msg) is None
