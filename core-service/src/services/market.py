"""
Market service for managing crypto-locked negotiation deals.
Handles deal creation, payment verification, and secret revelation.
"""

import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.crypto.encryption import SecretEncryption
from src.crypto.interfaces import CryptoProvider
from src.db import DealStatus, LockedDeal
from src.proto.aura.negotiation.v1 import negotiation_pb2

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

    def __init__(self, crypto_provider: CryptoProvider, encryption: SecretEncryption):
        """
        Initialize market service.

        Args:
            crypto_provider: Blockchain payment provider (e.g., SolanaProvider)
            encryption: Secret encryption handler for encrypting/decrypting reservation codes
        """
        self.provider = crypto_provider
        self.encryption = encryption

    def create_offer(
        self,
        db: Session,
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

        # Create locked deal record
        deal = LockedDeal(
            id=uuid.uuid4(),
            item_id=item_id,
            item_name=item_name,
            final_price=price,
            currency=currency,
            payment_memo=memo,
            secret_content=encrypted_secret,  # Encrypted with Fernet
            status=DealStatus.PENDING,
            buyer_did=buyer_did,
            created_at=now,
            expires_at=expires_at,
            updated_at=now,
        )

        db.add(deal)
        db.commit()
        db.refresh(deal)

        logger.info(
            "deal_created",
            extra={
                "deal_id": str(deal.id),
                "item_id": item_id,
                "item_name": item_name,
                "price": price,
                "currency": currency,
                "memo": memo,
                "expires_at": expires_at.isoformat(),
                "buyer_did": buyer_did,
            },
        )

        # Return payment instructions
        return negotiation_pb2.CryptoPaymentInstructions(
            deal_id=str(deal.id),
            wallet_address=self.provider.get_address(),
            amount=price,
            currency=currency,
            memo=memo,
            network=self.provider.get_network_name(),
            expires_at=int(expires_at.timestamp()),
        )

    async def check_status(
        self, db: Session, deal_id: str
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

        # Query deal from database with row-level lock to prevent race conditions
        stmt = select(LockedDeal).where(LockedDeal.id == deal_uuid).with_for_update()
        deal = db.scalars(stmt).first()

        if not deal:
            logger.info("Deal not found", extra={"deal_id": deal_id})
            return negotiation_pb2.CheckDealStatusResponse(status="NOT_FOUND")

        # Check if deal expired
        now = datetime.now(UTC)
        if deal.status == DealStatus.PENDING and now > deal.expires_at:
            deal.status = DealStatus.EXPIRED
            deal.updated_at = now
            db.commit()

            logger.info(
                "deal_expired",
                extra={
                    "deal_id": deal_id,
                    "expires_at": deal.expires_at.isoformat(),
                },
            )
            return negotiation_pb2.CheckDealStatusResponse(status="EXPIRED")

        # If already paid, return cached secret (idempotent)
        if deal.status == DealStatus.PAID:
            logger.info(
                "deal_already_paid",
                extra={
                    "deal_id": deal_id,
                    "paid_at": deal.paid_at.isoformat() if deal.paid_at else None,
                },
            )
            return self._build_paid_response(deal)

        # If pending, verify payment on-chain
        if deal.status == DealStatus.PENDING:
            proof = await self.provider.verify_payment(
                amount=deal.final_price,
                memo=deal.payment_memo,
                currency=deal.currency,
            )

            if proof:
                # Payment confirmed! Update database
                deal.status = DealStatus.PAID
                deal.transaction_hash = proof.transaction_hash
                deal.block_number = proof.block_number
                deal.from_address = proof.from_address
                deal.paid_at = proof.confirmed_at
                deal.updated_at = now
                db.commit()

                logger.info(
                    "payment_verified",
                    extra={
                        "deal_id": deal_id,
                        "transaction_hash": proof.transaction_hash,
                        "block_number": proof.block_number,
                        "from_address": proof.from_address,
                        "amount": deal.final_price,
                        "currency": deal.currency,
                    },
                )

                return self._build_paid_response(deal)
            else:
                # Payment not yet received
                logger.info(
                    "payment_pending",
                    extra={
                        "deal_id": deal_id,
                        "memo": deal.payment_memo,
                        "amount": deal.final_price,
                        "currency": deal.currency,
                    },
                )
                return self._build_pending_response(deal)

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
        self, deal: LockedDeal
    ) -> negotiation_pb2.CheckDealStatusResponse:
        """
        Builds response for PAID deals with decrypted secret and proof.

        Args:
            deal: LockedDeal record with payment confirmed

        Returns:
            CheckDealStatusResponse with status="PAID"
        """
        # Decrypt secret before revealing
        decrypted_secret = self.encryption.decrypt(deal.secret_content)

        secret = negotiation_pb2.DealSecret(
            reservation_code=decrypted_secret,
            item_name=deal.item_name,
            final_price=deal.final_price,
            paid_at=int(deal.paid_at.timestamp()) if deal.paid_at else 0,
        )

        proof = negotiation_pb2.PaymentProof(
            transaction_hash=deal.transaction_hash or "",
            block_number=deal.block_number or "",
            from_address=deal.from_address or "",
            confirmed_at=int(deal.paid_at.timestamp()) if deal.paid_at else 0,
        )

        return negotiation_pb2.CheckDealStatusResponse(
            status="PAID",
            secret=secret,
            proof=proof,
        )

    def _build_pending_response(
        self, deal: LockedDeal
    ) -> negotiation_pb2.CheckDealStatusResponse:
        """
        Builds response for PENDING deals with payment instructions.

        Args:
            deal: LockedDeal record awaiting payment

        Returns:
            CheckDealStatusResponse with status="PENDING"
        """
        instructions = negotiation_pb2.CryptoPaymentInstructions(
            deal_id=str(deal.id),
            wallet_address=self.provider.get_address(),
            amount=deal.final_price,
            currency=deal.currency,
            memo=deal.payment_memo,
            network=self.provider.get_network_name(),
            expires_at=int(deal.expires_at.timestamp()),
        )

        return negotiation_pb2.CheckDealStatusResponse(
            status="PENDING",
            payment_instructions=instructions,
        )
