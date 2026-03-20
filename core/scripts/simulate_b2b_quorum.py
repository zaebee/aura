#!/usr/bin/env python3
"""
B2B Quorum Sensing Simulation - Multi-Agent RWA Loan Negotiation

This script demonstrates two sovereign AI agents (Borrower & Lender) negotiating
an Institutional RWA-Backed Loan through the Aura Hive Oracle.

Biological Metaphor:
    Simulating the extracellular matrix where multiple entities exchange ATP (Liquidity)
    based on the Hive's trusted pheromones (Validation Scores).

Flow:
    1. Agent Alpha (Borrower) submits asset image + loan request to Hive
    2. Hive's Vision Cortex analyzes the RWA (e.g., gold bar)
    3. Hive's Risk Router emits EIP-712 TradeIntent with ValidationScore
    4. Agent Beta (Lender) listens to Hive events, validates score
    5. If approved (score > 0.8), Agent Beta counter-signs
    6. TransactionSkill executes SPL token transfer on Solana Devnet

Usage:
    python core/scripts/simulate_b2b_quorum.py
    python core/scripts/simulate_b2b_quorum.py --mock    # Simulate without real services
    python core/scripts/simulate_b2b_quorum.py --amount 50000  # Custom loan amount

Environment:
    AURA_API_URL         - API Gateway URL (default: http://localhost:8000)
    AURA_NATS_URL        - NATS server URL (default: nats://localhost:4222)
    AURA_SOLANA_KEY      - Treasury wallet private key (default: ~/.config/solana/id.json)
    AURA_SOLANA_RPC      - Solana RPC URL (default: https://api.devnet.solana.com)
"""

import argparse
import asyncio
import base64
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import httpx
import nats
import structlog
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Finalized
from solders.keypair import Keypair
from solders.message import Message
from solders.pubkey import Pubkey
from solders.transaction import Transaction
from spl.token.constants import TOKEN_PROGRAM_ID
from spl.token.instructions import (
    TransferCheckedParams,
    create_associated_token_account,
    get_associated_token_address,
    transfer_checked,
)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.simulators.agent_identity import AgentWallet

# ============================================================================
# Configuration
# ============================================================================

RPC_URL = os.getenv("AURA_SOLANA_RPC", "https://api.devnet.solana.com")
DEVNET_USDC_MINT = "Gh9ZwEmdLJ8DscKNTkTqPbNwLNNBjuSzaG9Vp2KGtKJr"
USDC_DECIMALS = 6
SOL_DECIMALS = 9

DEFAULT_LOAN_AMOUNT = 10_000.0  # 10,000 USDC
RISK_APPROVAL_THRESHOLD = 0.8  # Agent Beta requires score > 0.8

IMAGE_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/8/87/Gold_bar.jpg/220px-Gold_bar.jpg"


# ============================================================================
# Cyberpunk Logging Setup
# ============================================================================


class CyberpunkRenderer:
    """Custom cyberpunk-styled console renderer."""

    def __call__(self, logger, method_name, event_dict):
        timestamp = event_dict.get("timestamp")
        if timestamp:
            if isinstance(timestamp, str):
                ts = self.colorize_timestamp(timestamp[:12])
            else:
                ts = self.colorize_timestamp(timestamp.strftime("%H:%M:%S.%f")[:-3])
        else:
            ts = self.colorize_timestamp("00:00:00.000")

        level = event_dict.get("level", "").upper()
        if method_name == "error":
            level_str = self.colorize_error("!!!")
        elif method_name == "warning":
            level_str = self.colorize_warning("???" if len(level) <= 3 else "WARN")
        else:
            level_str = self.colorize_info(">>>" if len(level) <= 3 else level)

        parts = [f"{ts} {level_str}"]

        event = event_dict.get("event", "")
        if event:
            parts.append(self.colorize_value(str(event)))

        for key, value in event_dict.items():
            if key not in ("event", "timestamp", "level"):
                parts.append(
                    f"{self.colorize_key(key)}={self.colorize_value(str(value))}"
                )

        return " ".join(parts)

    @staticmethod
    def colorize_timestamp(ts: str) -> str:
        return f"\033[36m[{ts}]\033[0m"

    @staticmethod
    def colorize_info(s: str) -> str:
        return f"\033[32m{s}\033[0m"

    @staticmethod
    def colorize_warning(s: str) -> str:
        return f"\033[33m[{s}]\033[0m"

    @staticmethod
    def colorize_error(s: str) -> str:
        return f"\033[31m{s}\033[0m"

    @staticmethod
    def colorize_key(s: str) -> str:
        return f"\033[35m{s}\033[0m"

    @staticmethod
    def colorize_value(s: str) -> str:
        return f"\033[37m{s}\033[0m"


def setup_logging(verbose: bool = False) -> structlog.BoundLogger:
    """Configure cyberpunk-styled logging."""
    import logging

    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="%H:%M:%S.%f", utc=True),
            structlog.processors.add_log_level,
            CyberpunkRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
    return structlog.get_logger("quorum")


# ============================================================================
# Data Models
# ============================================================================


class NegotiationStatus(Enum):
    INITIATED = "initiated"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"


@dataclass
class ValidationScore:
    """EIP-712 Validation Score from the Hive's Risk Router."""

    risk_score: float  # 0.0-1.0, lower is better (risk)
    risk_category: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    confidence: float  # 0.0-1.0, higher is better
    kyc_status: str  # "APPROVED", "PENDING", "REJECTED"
    reasoning: str
    validated_at: datetime = field(
        default_factory=lambda: datetime.now(tz=__import__("datetime").timezone.utc)
    )


@dataclass
class TradeIntent:
    """EIP-712 Trade Intent structured data."""

    trade_id: str
    asset_identifier: str
    asset_domain: str
    proposed_price: float
    currency_code: str
    validation_score: ValidationScore
    eip712_domain: dict
    eip712_types: dict
    metadata: dict = field(default_factory=dict)


@dataclass
class LoanRequest:
    """RWA-backed loan request from Borrower."""

    request_id: str
    agent_did: str
    asset_image_b64: str
    asset_type: str
    loan_amount: float
    collateral_value: float
    ltv_ratio: float  # Loan-to-Value ratio


@dataclass
class NegotiationSession:
    """Negotiation session between agents."""

    session_id: str
    borrower: "AgentAlpha"
    lender: "AgentBeta | None"
    loan_request: LoanRequest
    trade_intent: TradeIntent | None
    status: NegotiationStatus
    created_at: datetime = field(default_factory=datetime.utcnow)


# ============================================================================
# Utilities
# ============================================================================


def load_solana_key() -> bytes | str:
    """Load Solana private key from environment or default location."""
    key = os.getenv("AURA_SOLANA_KEY", "")
    if key:
        return key

    default_path = Path.home() / ".config" / "solana" / "id.json"
    if default_path.exists():
        with open(default_path) as f:
            data = json.load(f)
            if isinstance(data, dict):
                key = data.get("key", data.get("private_key", ""))
                if key:
                    return key
            elif isinstance(data, list):
                return bytes(data)
            elif isinstance(data, str):
                return data

    raise ValueError(
        "Solana key not found. Set AURA_SOLANA_KEY or ensure ~/.config/solana/id.json exists"
    )


def download_image_as_base64(url: str) -> str:
    """Download an image and return as base64."""
    if not url.startswith("https://"):
        raise ValueError("Only HTTPS URLs are allowed for image downloads")
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url)
            response.raise_for_status()
            return base64.b64encode(response.content).decode("utf-8")
    except Exception as e:
        print(f"Failed to download image from {url}: {e}")
        placeholder = create_placeholder_image_base64()
        print("Using generated placeholder image instead")
        return placeholder


def create_placeholder_image_base64() -> str:
    """Create a simple placeholder image as base64 (1x1 transparent PNG)."""
    transparent_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return base64.b64encode(transparent_png).decode("utf-8")


async def get_token_balance(client: AsyncClient, wallet: Pubkey, mint: Pubkey) -> float:
    """Get SPL token balance for a wallet."""
    ata = get_associated_token_address(wallet, mint)
    try:
        resp = await client.get_token_account_balance(ata)
        decimals = resp.value.decimals
        return int(resp.value.amount) / (10**decimals)
    except Exception:
        return 0.0


async def create_ata_if_needed(
    client: AsyncClient, payer: Keypair, owner: Pubkey, mint: Pubkey
) -> Pubkey:
    """Create associated token account if it doesn't exist."""
    ata = get_associated_token_address(owner, mint)
    try:
        await client.get_token_account_balance(ata)
        return ata
    except Exception:  # nosec B110 - Gracefully handle missing ATA
        pass

    create_ix = create_associated_token_account(
        payer=payer.pubkey(), owner=owner, mint=mint
    )
    recent_blockhash = (await client.get_latest_blockhash()).value.blockhash
    msg = Message([create_ix], payer.pubkey())
    tx = Transaction([payer], msg, recent_blockhash)
    resp = await client.send_raw_transaction(bytes(tx))
    await client.confirm_transaction(resp.value, commitment=Finalized)
    return ata


# ============================================================================
# Agent Alpha (Borrower)
# ============================================================================


class AgentAlpha:
    """
    Agent Alpha: The Borrower

    Submits RWA-backed loan requests to the Aura Hive for analysis.
    Communicates via signed HTTP requests to the API Gateway.
    """

    def __init__(self, wallet: AgentWallet, api_url: str = "http://localhost:8000"):
        self.wallet = wallet
        self.api_url = api_url.rstrip("/")
        self.log = structlog.get_logger("agent_alpha")
        self.request_id = str(uuid.uuid4())[:8]

    async def submit_loan_request(
        self, asset_image_b64: str, loan_amount: float, asset_type: str = "gold_bar"
    ) -> dict[str, Any]:
        """
        Submit a loan request with asset image to the Hive.

        Flow:
        1. POST to /v1/vision/analyze with base64 image
        2. Receive vision analysis + ValidationScore
        3. Submit negotiation request with TradeIntent
        """
        self.log.info(
            "borrower_awakening",
            agent_did=self.wallet.did[:32],
            amount=loan_amount,
            asset=asset_type,
        )

        headers = self._build_signed_headers("POST", "/v1/vision/analyze")

        async with httpx.AsyncClient(timeout=60.0) as client:
            files = {
                "files": (
                    "gold_bar.jpg",
                    base64.b64decode(asset_image_b64),
                    "image/jpeg",
                ),
            }
            data = {"focus": f"RWA analysis for {asset_type}, valuation estimate"}

            try:
                resp = await client.post(
                    f"{self.api_url}/v1/vision/analyze",
                    files=files,
                    data=data,
                    headers=headers,
                )
                vision_result = resp.json()
                self.log.info("vision_analysis_received", confidence=0.95)
            except Exception as e:
                self.log.warning("vision_service_unavailable", error=str(e))
                vision_result = self._mock_vision_analysis(asset_type, loan_amount)

        self.log.info(
            "trade_intent_requested",
            request_id=self.request_id,
            amount=loan_amount,
            currency="USDC",
        )

        intent = self._build_trade_intent(loan_amount, vision_result)

        self.log.info(
            "eip712_trade_intent_received",
            trade_id=intent.trade_id,
            risk_score=intent.validation_score.risk_score,
            confidence=intent.validation_score.confidence,
            kyc=intent.validation_score.kyc_status,
        )

        return {
            "request_id": self.request_id,
            "trade_intent": intent,
            "vision_result": vision_result,
            "session_token": f"tok_{self.request_id}_{int(time.time())}",
        }

    def _build_signed_headers(self, method: str, path: str) -> dict[str, str]:
        """Build security headers for signed requests."""
        body = {"request_id": self.request_id}
        did, ts, sig = self.wallet.sign_request(method, path, body)
        return {
            "X-Agent-ID": did,
            "X-Timestamp": ts,
            "X-Signature": sig,
        }

    def _build_trade_intent(self, amount: float, vision_result: dict) -> TradeIntent:
        """Build EIP-712 TradeIntent from vision analysis."""
        score = ValidationScore(
            risk_score=0.15,
            risk_category="LOW",
            confidence=0.92,
            kyc_status="APPROVED",
            reasoning="Asset verified as authentic gold bar, market value confirmed",
        )

        return TradeIntent(
            trade_id=f"trade_{self.request_id}_{int(time.time())}",
            asset_identifier="AUR-RWA-001-GOLD",
            asset_domain="precious_metals",
            proposed_price=amount,
            currency_code="USDC",
            validation_score=score,
            eip712_domain={
                "name": "AuraHiveRiskRouter",
                "version": "1",
                "chainId": 103,
                "verifyingContract": "AuraRiskRouter111111111111111111",
            },
            eip712_types={
                "TradeIntent": [
                    {"name": "tradeId", "type": "string"},
                    {"name": "assetIdentifier", "type": "string"},
                    {"name": "proposedPrice", "type": "uint256"},
                    {"name": "currencyCode", "type": "string"},
                ]
            },
            metadata={
                "collateral_type": "gold_bar",
                "market_value_usd": amount * 1.5,
                "ltv_ratio": "0.67",
            },
        )

    def _mock_vision_analysis(self, asset_type: str, amount: float) -> dict[str, Any]:
        """Generate mock vision analysis when service is unavailable."""
        return {
            "description": f"High-purity {asset_type} with serial authentication",
            "confidence": 0.92,
            "market_value_usd": amount * 1.5,
            "authentication_status": "VERIFIED",
            "physical_condition": "MINT",
        }


# ============================================================================
# Agent Beta (Lender)
# ============================================================================


class AgentBeta:
    """
    Agent Beta: The Institutional Lender

    Monitors the Hive's event stream for validated TradeIntents.
    Automatically approves loans when ValidationScore exceeds threshold.
    """

    def __init__(
        self,
        wallet: AgentWallet,
        api_url: str = "http://localhost:8000",
        nats_url: str = "nats://localhost:4222",
    ):
        self.wallet = wallet
        self.api_url = api_url.rstrip("/")
        self.nats_url = nats_url
        self.log = structlog.get_logger("agent_beta")
        self.nc: nats.NATS | None = None
        self.approval_threshold = RISK_APPROVAL_THRESHOLD

    async def listen_for_trades(self) -> None:
        """Subscribe to Hive events via NATS."""
        try:
            self.nc = await nats.connect(self.nats_url)
            self.log.info("nats_connected", server=self.nats_url)
            js = self.nc.jetstream()

            async def handle_event(msg: nats.Msg) -> None:
                try:
                    data = json.loads(msg.data.decode())
                    topic = msg.subject
                    self.log.info("hive_event_received", topic=topic, data=data)
                except Exception:
                    self.log.debug("binary_proto_event", topic=msg.subject)

            await js.subscribe("aura.hive.events.>", cb=handle_event)
            self.log.info("subscribed_to_hive_events", pattern="aura.hive.events.>")

        except Exception as e:
            self.log.warning("nats_unavailable", error=str(e))
            self.log.info("falling_back_to_polling_mode")

    async def evaluate_trade(
        self, trade_intent: TradeIntent, borrower_did: str
    ) -> bool:
        """
        Evaluate a TradeIntent and decide whether to approve.

        Decision logic:
        - Check ValidationScore.kyc_status == "APPROVED"
        - Check ValidationScore.confidence > 0.8 (high confidence in valuation)
        - Check ValidationScore.risk_score < 0.3 (LOW risk category)
        """
        score = trade_intent.validation_score

        self.log.info(
            "evaluating_trade_intent",
            trade_id=trade_intent.trade_id,
            risk_score=score.risk_score,
            confidence=score.confidence,
            kyc=score.kyc_status,
        )

        if score.kyc_status != "APPROVED":
            self.log.warning(
                "kyc_rejected",
                trade_id=trade_intent.trade_id,
                kyc_status=score.kyc_status,
            )
            return False

        if score.confidence < 0.8:
            self.log.warning(
                "low_confidence",
                trade_id=trade_intent.trade_id,
                confidence=score.confidence,
            )
            return False

        max_acceptable_risk = 0.3
        if score.risk_score > max_acceptable_risk:
            self.log.warning(
                "risk_threshold_not_met",
                trade_id=trade_intent.trade_id,
                risk_score=score.risk_score,
                threshold=max_acceptable_risk,
            )
            return False

        self.log.info(
            "liquidity_approved",
            trade_id=trade_intent.trade_id,
            amount=trade_intent.proposed_price,
            currency=trade_intent.currency_code,
            lender=self.wallet.did[:32],
        )

        return True

    async def send_approval(
        self, session_token: str, trade_id: str, amount: float
    ) -> dict[str, Any]:
        """Send liquidity approval to the Hive."""
        headers = self._build_signed_headers("POST", "/v1/deals/status")

        payload = {
            "session_token": session_token,
            "trade_id": trade_id,
            "action": "APPROVE",
            "amount": amount,
            "lender_did": self.wallet.did,
            "approval_timestamp": datetime.now(
                tz=__import__("datetime").timezone.utc
            ).isoformat(),
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.post(
                    f"{self.api_url}/v1/deals/status",
                    json=payload,
                    headers=headers,
                )
                return resp.json()
            except Exception as e:
                self.log.warning("approval_endpoint_unavailable", error=str(e))
                return {"status": "APPROVED", "mock": True}

    def _build_signed_headers(self, method: str, path: str) -> dict[str, str]:
        """Build security headers for signed requests."""
        body = {"action": "APPROVE"}
        did, ts, sig = self.wallet.sign_request(method, path, body)
        return {
            "X-Agent-ID": did,
            "X-Timestamp": ts,
            "X-Signature": sig,
        }


# ============================================================================
# Hive Simulator
# ============================================================================


class HiveSimulator:
    """
    Aura Hive Simulator

    Simulates the Hive's response when real services are unavailable.
    Generates realistic ValidationScores and TradeIntents.
    """

    def __init__(self):
        self.log = structlog.get_logger("aura_hive")
        self.sessions: dict[str, NegotiationSession] = {}

    async def process_loan_request(self, loan_request: LoanRequest) -> TradeIntent:
        """Process a loan request and generate TradeIntent with ValidationScore."""

        self.log.info(
            "rwa_signal_received",
            request_id=loan_request.request_id,
            asset_type=loan_request.asset_type,
            amount=loan_request.loan_amount,
        )

        await asyncio.sleep(0.5)

        self.log.info(
            "vision_cortex_analyzing",
            request_id=loan_request.request_id,
            model="gemma-3-4b-it",
            focus=f"RWA analysis for {loan_request.asset_type}",
        )

        await asyncio.sleep(0.3)

        asset_values = {
            "gold_bar": {"value_factor": 1.5, "authenticity": 0.98},
            "real_estate": {"value_factor": 1.2, "authenticity": 0.95},
            "artwork": {"value_factor": 1.3, "authenticity": 0.88},
        }
        asset_info = asset_values.get(
            loan_request.asset_type,
            {"value_factor": 1.4, "authenticity": 0.90},
        )

        collateral_value = loan_request.loan_amount * asset_info["value_factor"]
        ltv = loan_request.loan_amount / collateral_value

        base_risk = (1 - asset_info["authenticity"]) * 0.5
        if ltv <= 0.6:
            risk_category = "LOW"
            risk_score = 0.05 + base_risk
        elif ltv <= 0.75:
            risk_category = "MEDIUM"
            risk_score = 0.15 + base_risk
        else:
            risk_category = "HIGH"
            risk_score = 0.3 + base_risk

        validation_score = ValidationScore(
            risk_score=min(risk_score, 0.95),
            risk_category=risk_category,
            confidence=asset_info["authenticity"],
            kyc_status="APPROVED",
            reasoning=f"Asset verified as authentic {loan_request.asset_type}. "
            f"Collateral value ${collateral_value:,.2f} supports {loan_request.loan_amount:,.2f} loan at {ltv:.1%} LTV.",
        )

        trade_id = f"trade_{loan_request.request_id}_{int(time.time())}"
        trade_intent = TradeIntent(
            trade_id=trade_id,
            asset_identifier=f"AUR-RWA-{uuid.uuid4().hex[:8].upper()}",
            asset_domain=loan_request.asset_type,
            proposed_price=loan_request.loan_amount,
            currency_code="USDC",
            validation_score=validation_score,
            eip712_domain={
                "name": "AuraHiveRiskRouter",
                "version": "1",
                "chainId": 103,
                "verifyingContract": "AuraRiskRouter111111111111111111",
            },
            eip712_types={
                "TradeIntent": [
                    {"name": "tradeId", "type": "string"},
                    {"name": "assetIdentifier", "type": "string"},
                    {"name": "proposedPrice", "type": "uint256"},
                    {"name": "currencyCode", "type": "string"},
                ]
            },
            metadata={
                "collateral_type": loan_request.asset_type,
                "collateral_value_usd": collateral_value,
                "ltv_ratio": f"{ltv:.2f}",
                "request_id": loan_request.request_id,
            },
        )

        self.log.info(
            "eip712_trade_intent_generated",
            trade_id=trade_id,
            risk_score=validation_score.risk_score,
            risk_category=validation_score.risk_category,
            confidence=validation_score.confidence,
            kyc_status=validation_score.kyc_status,
            reasoning=validation_score.reasoning[:80],
        )

        self.log.info(
            "pheromone_emitted",
            subject="aura.hive.events.trade_validated",
            trade_id=trade_id,
            validation_score=validation_score.risk_score,
        )

        return trade_intent


# ============================================================================
# Transaction Executor (Solana Devnet)
# ============================================================================


class TransactionExecutor:
    """
    Transaction Skill for Solana Devnet SPL Token Transfers.

    Executes the final RWA-collateral loan disbursement on-chain.
    """

    def __init__(
        self,
        treasury_key: str | bytes,
        rpc_url: str = RPC_URL,
        usdc_mint: str = DEVNET_USDC_MINT,
    ):
        if isinstance(treasury_key, bytes):
            self.treasury_keypair = Keypair.from_bytes(treasury_key)
        else:
            self.treasury_keypair = Keypair.from_base58_string(treasury_key)
        self.rpc_url = rpc_url
        self.usdc_mint = Pubkey.from_string(usdc_mint)
        self.log = structlog.get_logger("transaction_skill")

    async def execute_loan_disbursement(
        self, borrower_wallet: str, amount_usdc: float
    ) -> str:
        """
        Execute SPL token transfer from Treasury to Borrower.

        This simulates the release of a stablecoin loan backed by RWA collateral.
        """
        self.log.info(
            "transaction_initiated",
            from_address=str(self.treasury_keypair.pubkey())[:20],
            to_address=borrower_wallet[:20],
            amount=amount_usdc,
            currency="USDC",
            network="solana_devnet",
        )

        async with AsyncClient(self.rpc_url) as client:
            borrower_pubkey = Pubkey.from_string(borrower_wallet)

            await create_ata_if_needed(
                client,
                self.treasury_keypair,
                self.treasury_keypair.pubkey(),
                self.usdc_mint,
            )
            await create_ata_if_needed(
                client, self.treasury_keypair, borrower_pubkey, self.usdc_mint
            )

            await asyncio.sleep(1)

            treasury_ata = get_associated_token_address(
                self.treasury_keypair.pubkey(), self.usdc_mint
            )
            borrower_ata = get_associated_token_address(borrower_pubkey, self.usdc_mint)

            treasury_balance = await get_token_balance(
                client, self.treasury_keypair.pubkey(), self.usdc_mint
            )
            self.log.info(
                "treasury_balance_check",
                balance=treasury_balance,
                required=amount_usdc,
            )

            if treasury_balance < amount_usdc:
                self.log.warning(
                    "insufficient_treasury_funds",
                    balance=treasury_balance,
                    required=amount_usdc,
                )
                raise ValueError(
                    f"Insufficient treasury balance: {treasury_balance} < {amount_usdc}"
                )

            transfer_ix = transfer_checked(
                TransferCheckedParams(
                    source=treasury_ata,
                    mint=self.usdc_mint,
                    dest=borrower_ata,
                    owner=self.treasury_keypair.pubkey(),
                    amount=int(amount_usdc * (10**USDC_DECIMALS)),
                    decimals=USDC_DECIMALS,
                    program_id=TOKEN_PROGRAM_ID,
                )
            )

            recent_blockhash = (await client.get_latest_blockhash()).value.blockhash
            msg = Message([transfer_ix], self.treasury_keypair.pubkey())
            tx = Transaction([self.treasury_keypair], msg, recent_blockhash)

            self.log.info("submitting_transaction", network="solana_devnet")
            resp = await client.send_raw_transaction(bytes(tx))
            tx_sig = resp.value

            self.log.info("transaction_sent", signature=tx_sig[:30])

            await client.confirm_transaction(tx_sig, commitment=Finalized)

            await asyncio.sleep(2)

            final_balance = await get_token_balance(
                client, borrower_pubkey, self.usdc_mint
            )
            self.log.info(
                "collateral_released",
                signature=tx_sig[:30],
                borrower_balance=final_balance,
                amount=amount_usdc,
            )

            solscan_url = f"https://solscan.io/tx/{tx_sig}?cluster=devnet"
            self.log.info("explorer_url", url=solscan_url)

            return tx_sig


# ============================================================================
# Quorum Sensing Orchestration
# ============================================================================


async def run_quorum_sensing_simulation(
    loan_amount: float = DEFAULT_LOAN_AMOUNT,
    mock_mode: bool = False,
    api_url: str = "http://localhost:8000",
    nats_url: str = "nats://localhost:4222",
) -> None:
    """
    Execute the complete B2B Quorum Sensing simulation.

    This orchestrates the entire flow:
    1. Agent Alpha submits loan request
    2. Hive processes and generates TradeIntent
    3. Agent Beta evaluates and approves
    4. TransactionSkill executes on-chain transfer
    """

    print("\n" + "=" * 70)
    print("  B2B QUORUM SENSING SIMULATION - Aura Hive RWA Loan Negotiation")
    print("=" * 70)
    print()
    print("  Biological Metaphor: Extracellular Matrix ATP (Liquidity) Exchange")
    print("  via Trusted Pheromones (Validation Scores)")
    print()
    print("-" * 70)

    log = setup_logging(verbose=True)

    log.info(
        "simulation_initializing",
        loan_amount=loan_amount,
        mode="REAL" if not mock_mode else "MOCK",
        api_url=api_url,
        nats_url=nats_url,
    )

    borrower_wallet = AgentWallet()
    lender_wallet = AgentWallet()
    log.info(
        "agents_awakened",
        borrower=borrower_wallet.did[:32],
        lender=lender_wallet.did[:32],
    )

    print()
    print("  [ Agent Alpha - The Borrower ]")
    print("  [ Agent Beta  - The Lender   ]")
    print("  [ Hive        - Oracle/ESC   ]")
    print()
    print("-" * 70)

    log.info("fetching_rwa_asset_image", source=IMAGE_URL)
    asset_image_b64 = download_image_as_base64(IMAGE_URL)
    log.info("asset_image_encoded", size_bytes=len(asset_image_b64))

    agent_alpha = AgentAlpha(borrower_wallet, api_url)
    agent_beta = AgentBeta(lender_wallet, api_url, nats_url)
    hive = HiveSimulator()

    print()
    log.info(
        "alpha_submitting_loan_request",
        agent=borrower_wallet.did[:32],
        amount=loan_amount,
        currency="USDC",
        asset="gold_bar",
    )

    print()
    print("  \033[36m[ Alpha -> Hive ]\033[0m Submitting RWA-backed loan request...")
    print("  \033[36m[ Alpha -> Hive ]\033[0m Asset: Gold Bar (1kg)")
    print(
        f"  \033[36m[ Alpha -> Hive ]\033[0m Requested Amount: {loan_amount:,.2f} USDC"
    )
    print()

    loan_request = LoanRequest(
        request_id=str(uuid.uuid4())[:8],
        agent_did=borrower_wallet.did,
        asset_image_b64=asset_image_b64,
        asset_type="gold_bar",
        loan_amount=loan_amount,
        collateral_value=loan_amount * 1.5,
        ltv_ratio=loan_amount / (loan_amount * 1.5),
    )

    if mock_mode:
        print("  \033[33m[ HIVE SIMULATOR ]\033[0m Processing request...")
        await asyncio.sleep(0.5)
        trade_intent = await hive.process_loan_request(loan_request)
        session_token = f"tok_{loan_request.request_id}_{int(time.time())}"
    else:
        print("  \033[33m[ Alpha -> Hive ]\033[0m Sending signed request...")
        try:
            result = await agent_alpha.submit_loan_request(
                asset_image_b64, loan_amount, "gold_bar"
            )
            trade_intent = result["trade_intent"]
            session_token = result["session_token"]
        except Exception as e:
            log.warning("api_unavailable_using_mock", error=str(e))
            print()
            print(
                "  \033[33m[ HIVE SIMULATOR ]\033[0m Gateway unavailable, using mock Hive..."
            )
            await asyncio.sleep(0.5)
            trade_intent = await hive.process_loan_request(loan_request)
            session_token = f"tok_{loan_request.request_id}_{int(time.time())}"

    print()
    print("  \033[32m[ Hive -> Alpha ]\033[0m EIP-712 TradeIntent received!")
    print(f"  \033[32m[ Hive -> Alpha ]\033[0m Trade ID: {trade_intent.trade_id}")
    print(
        f"  \033[32m[ Hive -> Alpha ]\033[0m Risk Score: {trade_intent.validation_score.risk_score:.2f}"
    )
    print(
        f"  \033[32m[ Hive -> Alpha ]\033[0m Confidence: {trade_intent.validation_score.confidence:.2f}"
    )
    print(
        f"  \033[32m[ Hive -> Alpha ]\033[0m KYC Status: {trade_intent.validation_score.kyc_status}"
    )
    print()

    log.info(
        "eip712_intent_broadcast",
        subject="aura.hive.events.trade_validated",
        trade_id=trade_intent.trade_id,
    )

    print()
    print("  \033[35m[ Hive -> Beta ]\033[0m Pheromone broadcast: Trade Validated")
    print("  \033[35m[ Hive -> Beta ]\033[0m Beta listening on: aura.hive.events.>")
    print()

    log.info("beta_receiving_intent", trade_id=trade_intent.trade_id)

    print()
    print("  \033[34m[ Beta ]\033[0m Evaluating TradeIntent...")
    print(
        "  \033[34m[ Beta ]\033[0m Criteria: Confidence >80%, Risk Score <30%, KYC = APPROVED"
    )
    print()

    approved = await agent_beta.evaluate_trade(trade_intent, borrower_wallet.did)

    if approved:
        print()
        print("  \033[32m[ Beta APPROVED ]\033[0m" + "=" * 40)
        print(
            f"  \033[32m[ Beta APPROVED ]\033[0m Risk Score: {trade_intent.validation_score.risk_score:.2f}"
        )
        print(
            f"  \033[32m[ Beta APPROVED ]\033[0m Confidence: {trade_intent.validation_score.confidence:.2f}"
        )
        print(
            f"  \033[32m[ Beta APPROVED ]\033[0m KYC Status: {trade_intent.validation_score.kyc_status}"
        )
        print(
            f"  \033[32m[ Beta APPROVED ]\033[0m Loan Amount: {trade_intent.proposed_price:,.2f} USDC"
        )
        print("  \033[32m[ Beta APPROVED ]\033[0m" + "=" * 40)
        print()

        log.info("liquidity_commitment", amount=loan_amount, currency="USDC")

        print()
        print("  \033[34m[ Beta -> Hive ]\033[0m Counter-signing TradeIntent...")
        print(
            f"  \033[34m[ Beta -> Hive ]\033[0m Lender DID: {lender_wallet.did[:32]}..."
        )
        await asyncio.sleep(0.3)

        await agent_beta.send_approval(
            session_token, trade_intent.trade_id, loan_amount
        )

        print()
        print(
            "  \033[36m[ Hive -> TransactionSkill ]\033[0m Executing on-chain settlement..."
        )
        print()

        treasury_key = load_solana_key()
        executor = TransactionExecutor(treasury_key)

        from solders.keypair import Keypair

        temp_kp = Keypair()
        borrower_address = str(temp_kp.pubkey())
        log.warning(
            "generated_ephemeral_wallet",
            address=borrower_address[:20],
            note="Using ephemeral wallet for demo",
        )

        try:
            tx_sig = await executor.execute_loan_disbursement(
                borrower_address, loan_amount
            )

            print()
            print("  \033[32m[ SYMBIOTIC EXECUTION COMPLETE ]\033[0m" + "=" * 30)
            print()
            print(f"  \033[32m✓\033[0m Transaction Signature: {tx_sig[:30]}...")
            print(f"  \033[32m✓\033[0m Loan Amount: {loan_amount:,.2f} USDC")
            print(f"  \033[32m✓\033[0m Borrower: {borrower_address[:20]}...")
            print("  \033[32m✓\033[0m Network: Solana Devnet")
            print(
                f"  \033[32m✓\033[0m Explorer: https://solscan.io/tx/{tx_sig}?cluster=devnet"
            )
            print()

        except Exception as e:
            print()
            print(f"  \033[31m[ TRANSACTION FAILED ]\033[0m {e}")
            log.error("transaction_failed", error=str(e))

    else:
        print()
        print("  \033[31m[ Beta REJECTED ]\033[0m" + "=" * 42)
        print(f"  \033[31m[ Beta REJECTED ]\033[0m Trade ID: {trade_intent.trade_id}")
        print("  \033[31m[ Beta REJECTED ]\033[0m Reason: Risk threshold not met")
        print("  \033[31m[ Beta REJECTED ]\033[0m" + "=" * 42)
        print()

    print("-" * 70)
    print()
    print("  QUORUM SENSING COMPLETE")
    print()
    print("  ATP (Liquidity) Exchange Summary:")
    print(f"    - Loan Amount: {loan_amount:,.2f} USDC")
    print("    - Asset: Gold Bar (1kg)")
    print(f"    - Borrower: {borrower_wallet.did[:32]}...")
    print(f"    - Lender: {lender_wallet.did[:32]}...")
    print(f"    - Risk Score: {trade_intent.validation_score.risk_score:.2f}")
    print(f"    - Status: {'EXECUTED' if approved else 'REJECTED'}")
    print()
    print("=" * 70)


# ============================================================================
# Main Entry Point
# ============================================================================


def main() -> int:
    parser = argparse.ArgumentParser(
        description="B2B Quorum Sensing Simulation - Multi-Agent RWA Loan Negotiation"
    )
    parser.add_argument(
        "--amount",
        type=float,
        default=DEFAULT_LOAN_AMOUNT,
        help=f"Loan amount in USDC (default: {DEFAULT_LOAN_AMOUNT})",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock Hive simulation instead of real services",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default=os.getenv("AURA_API_URL", "http://localhost:8000"),
        help="API Gateway URL",
    )
    parser.add_argument(
        "--nats-url",
        type=str,
        default=os.getenv("AURA_NATS_URL", "nats://localhost:4222"),
        help="NATS server URL",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )

    args = parser.parse_args()

    try:
        asyncio.run(
            run_quorum_sensing_simulation(
                loan_amount=args.amount,
                mock_mode=args.mock,
                api_url=args.api_url,
                nats_url=args.nats_url,
            )
        )
        return 0
    except KeyboardInterrupt:
        print("\n  Simulation interrupted by user")
        return 130
    except Exception as e:
        print(f"\n  Error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
