"""
Market service for managing transaction-locked negotiation deals.
Handles deal creation, payment verification, and secret revelation.
Aligned with chromosomal DNA v0.3.0.
"""

import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from aura_core import SkillProtocol
from aura_core_gen.aura.negotiation.v1 import (
    CheckDealStatusResponse,
    CryptoPaymentInstructions,
    DealSecret,
    PaymentProof,
)

logger = logging.getLogger(__name__)


class MarketService:
    """
    Service for managing locked deals that require crypto payment.
    Uses betterproto chromosomal types.
    """

    def __init__(
        self,
        persistence: SkillProtocol,
        transaction: SkillProtocol,
        pulse: SkillProtocol | None = None,
    ):
        self.persistence = persistence
        self.transaction = transaction
        self.pulse = pulse

    async def create_offer(
        self,
        item_id: str,
        item_name: str,
        secret: str,
        price: float,
        currency: str,
        buyer_did: str | None = None,
        ttl_seconds: int = 3600,
    ) -> tuple[CryptoPaymentInstructions, str]:
        """Creates a locked deal and returns payment instructions."""
        memo = self._generate_unique_memo()
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=ttl_seconds)

        encrypt_obs = await self.transaction.execute("encrypt_secret", {"secret": secret})
        if not encrypt_obs.success:
            raise ValueError(f"Encryption failed: {encrypt_obs.error}")

        # In v0.3.0, obsidian_data/metadata struct is used
        encrypted_secret = encrypt_obs.metadata.to_dict().get("encrypted_secret") or encrypt_obs.error

        deal_id = uuid.uuid4()
        obs = await self.persistence.execute(
            "set_excited_state",
            {
                "id": deal_id,
                "item_id": item_id,
                "item_name": item_name,
                "final_price": price,
                "currency": currency,
                "payment_memo": memo,
                "secret_content": encrypted_secret,
                "buyer_did": buyer_did,
                "expires_at": expires_at,
                "ttl": ttl_seconds,
            },
        )

        if not obs.success:
            raise ValueError(f"Failed to create deal: {obs.error}")

        addr_obs = await self.transaction.execute("get_address", {})
        network_obs = await self.transaction.execute("get_network_name", {})
        uri_obs = await self.transaction.execute(
            "generate_payment_request",
            {
                "amount": price,
                "memo": memo,
                "currency": currency,
                "label": f"Aura Hive - {item_name}",
            },
        )

        addr = addr_obs.metadata.to_dict().get("address", "unknown")
        network = network_obs.metadata.to_dict().get("network", "unknown")
        payment_uri = uri_obs.metadata.to_dict().get("uri", "")

        return (
            CryptoPaymentInstructions(
                deal_id=str(deal_id),
                wallet_address=addr,
                amount=price,
                currency=currency,
                memo=memo,
                network=network,
                expires_at=int(expires_at.timestamp()),
            ),
            payment_uri,
        )

    async def check_status(self, deal_id: str) -> CheckDealStatusResponse:
        """Checks the payment status of a locked deal."""
        deal_uuid = uuid.UUID(deal_id)
        obs = await self.persistence.execute("get_deal_by_id", {"deal_id": deal_uuid})

        if not obs.success:
            return CheckDealStatusResponse(status="NOT_FOUND")

        deal = obs.metadata.to_dict()
        if not deal:
             return CheckDealStatusResponse(status="NOT_FOUND")

        now = datetime.now(UTC)
        expires_at_raw = deal.get("expires_at")
        expires_at = datetime.fromisoformat(expires_at_raw) if isinstance(expires_at_raw, str) else expires_at_raw

        if deal.get("status") == "PENDING" and now > expires_at:
            await self.persistence.execute(
                "update_deal_status", {"deal_id": deal_uuid, "status": "EXPIRED"}
            )
            return CheckDealStatusResponse(status="EXPIRED")

        if deal.get("status") == "PAID":
            return await self._build_paid_response(deal)

        if deal.get("status") == "PENDING":
            proof_obs = await self.transaction.execute(
                "verify_settlement",
                {
                    "amount": deal["final_price"],
                    "memo": deal["payment_memo"],
                    "currency": deal["currency"],
                },
            )

            if proof_obs.success:
                proof_data = proof_obs.metadata.to_dict()
                await self.persistence.execute(
                    "confirm_ground_state",
                    {
                        "deal_id": deal_uuid,
                        "status": "PAID",
                        "transaction_hash": proof_data["transaction_hash"],
                        "block_number": proof_data["block_number"],
                        "from_address": proof_data["from_address"],
                        "paid_at": proof_data["confirmed_at"],
                    },
                )

                if self.pulse:
                    await self.pulse.execute(
                        "emit_negotiation",
                        {
                            "session_token": f"deal_{deal_id}",
                            "action": "accept",
                            "price": deal["final_price"],
                            "item_id": deal["item_id"],
                            "agent_did": deal.get("buyer_did") or "unknown",
                        },
                    )

                deal["status"] = "PAID"
                deal.update(proof_data)
                return await self._build_paid_response(deal)
            else:
                return await self._build_pending_response(deal)

        return CheckDealStatusResponse(status=str(deal.get("status", "NOT_FOUND")))

    def _generate_unique_memo(self) -> str:
        return secrets.token_urlsafe(6)[:8]

    async def _build_paid_response(self, deal: dict[str, Any]) -> CheckDealStatusResponse:
        decrypt_obs = await self.transaction.execute(
            "decrypt_secret", {"encrypted_secret": deal["secret_content"]}
        )
        if not decrypt_obs.success:
            raise ValueError(f"Decryption failed: {decrypt_obs.error}")

        decrypted_secret = decrypt_obs.metadata.to_dict().get("secret", "")

        paid_at_raw = deal.get("paid_at")
        paid_at_ts = int(datetime.fromisoformat(paid_at_raw).timestamp()) if isinstance(paid_at_raw, str) else 0

        return CheckDealStatusResponse(
            status="PAID",
            secret=DealSecret(
                reservation_code=decrypted_secret,
                item_name=deal.get("item_name", ""),
                final_price=float(deal.get("final_price", 0.0)),
                paid_at=paid_at_ts,
            ),
            proof=PaymentProof(
                transaction_hash=deal.get("transaction_hash") or "",
                block_number=str(deal.get("block_number") or ""),
                from_address=deal.get("from_address") or "",
                confirmed_at=paid_at_ts,
            )
        )

    async def _build_pending_response(self, deal: dict[str, Any]) -> CheckDealStatusResponse:
        addr_obs = await self.transaction.execute("get_address", {})
        network_obs = await self.transaction.execute("get_network_name", {})

        addr = addr_obs.metadata.to_dict().get("address", "unknown")
        network = network_obs.metadata.to_dict().get("network", "unknown")

        expires_at_raw = deal.get("expires_at")
        expires_at_ts = int(datetime.fromisoformat(expires_at_raw).timestamp()) if isinstance(expires_at_raw, str) else 0

        return CheckDealStatusResponse(
            status="PENDING",
            payment_instructions=CryptoPaymentInstructions(
                deal_id=str(deal.get("id")),
                wallet_address=addr,
                amount=float(deal.get("final_price", 0.0)),
                currency=deal.get("currency", ""),
                memo=deal.get("payment_memo", ""),
                network=network,
                expires_at=expires_at_ts,
            )
        )
