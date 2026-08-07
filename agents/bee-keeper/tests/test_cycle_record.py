import json
from types import SimpleNamespace

from aura_keeper.config import KeeperSettings
from aura_keeper.hive.transformer import BeeTransformer


def _settings(tmp_path) -> KeeperSettings:
    return KeeperSettings(
        AURA_LLM__API_KEY="test-key",
        GITHUB_REPOSITORY="zaebee/aura",
        GITHUB_SHA="abc1234",
        AURA_METABOLISM_LOG=str(tmp_path / "metabolism.jsonl"),
    )


def _response(prompt: int, completion: int) -> SimpleNamespace:
    return SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion)
    )


def test_usage_sums_across_multiple_calls(tmp_path):
    transformer = BeeTransformer(_settings(tmp_path))

    transformer._accumulate_usage(_response(100, 10), "mistral/mistral-large-latest")
    transformer._accumulate_usage(_response(400, 40), "mistral/mistral-large-latest")

    assert transformer.usage_totals["llm_calls"] == 2
    assert transformer.usage_totals["prompt_tokens"] == 500
    assert transformer.usage_totals["completion_tokens"] == 50


def test_usage_resets_between_cycles(tmp_path):
    """main() runs a continuous loop, calling execute() once per NATS event on
    one long-lived transformer. Without a per-cycle reset, every record after
    the first reports the sum of all preceding cycles."""
    transformer = BeeTransformer(_settings(tmp_path))

    transformer._accumulate_usage(_response(100, 10), "mistral/mistral-large-latest")
    transformer.reset_usage()
    transformer._accumulate_usage(_response(400, 40), "mistral/mistral-large-latest")

    assert transformer.usage_totals["llm_calls"] == 1
    assert transformer.usage_totals["prompt_tokens"] == 400
    assert transformer.usage_totals["completion_tokens"] == 40


def test_unknown_usage_does_not_become_zero(tmp_path):
    transformer = BeeTransformer(_settings(tmp_path))

    transformer._accumulate_usage(SimpleNamespace(), "mistral/mistral-large-latest")

    assert transformer.usage_totals["llm_calls"] == 1
    assert transformer.usage_totals["prompt_tokens"] is None


def test_cycle_writes_a_record(tmp_path):
    from aura_keeper.hive.connector import BeeConnector
    from aura_keeper.hive.records import MetabolicRecord

    settings = _settings(tmp_path)
    connector = BeeConnector(settings)
    connector.write_metabolic_record(
        MetabolicRecord(
            ts="2026-08-01T18:40:12Z",
            bee="keeper",
            cycle_id="c1",
            git_sha=settings.git_sha,
            model=None,
            llm_calls=0,
            prompt_tokens=None,
            completion_tokens=None,
            usd=None,
            wall_clock_s=0.5,
            outcome="success",
            dry_run=False,
        )
    )

    record = json.loads(open(settings.metabolism_log, encoding="utf-8").read())
    assert record["bee"] == "keeper"
    assert record["git_sha"] == "abc1234"
