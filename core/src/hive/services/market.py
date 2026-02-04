"""
Market service for managing crypto-locked negotiation deals.
Handles deal creation, payment verification, and secret revelation.
"""

import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from aura_core import SkillProtocol
from hive.connector.proteins.encryption import SecretEncryption
from hive.proto.aura.negotiation.v1 import negotiation_pb2

logger = logging.getLogger(__name__)


class MarketService:
    """
    Service for managing locked deals that require crypto payment.

    Responsibilities:
    - Creating locked deals with unique payment memos
    - Encrypting secrets with Fernet encryption
    - Checking payment status via blockchain verification
    - Revealing decrypted secrets after payment confirmation
    - Managing deal expiration
    """

    def __init__(
        self,
        storage: SkillProtocol,
        crypto: SkillProtocol,
        encryption: SecretEncryption,
    ):
        """
        Initialize market service.

        Args:
            storage: Storage Protein for database operations
            crypto: Crypto Protein for blockchain verification
            encryption: Secret encryption handler for encrypting/decrypting reservation codes
        """
        self.storage = storage
        self.crypto = crypto
        self.encryption = encryption

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

        Process:
        1. Generate unique 8-character payment memo
        2. Create LockedDeal record in database (status=PENDING)
        3. Return payment instructions proto

        Args:
            db: Database session
            item_id: ID of the negotiated item
            item_name: Name of the item
            secret: Reservation code to lock (revealed after payment)
            price: Final agreed price
            currency: Payment currency ("SOL" or "USDC")
            buyer_did: Optional buyer DID for tracking
            ttl_seconds: Time-to-live in seconds (default: 1 hour)

        Returns:
            CryptoPaymentInstructions proto message
        """
        # Generate unique memo (8 characters = ~2.8 trillion combinations)
        memo = self._generate_unique_memo()

        # Calculate expiration time
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=ttl_seconds)

        # Encrypt secret before storing
        encrypted_secret = self.encryption.encrypt(secret)

        deal_id = uuid.uuid4()
        # Create locked deal record via Storage Protein
        obs = await self.storage.execute(
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

        # Get crypto provider info
        addr_obs = await self.crypto.execute("get_address", {})
        network_obs = await self.crypto.execute("get_network_name", {})

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

        State Machine:
        - NOT_FOUND: Deal doesn't exist
        - EXPIRED: Deal expired before payment
        - PENDING: Awaiting payment (includes payment_instructions)
        - PAID: Payment confirmed (includes secret + proof)

        Idempotency: If deal is already PAID, returns cached secret/proof
        without re-verifying on-chain.

        Args:
            db: Database session
            deal_id: UUID of the deal to check

        Returns:
            CheckDealStatusResponse proto message
        """
        # Parse UUID (already validated at API boundary)
        deal_uuid = uuid.UUID(deal_id)

        # Query deal from Storage Protein
        obs = await self.storage.execute("get_deal_by_id", {"deal_id": deal_uuid})

        if not obs.success or not obs.data:
            logger.info("Deal not found", extra={"deal_id": deal_id})
            return negotiation_pb2.CheckDealStatusResponse(status="NOT_FOUND")

        deal = obs.data
        # Check if deal expired
        now = datetime.now(UTC)
        if deal["status"] == "PENDING" and now > deal["expires_at"]:
            await self.storage.execute(
                "update_deal_status", {"deal_id": deal_uuid, "status": "EXPIRED"}
            )
            logger.info(
                "deal_expired",
                extra={
                    "deal_id": deal_id,
                    "expires_at": deal["expires_at"].isoformat(),
                },
            )
            return negotiation_pb2.CheckDealStatusResponse(status="EXPIRED")

        # If already paid, return cached secret (idempotent)
        if deal["status"] == "PAID":
            logger.info(
                "deal_already_paid",
                extra={
                    "deal_id": deal_id,
                    "paid_at": deal["paid_at"].isoformat() if deal["paid_at"] else None,
                },
            )
            return self._build_paid_response(deal)

        # If pending, verify payment on-chain
        if deal["status"] == "PENDING":
            proof_obs = await self.crypto.execute(
                "verify_payment",
                {
                    "amount": deal["final_price"],
                    "memo": deal["payment_memo"],
                    "currency": deal["currency"],
                },
            )

            if proof_obs.success and proof_obs.data:
                proof = proof_obs.data
                # Payment confirmed! Update Storage
                await self.storage.execute(
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

                # Update local deal dict for response building
                deal["status"] = "PAID"
                deal["transaction_hash"] = proof["transaction_hash"]
                deal["block_number"] = proof["block_number"]
                deal["from_address"] = proof["from_address"]
                deal["paid_at"] = proof["confirmed_at"]

                logger.info(
                    "payment_verified",
                    extra={
                        "deal_id": deal_id,
                        "transaction_hash": proof["transaction_hash"],
                        "block_number": proof["block_number"],
                        "from_address": proof["from_address"],
                        "amount": deal["final_price"],
                        "currency": deal["currency"],
                    },
                )

                return self._build_paid_response(deal)
            else:
                # Payment not yet received
                logger.info(
                    "payment_pending",
                    extra={
                        "deal_id": deal_id,
                        "memo": deal["payment_memo"],
                        "amount": deal["final_price"],
                        "currency": deal["currency"],
                    },
                )
                return await self._build_pending_response(deal)

        # Handle unexpected status
        logger.warning(
            "Unexpected deal status", extra={"deal_id": deal_id, "status": deal.status}
        )
        return negotiation_pb2.CheckDealStatusResponse(status=deal.status.value)

    def _generate_unique_memo(self) -> str:
        """
        Generates a cryptographically random 8-character memo.

        Uses secrets.token_urlsafe for high entropy (2.8 trillion combinations).

        Returns:
            8-character alphanumeric string
        """
        return secrets.token_urlsafe(6)[:8]  # 6 bytes = 8 base64 chars

    def _build_paid_response(
        self, deal: dict[str, Any]
    ) -> negotiation_pb2.CheckDealStatusResponse:
        """
        Builds response for PAID deals with decrypted secret and proof.
        """
        decrypted_secret = self.encryption.decrypt(deal["secret_content"])

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
        """
        Builds response for PENDING deals with payment instructions.
        """
        addr_obs = await self.crypto.execute("get_address", {})
        network_obs = await self.crypto.execute("get_network_name", {})

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
