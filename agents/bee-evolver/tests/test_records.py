import json

from hive.records import MetabolicRecord


def _record(**overrides) -> MetabolicRecord:
    base = dict(
        ts="2026-08-01T18:40:12Z",
        bee="evolver",
        cycle_id="20260801-184012",
        git_sha="abc1234",
        model="mistral/mistral-large-latest",
        llm_calls=1,
        prompt_tokens=3412,
        completion_tokens=688,
        usd=0.0141,
        wall_clock_s=47.3,
        outcome="success",
        dry_run=False,
        proposals=3,
        applied=2,
    )
    base.update(overrides)
    return MetabolicRecord(**base)


def test_to_json_line_is_one_line_of_valid_json():
    line = _record().to_json_line()
    assert line.endswith("\n")
    assert line.count("\n") == 1
    parsed = json.loads(line)
    assert parsed["bee"] == "evolver"
    assert parsed["prompt_tokens"] == 3412


def test_unknown_usage_serialises_as_null_not_zero():
    line = _record(prompt_tokens=None, completion_tokens=None, usd=None).to_json_line()
    parsed = json.loads(line)
    assert parsed["prompt_tokens"] is None
    assert parsed["completion_tokens"] is None
    assert parsed["usd"] is None
