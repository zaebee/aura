import pytest
from src.hive.proteins.reasoning.engine import clean_and_parse_json


def test_clean_and_parse_json_pure():
    text = '{"action": "accept", "price": 100}'
    assert clean_and_parse_json(text) == {"action": "accept", "price": 100}


def test_clean_and_parse_json_markdown():
    text = 'Here is the result:\n```json\n{"action": "counter", "price": 150}\n```'
    assert clean_and_parse_json(text) == {"action": "counter", "price": 150}


def test_clean_and_parse_json_with_text():
    text = 'The decision is: {"action": "reject", "price": 0} - end.'
    assert clean_and_parse_json(text) == {"action": "reject", "price": 0}


def test_clean_and_parse_json_invalid():
    text = "Not a JSON"
    with pytest.raises(ValueError, match="Could not parse JSON"):
        clean_and_parse_json(text)
