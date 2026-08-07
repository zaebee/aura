from types import SimpleNamespace

from hive.transformer import extract_cost, extract_usage


def test_extract_usage_reads_the_split():
    response = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20)
    )
    assert extract_usage(response) == (100, 20)


def test_extract_usage_returns_none_when_usage_absent():
    assert extract_usage(SimpleNamespace()) == (None, None)


def test_extract_usage_returns_none_when_usage_is_falsy():
    assert extract_usage(SimpleNamespace(usage=None)) == (None, None)


def test_extract_usage_returns_none_for_missing_fields_not_zero():
    response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=100))
    prompt, completion = extract_usage(response)
    assert prompt == 100
    assert completion is None


def test_extract_cost_returns_none_when_pricing_fails():
    # An object litellm cannot price must yield None, not 0.0.
    assert extract_cost(SimpleNamespace()) is None
