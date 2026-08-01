import httpx

from config import EvolverSettings
from hive.connector import EvolverConnector
from hive.models import EvolutionPlan, Improvement


def _settings(tmp_path, dry_run: bool) -> EvolverSettings:
    return EvolverSettings(
        AURA_LLM__API_KEY="test-key",
        GITHUB_REPOSITORY="zaebee/aura",
        GITHUB_TOKEN="ghp_realish",
        AURA_TELEGRAM_TOKEN="tg-token",
        AURA_METABOLISM_LOG=str(tmp_path / "metabolism.jsonl"),
        EVOLVER_DRY_RUN=dry_run,
    )


def _plan() -> EvolutionPlan:
    return EvolutionPlan(
        improvements=[
            Improvement(
                type="issue",
                title="Something",
                description="d",
                issue_body="body",
            )
        ],
        narrative="n",
    )


async def test_dry_run_makes_no_http_calls(tmp_path, monkeypatch):
    calls: list[str] = []

    async def _forbid(self, method, url, **kwargs):
        calls.append(str(url))
        raise AssertionError(f"dry_run must not call {url}")

    monkeypatch.setattr(httpx.AsyncClient, "request", _forbid)

    connector = EvolverConnector(_settings(tmp_path, dry_run=True))
    observation = await connector.act(
        plan=_plan(), branch="b", timestamp="20260801-1", apply_errors=[]
    )

    assert calls == []
    assert observation.pr_url == ""
    assert observation.telegram_sent is False
