"""ReceiptRepository — the auditor's copy of every decision receipt.

Keeps the receipt SQL in one place so the skill's handlers stay thin
(params -> repo -> Observation). Methods are synchronous; callers wrap them in
``asyncio.to_thread`` exactly as the other repositories are called.
"""

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from .engine import DecisionReceiptRecord


class ReceiptRepository:
    """Write-once storage for decision receipts, read by dispute token."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session = session_factory

    def record(self, receipt: dict[str, Any], dispute_token: str) -> None:
        """
        Store a receipt under the token the counterparty was given.

        The indexed columns are derived from the document rather than passed
        in beside it, so an index cannot come to disagree with the receipt it
        indexes.
        """
        with self._session() as session:
            session.add(
                DecisionReceiptRecord(
                    dispute_token=dispute_token,
                    decision_id=str(receipt.get("decisionId", "")),
                    request_id=str(receipt.get("requestId", "")),
                    issued_at=str(receipt.get("issuedAt", "")),
                    receipt=receipt,
                )
            )
            session.commit()

    def find_by_dispute_token(self, token: str) -> dict[str, Any] | None:
        """The document, or None. An unissued token is an answer, not a fault."""
        with self._session() as session:
            row = (
                session.query(DecisionReceiptRecord)
                .filter_by(dispute_token=token)
                .first()
            )
            return dict(row.receipt) if row else None
