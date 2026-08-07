import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))

from aggregate_metabolism import aggregate  # noqa: E402


def _line(cycle_id: str, prompt_tokens=10) -> str:
    return json.dumps(
        {"cycle_id": cycle_id, "bee": "evolver", "prompt_tokens": prompt_tokens}
    )


def test_deduplicates_by_cycle_id():
    lines, _, _ = aggregate([_line("a"), _line("b"), _line("a")])
    assert len(lines) == 2
    assert [json.loads(x)["cycle_id"] for x in lines] == ["a", "b"]


def test_counts_rows_with_unknown_usage():
    lines, unknown, _ = aggregate([_line("a"), _line("b", prompt_tokens=None)])
    assert len(lines) == 2
    assert unknown == 1


def test_skips_malformed_lines():
    lines, _, malformed = aggregate([_line("a"), "not json", ""])
    assert len(lines) == 1
    assert malformed == 1


def test_records_without_cycle_id_do_not_swallow_each_other():
    """A None cycle_id entering `seen` would make the first such row discard
    every later one — silent loss, the failure mode this tool guards against.
    They are dropped, but counted."""
    lines, _, malformed = aggregate(
        [
            json.dumps({"bee": "evolver", "prompt_tokens": 10}),
            json.dumps({"bee": "keeper", "prompt_tokens": 20}),
            _line("a"),
        ]
    )
    assert [json.loads(x)["cycle_id"] for x in lines] == ["a"]
    assert malformed == 2
