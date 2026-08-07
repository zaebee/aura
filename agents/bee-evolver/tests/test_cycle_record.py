import json

import pytest

from config import EvolverSettings
from hive.metabolism import EvolverMetabolism
from hive.models import EvolutionPlan


def _settings(tmp_path) -> EvolverSettings:
    return EvolverSettings(
        AURA_LLM__API_KEY="test-key",
        GITHUB_REPOSITORY="zaebee/aura",
        GITHUB_SHA="abc1234",
        AURA_METABOLISM_LOG=str(tmp_path / "metabolism.jsonl"),
        EVOLVER_DRY_RUN=True,
    )


def _read_record(path):
    lines = open(path, encoding="utf-8").read().splitlines()
    assert len(lines) == 1
    return json.loads(lines[0])


def _read_records(path):
    return [
        json.loads(x) for x in open(path, encoding="utf-8").read().splitlines()
    ]


async def test_transformer_failure_still_writes_a_record(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    metabolism = EvolverMetabolism(settings)

    async def _perceive():
        return object()

    async def _boom(_context):
        raise RuntimeError("brain exploded")

    # _configure_git shells out to git; keep the test hermetic.
    monkeypatch.setattr(metabolism, "_configure_git", lambda: None)
    monkeypatch.setattr(metabolism.aggregator, "perceive", _perceive)
    monkeypatch.setattr(metabolism.transformer, "think", _boom)

    with pytest.raises(RuntimeError):
        await metabolism.execute()

    record = _read_record(settings.metabolism_log)
    assert record["outcome"] == "llm_error"
    assert record["bee"] == "evolver"
    assert record["git_sha"] == "abc1234"
    assert record["wall_clock_s"] >= 0


async def test_aggregator_failure_is_not_labelled_llm_error(tmp_path, monkeypatch):
    """Each stage must own its failure label, or `outcome` cannot be trusted
    as the denominator of any per-success cost figure."""
    settings = _settings(tmp_path)
    metabolism = EvolverMetabolism(settings)

    async def _boom():
        raise RuntimeError("senses failed")

    monkeypatch.setattr(metabolism, "_configure_git", lambda: None)
    monkeypatch.setattr(metabolism.aggregator, "perceive", _boom)

    with pytest.raises(RuntimeError):
        await metabolism.execute()

    assert _read_record(settings.metabolism_log)["outcome"] == "aggregator_error"


async def test_sequential_cycles_do_not_accumulate_usage(tmp_path, monkeypatch):
    """Two cycles on one long-lived metabolism must report their own usage,
    not a running total.

    Today main.py calls execute() once and exits, so this cannot bite — but
    that is a property of how the Evolver is invoked, not of this code. Raising
    the cadence via a long-lived process would expose it, and the same defect
    was real in bee.Keeper, whose main() is a continuous loop.
    """
    settings = _settings(tmp_path)
    metabolism = EvolverMetabolism(settings)

    async def _perceive():
        return object()

    def _think_returning(prompt_tokens: int):
        async def _think(_context):
            return EvolutionPlan(
                prompt_tokens=prompt_tokens,
                completion_tokens=1,
                usd=0.001,
                model_used="mistral/mistral-large-latest",
                llm_calls=1,
            )

        return _think

    monkeypatch.setattr(metabolism, "_configure_git", lambda: None)
    monkeypatch.setattr(metabolism.aggregator, "perceive", _perceive)

    monkeypatch.setattr(metabolism.transformer, "think", _think_returning(100))
    await metabolism.execute()
    monkeypatch.setattr(metabolism.transformer, "think", _think_returning(400))
    await metabolism.execute()

    records = _read_records(settings.metabolism_log)
    assert len(records) == 2
    assert [r["prompt_tokens"] for r in records] == [100, 400]
    assert [r["llm_calls"] for r in records] == [1, 1]


async def test_connector_failure_is_labelled_connector_error(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    metabolism = EvolverMetabolism(settings)

    async def _perceive():
        return object()

    async def _think(_context):
        return EvolutionPlan()

    async def _boom(**_kwargs):
        raise RuntimeError("github down")

    monkeypatch.setattr(metabolism, "_configure_git", lambda: None)
    monkeypatch.setattr(metabolism.aggregator, "perceive", _perceive)
    monkeypatch.setattr(metabolism.transformer, "think", _think)
    monkeypatch.setattr(metabolism.connector, "act", _boom)

    with pytest.raises(RuntimeError):
        await metabolism.execute()

    assert _read_record(settings.metabolism_log)["outcome"] == "connector_error"
