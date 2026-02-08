"""
Market service for managing transaction-locked negotiation deals.
Handles deal creation, payment verification, and secret revelation.
"""

import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from aura.negotiation.v1 import negotiation_pb2  # type: ignore
from aura_core import SkillProtocol

logger = logging.getLogger(__name__)


class MarketService:
    """
    Service for managing locked deals that require crypto payment.

    Responsibilities:
    - Creating locked deals with unique payment memos
    - Encrypting secrets via Transaction Protein
    - Checking payment status via blockchain verification
    - Revealing decrypted secrets after payment confirmation
    - Managing deal expiration
    """

    def __init__(
        self,
        persistence: SkillProtocol,
        transaction: SkillProtocol,
    ):
        """
        Initialize market service.

        Args:
            persistence: Persistence Protein for database operations
            transaction: Transaction Protein for blockchain verification and encryption
        """
        self.persistence = persistence
        self.transaction = transaction

    async def create_offer(
        self,
        item_id: str,
        item_name: str,
        secret: str,
        price: float,
        currency: str,
        buyer_did: str | None = None,
        ttl_seconds: int = 3600,
    ) -> negotiation_pb2.CryptoPaymentInstructions:
        """
        Creates a locked deal and returns payment instructions.
        """
        # Generate unique memo
        memo = self._generate_unique_memo()

        # Calculate expiration time
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=ttl_seconds)

        # Encrypt secret via Transaction Protein
        encrypt_obs = await self.transaction.execute(
            "encrypt_secret", {"secret": secret}
        )
        if not encrypt_obs.success:
            raise ValueError(f"Encryption failed: {encrypt_obs.error}")
        encrypted_secret = encrypt_obs.data

        deal_id = uuid.uuid4()
        # Create locked deal record via Persistence Protein
        obs = await self.persistence.execute(
            "create_deal",
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
            },
        )

        if not obs.success:
            raise ValueError(f"Failed to create deal: {obs.error}")

        logger.info(
            "deal_created",
            extra={
                "deal_id": str(deal_id),
                "item_id": item_id,
                "item_name": item_name,
                "price": price,
                "currency": currency,
                "memo": memo,
                "expires_at": expires_at.isoformat(),
                "buyer_did": buyer_did,
            },
        )

        # Get transaction provider info
        addr_obs = await self.transaction.execute("get_address", {})
        network_obs = await self.transaction.execute("get_network_name", {})

        # Return payment instructions
        return negotiation_pb2.CryptoPaymentInstructions(
            deal_id=str(deal_id),
            wallet_address=addr_obs.data if addr_obs.success else "unknown",
            amount=price,
            currency=currency,
            memo=memo,
            network=network_obs.data if network_obs.success else "unknown",
            expires_at=int(expires_at.timestamp()),
        )

    async def check_status(
        self, deal_id: str
    ) -> negotiation_pb2.CheckDealStatusResponse:
        """
        Checks the payment status of a locked deal.
        """
        deal_uuid = uuid.UUID(deal_id)

        # Query deal from Persistence Protein
        obs = await self.persistence.execute("get_deal_by_id", {"deal_id": deal_uuid})

        if not obs.success or not obs.data:
            logger.info("Deal not found", extra={"deal_id": deal_id})
            return negotiation_pb2.CheckDealStatusResponse(status="NOT_FOUND")

        deal = obs.data
        now = datetime.now(UTC)
        expires_at = deal["expires_at"]
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)

        if deal["status"] == "PENDING" and now > expires_at:
            await self.persistence.execute(
                "update_deal_status", {"deal_id": deal_uuid, "status": "EXPIRED"}
            )
            return negotiation_pb2.CheckDealStatusResponse(status="EXPIRED")

        if deal["status"] == "PAID":
            return await self._build_paid_response(deal)

        if deal["status"] == "PENDING":
            proof_obs = await self.transaction.execute(
                "verify_payment",
                {
                    "amount": deal["final_price"],
                    "memo": deal["payment_memo"],
                    "currency": deal["currency"],
                },
            )

            if proof_obs.success and proof_obs.data:
                proof = proof_obs.data
                await self.persistence.execute(
                    "update_deal_status",
                    {
                        "deal_id": deal_uuid,
                        "status": "PAID",
                        "transaction_hash": proof["transaction_hash"],
                        "block_number": proof["block_number"],
                        "from_address": proof["from_address"],
                        "paid_at": proof["confirmed_at"],
                    },
                )

                deal["status"] = "PAID"
                deal["transaction_hash"] = proof["transaction_hash"]
                deal["block_number"] = proof["block_number"]
                deal["from_address"] = proof["from_address"]
                deal["paid_at"] = proof["confirmed_at"]

                return await self._build_paid_response(deal)
            else:
                return await self._build_pending_response(deal)

        return negotiation_pb2.CheckDealStatusResponse(status=deal["status"])

    def _generate_unique_memo(self) -> str:
        return secrets.token_urlsafe(6)[:8]

    async def _build_paid_response(
        self, deal: dict[str, Any]
    ) -> negotiation_pb2.CheckDealStatusResponse:
        """
        Builds response for PAID deals with decrypted secret via Transaction Protein.
        """
        decrypt_obs = await self.transaction.execute(
            "decrypt_secret", {"encrypted_secret": deal["secret_content"]}
        )
        if not decrypt_obs.success:
            raise ValueError(f"Decryption failed: {decrypt_obs.error}")
        decrypted_secret = decrypt_obs.data

        secret = negotiation_pb2.DealSecret(
            reservation_code=decrypted_secret,
            item_name=deal["item_name"],
            final_price=deal["final_price"],
            paid_at=int(deal["paid_at"].timestamp()) if deal["paid_at"] else 0,
        )

        proof = negotiation_pb2.PaymentProof(
            transaction_hash=deal["transaction_hash"] or "",
            block_number=deal["block_number"] or "",
            from_address=deal["from_address"] or "",
            confirmed_at=int(deal["paid_at"].timestamp()) if deal["paid_at"] else 0,
        )

        return negotiation_pb2.CheckDealStatusResponse(
            status="PAID",
            secret=secret,
            proof=proof,
        )

    async def _build_pending_response(
        self, deal: dict[str, Any]
    ) -> negotiation_pb2.CheckDealStatusResponse:
        addr_obs = await self.transaction.execute("get_address", {})
        network_obs = await self.transaction.execute("get_network_name", {})

        instructions = negotiation_pb2.CryptoPaymentInstructions(
            deal_id=str(deal["id"]),
            wallet_address=addr_obs.data if addr_obs.success else "unknown",
            amount=deal["final_price"],
            currency=deal["currency"],
            memo=deal["payment_memo"],
            network=network_obs.data if network_obs.success else "unknown",
            expires_at=int(deal["expires_at"].timestamp()),
        )

        return negotiation_pb2.CheckDealStatusResponse(
            status="PENDING",
            payment_instructions=instructions,
        )
