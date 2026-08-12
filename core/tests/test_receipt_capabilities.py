"""
The lookup lives in the protein, not in the tool.

A `make resolve-dispute` command and a future internal endpoint should be two
thin callers of one query rather than two implementations of it.
"""

from unittest.mock import MagicMock

import pytest
from aura_hive.config.database import DatabaseSettings
from aura_hive.hive.proteins.persistence.skill import PersistenceSkill


def a_receipt() -> dict:
    return {
        "version": "AURA-RECEIPT-V2-UNSIGNED",
        "claimHash": "a" * 64,
        "decisionId": "dec-1111",
        "requestId": "req-2222",
        "issuedAt": "2026-08-12T10:00:00Z",
    }


def skill_with(session: MagicMock) -> PersistenceSkill:
    skill = PersistenceSkill()
    settings = DatabaseSettings(
        url="postgresql://user:password@localhost:5432/aura_db",
        redis_url="redis://localhost:6379/0",
    )
    skill.bind(settings, (MagicMock(return_value=session), MagicMock(), None))
    return skill


def a_session() -> MagicMock:
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    return session


class TestRecording:
    @pytest.mark.asyncio
    async def test_a_receipt_is_recorded_under_its_token(self) -> None:
        session = a_session()

        obs = await skill_with(session).execute(
            "record_receipt", {"receipt": a_receipt(), "dispute_token": "tok-abc"}
        )

        assert obs.success
        assert session.add.call_args[0][0].dispute_token == "tok-abc"

    @pytest.mark.asyncio
    async def test_a_missing_token_is_refused_by_value(self) -> None:
        obs = await skill_with(a_session()).execute(
            "record_receipt", {"receipt": a_receipt()}
        )

        assert not obs.success
        assert obs.error == "dispute_token_required"

    @pytest.mark.asyncio
    async def test_a_missing_receipt_is_refused_by_value(self) -> None:
        obs = await skill_with(a_session()).execute(
            "record_receipt", {"dispute_token": "tok-abc"}
        )

        assert not obs.success
        assert obs.error == "receipt_required"

    @pytest.mark.asyncio
    async def test_a_database_failure_is_reported_not_raised(self) -> None:
        """
        The Connector treats this as fail-open, so it must come back as a
        failed Observation rather than an exception crossing the boundary.
        """
        session = a_session()
        session.commit.side_effect = RuntimeError("connection refused")

        obs = await skill_with(session).execute(
            "record_receipt", {"receipt": a_receipt(), "dispute_token": "tok-abc"}
        )

        assert not obs.success
        assert "connection refused" in (obs.error or "")


class TestFinding:
    @pytest.mark.asyncio
    async def test_a_known_token_returns_the_document(self) -> None:
        session = a_session()
        row = MagicMock()
        row.receipt = a_receipt()
        session.query.return_value.filter_by.return_value.first.return_value = row

        obs = await skill_with(session).execute(
            "find_receipt_by_dispute_token", {"dispute_token": "tok-abc"}
        )

        assert obs.success
        assert obs.metadata.to_dict()["receipt"]["decisionId"] == "dec-1111"

    @pytest.mark.asyncio
    async def test_an_unknown_token_is_not_found_rather_than_an_error(self) -> None:
        session = a_session()
        session.query.return_value.filter_by.return_value.first.return_value = None

        obs = await skill_with(session).execute(
            "find_receipt_by_dispute_token", {"dispute_token": "never-issued"}
        )

        assert not obs.success
        assert obs.error == "not_found"
