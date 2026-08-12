"""
Receipts survive the log they used to live in.

`DECISION_RECEIPT.md` §7 says the log line makes the log the store. It does,
for days to weeks: the stream goes to a Loki outside this repository with a
short retention, and nothing wrote a receipt anywhere else. A dispute arriving
a month after the decision found nothing.
"""

import json
from unittest.mock import MagicMock

from aura_core_gen.aura.core.v1 import DecisionReceipt
from aura_hive.hive.proteins.persistence.receipts import ReceiptRepository


def a_receipt() -> dict:
    """A receipt dict in the shape `to_dict()` produces — camelCase keys."""
    return {
        "version": "AURA-RECEIPT-V2-UNSIGNED",
        "claimHash": "a" * 64,
        "emissionHash": "b" * 64,
        "outcome": "DECISION_OUTCOME_EMIT",
        "outcomeGate": "",
        "canonicalPrefix": "c" * 16,
        "issuedAt": "2026-08-12T10:00:00Z",
        "decisionId": "dec-1111",
        "requestId": "req-2222",
        "rulesetVersion": "guard/negotiation@2.0.0+deadbeef",
    }


def a_session() -> MagicMock:
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    return session


class TestRecording:
    def test_the_indexed_columns_are_taken_from_the_document(self) -> None:
        """
        Derived here rather than passed in, so an index cannot disagree with
        the receipt it indexes.
        """
        session = a_session()
        repo = ReceiptRepository(MagicMock(return_value=session))

        repo.record(a_receipt(), dispute_token="tok-abc")

        row = session.add.call_args[0][0]
        assert row.dispute_token == "tok-abc"
        assert row.decision_id == "dec-1111"
        assert row.request_id == "req-2222"
        assert row.issued_at == "2026-08-12T10:00:00Z"
        assert row.receipt == a_receipt()
        session.commit.assert_called_once()

    def test_the_whole_document_is_stored_not_a_decomposition(self) -> None:
        """
        `verify()` takes a document. Every normalisation is a chance to
        reassemble something at read time that differs from what was signed.
        """
        session = a_session()
        repo = ReceiptRepository(MagicMock(return_value=session))

        repo.record(a_receipt(), dispute_token="tok-abc")

        stored = session.add.call_args[0][0].receipt
        assert stored == a_receipt()

    def test_a_stored_receipt_survives_json_and_still_parses(self) -> None:
        """
        The column is JSON, so the document goes through a serialisation the
        receipt never asked for. This is the property the whole archive rests
        on: what comes back must be the document that was signed.
        """
        session = a_session()
        repo = ReceiptRepository(MagicMock(return_value=session))

        repo.record(a_receipt(), dispute_token="tok-abc")
        stored = session.add.call_args[0][0].receipt

        parsed = DecisionReceipt().from_dict(json.loads(json.dumps(stored)))

        assert parsed.decision_id == "dec-1111"
        assert parsed.claim_hash == "a" * 64
        assert parsed.canonical_prefix == "c" * 16


class TestADocumentThatCarriesNulls:
    def test_a_null_field_stores_an_empty_string_not_the_word_none(self) -> None:
        """
        `str(None)` is `"None"`, and an indexed column holding that literal is
        a row that exists and cannot be found — the worst shape of silent
        corruption for an archive whose only job is to be searchable.

        betterproto omits empty fields rather than emitting null, so a receipt
        minted here cannot carry one. A dict reaching this repository from
        anywhere else — a JSON blob with explicit nulls, a future caller — can.
        """
        session = a_session()
        repo = ReceiptRepository(MagicMock(return_value=session))

        repo.record(
            a_receipt() | {"decisionId": None, "requestId": None, "issuedAt": None},
            dispute_token="tok-abc",
        )

        row = session.add.call_args[0][0]
        assert row.decision_id == ""
        assert row.request_id == ""
        assert row.issued_at == ""


class TestFinding:
    def test_a_known_token_returns_the_document(self) -> None:
        session = a_session()
        row = MagicMock()
        row.receipt = a_receipt()
        session.query.return_value.filter_by.return_value.first.return_value = row
        repo = ReceiptRepository(MagicMock(return_value=session))

        assert repo.find_by_dispute_token("tok-abc") == a_receipt()

    def test_an_unknown_token_returns_nothing_rather_than_raising(self) -> None:
        """
        A token that was never issued is a legitimate answer to give an
        auditor — someone may have invented it — not a failure.
        """
        session = a_session()
        session.query.return_value.filter_by.return_value.first.return_value = None
        repo = ReceiptRepository(MagicMock(return_value=session))

        assert repo.find_by_dispute_token("never-issued") is None


class TestASessionCanBeReassembled:
    def test_two_decisions_in_one_session_share_a_request_id(self) -> None:
        """
        `request_id` exists so an auditor holding one token can pull the whole
        negotiation rather than the single turn they were cited. Nothing else
        asserts the field, so it would rot unnoticed.
        """
        session = a_session()
        repo = ReceiptRepository(MagicMock(return_value=session))

        first = a_receipt()
        second = a_receipt() | {"decisionId": "dec-3333"}
        repo.record(first, dispute_token="tok-one")
        repo.record(second, dispute_token="tok-two")

        rows = [call[0][0] for call in session.add.call_args_list]
        assert [row.decision_id for row in rows] == ["dec-1111", "dec-3333"]
        assert {row.request_id for row in rows} == {"req-2222"}
