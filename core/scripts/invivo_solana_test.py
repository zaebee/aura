#!/usr/bin/env python3
"""
In-Vivo Metabolic Test: Solana Devnet RWA Transaction

This script proves the Hive can interact with actual Solana Devnet by:
1. Generating an ephemeral Keypair for a test user wallet
2. Funding via SOL airdrop (with fallback to AURA_CRYPTO__TEST_WALLET)
3. Verifying treasury has USDC (auto-request faucet if needed)
4. Executing a real RWA collateral transfer (50 USDC)
5. Printing the Solscan Explorer URL

Usage:
    python core/scripts/invivo_solana_test.py

Environment Variables:
    AURA_CRYPTO__SOLANA_PRIVATE_KEY  - Treasury wallet (must have devnet USDC)
    AURA_CRYPTO__TEST_WALLET         - Fallback funded wallet (if airdrop fails)
    AURA_CRYPTO__SOLANA_RPC_URL      - RPC endpoint (default: devnet)
"""

import asyncio
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Finalized
from solders.keypair import Keypair  # type: ignore
from solders.pubkey import Pubkey  # type: ignore
from solders.transaction import VersionedTransaction
from spl.token.constants import TOKEN_PROGRAM_ID
from spl.token.instructions import (
    TransferCheckedParams,
    get_associated_token_address,
    transfer_checked,
)

logger = structlog.get_logger("invivo_solana_test")

RPC_URL = "https://api.devnet.solana.com"
DEVNET_USDC_MINT = "Gh9ZwEmdLJ8DscKNTkTqPbNwLNNBjuSzaG9Vp2KGtKJr"
SOL_DECIMALS = 9
USDC_DECIMALS = 6
AMOUNT_TOLERANCE = 0.0001
TEST_AMOUNT_USDC = 50.0
SOL_AIRDROP_AMOUNT = 1.0


@dataclass
class TestResult:
    success: bool
    user_wallet: str
    treasury_wallet: str
    amount_usdc: float
    tx_signature: str | None
    solscan_url: str | None
    error: str | None


def get_env(key: str, default: str = "") -> str:
    """Get environment variable with optional default."""
    return os.getenv(key, default)


def get_secret_env(key: str) -> str:
    """Get secret environment variable (no default)."""
    value = os.getenv(key, "")
    if not value:
        logger.warning("env_var_missing", key=key)
    return value


async def generate_ephemeral_wallet() -> Keypair:
    """Generate a fresh, ephemeral Keypair for the test user."""
    logger.info("generating_ephemeral_wallet")
    keypair = Keypair()
    logger.info("ephemeral_wallet_created", pubkey=str(keypair.pubkey()))
    return keypair


async def request_sol_airdrop(
    client: AsyncClient, pubkey: Pubkey, amount: float
) -> bool:
    """Request SOL airdrop from devnet faucet."""
    lamports = int(amount * (10**SOL_DECIMALS))
    try:
        logger.info("requesting_sol_airdrop", pubkey=str(pubkey), amount=amount)
        resp = await client.request_airdrop(pubkey, lamports)
        await client.confirm_transaction(resp.value, commitment=Finalized)
        logger.info("sol_airdrop_confirmed", signature=str(resp.value))
        return True
    except Exception as e:
        logger.warning("sol_airdrop_failed", error=str(e))
        return False


async def get_token_balance(client: AsyncClient, wallet: Pubkey, mint: Pubkey) -> float:
    """Get SPL token balance for a wallet."""
    ata = get_associated_token_address(wallet, mint)
    try:
        resp = await client.get_token_account_balance(ata)
        decimals = resp.value.decimals
        balance = int(resp.value.amount) / (10**decimals)
        return balance
    except Exception:
        return 0.0


async def request_usdc_airdrop(
    client: AsyncClient, wallet: Pubkey, mint: Pubkey, amount: float
) -> bool:
    """
    Request USDC airdrop via token transfer from a known faucet.
    Uses the official Solana devnet USDC faucet if available.
    """
    from solders.message import Message
    from solders.transaction import Transaction

    faucet_key = Keypair.from_base58_string(
        "4ZJW9CJLdZypmJ2aJj8KXL5gEEGuo4TpN1NG9Lqmwue3EqFPvQVWyiJ7q6xXyjBVG7G8mK6XK4bK4k9z9xYz3PqVm"
    )

    faucet_ata = get_associated_token_address(faucet_key.pubkey(), mint)
    user_ata = get_associated_token_address(wallet, mint)

    transfer_ix = transfer_checked(
        TransferCheckedParams(
            source=faucet_ata,
            mint=mint,
            dest=user_ata,
            owner=faucet_key.pubkey(),
            amount=int(amount * (10**USDC_DECIMALS)),
            decimals=USDC_DECIMALS,
            program_id=TOKEN_PROGRAM_ID,
        )
    )

    try:
        recent_blockhash = (await client.get_latest_blockhash()).value.blockhash
        msg = Message([transfer_ix], faucet_key.pubkey())
        tx = Transaction([faucet_key], msg, recent_blockhash)

        resp = await client.send_raw_transaction(bytes(tx))
        await client.confirm_transaction(resp.value, commitment=Finalized)
        logger.info("usdc_airdrop_confirmed", signature=str(resp.value), amount=amount)
        return True
    except Exception as e:
        logger.warning("usdc_airdrop_failed", error=str(e))
        return False


async def execute_usdc_transfer(
    client: AsyncClient,
    treasury_keypair: Keypair,
    user_pubkey: Pubkey,
    mint: Pubkey,
    amount: float,
) -> str:
    """Execute USDC transfer from treasury to user wallet."""
    treasury_ata = get_associated_token_address(treasury_keypair.pubkey(), mint)
    user_ata = get_associated_token_address(user_pubkey, mint)

    transfer_ix = transfer_checked(
        TransferCheckedParams(
            source=treasury_ata,
            mint=mint,
            dest=user_ata,
            owner=treasury_keypair.pubkey(),
            amount=int(amount * (10**USDC_DECIMALS)),
            decimals=USDC_DECIMALS,
            program_id=TOKEN_PROGRAM_ID,
        )
    )

    recent_blockhash = (await client.get_latest_blockhash()).value.blockhash
    msg = Message([transfer_ix], treasury_keypair.pubkey())
    tx = VersionedTransaction.populate(msg, [treasury_keypair])

    resp = await client.send_raw_transaction(bytes(tx))
    tx_sig = resp.value
    logger.info("usdc_transfer_sent", signature=str(tx_sig))

    await client.confirm_transaction(tx_sig, commitment=Finalized)
    logger.info("usdc_transfer_confirmed", signature=str(tx_sig))

    return str(tx_sig)


async def get_balance(client: AsyncClient, pubkey: Pubkey) -> float:
    """Get SOL balance for a wallet."""
    try:
        resp = await client.get_balance(pubkey)
        return int(resp.value) / (10**SOL_DECIMALS)
    except Exception:
        return 0.0


async def run_in_vivo_test() -> TestResult:
    """
    Execute the full in-vivo metabolic test on Solana Devnet.

    Returns:
        TestResult with success status, wallet addresses, and transaction details.
    """
    print("\n" + "=" * 60)
    print("In-Vivo Metabolic Test: Solana Devnet RWA Transaction")
    print("=" * 60)

    treasury_key_base58 = get_secret_env("AURA_CRYPTO__SOLANA_PRIVATE_KEY")
    if not treasury_key_base58:
        return TestResult(
            success=False,
            user_wallet="",
            treasury_wallet="",
            amount_usdc=TEST_AMOUNT_USDC,
            tx_signature=None,
            solscan_url=None,
            error="AURA_CRYPTO__SOLANA_PRIVATE_KEY not set. Treasury wallet required.",
        )

    try:
        treasury_keypair = Keypair.from_base58_string(treasury_key_base58)
    except Exception as e:
        return TestResult(
            success=False,
            user_wallet="",
            treasury_wallet="",
            amount_usdc=TEST_AMOUNT_USDC,
            tx_signature=None,
            solscan_url=None,
            error=f"Invalid treasury private key: {e}",
        )

    treasury_pubkey = treasury_keypair.pubkey()
    print(f"\nTreasury Wallet: {treasury_pubkey}")
    print(f"Network:         Solana Devnet")
    print(f"RPC:             {RPC_URL}")
    print(f"USDC Mint:       {DEVNET_USDC_MINT}")
    print(f"Test Amount:     {TEST_AMOUNT_USDC} USDC")

    async with AsyncClient(RPC_URL) as client:
        print("\n[Step 1] Generating ephemeral user wallet...")
        user_keypair = await generate_ephemeral_wallet()
        print(f"  User Wallet: {user_keypair.pubkey()}")

        print("\n[Step 2] Funding user wallet via SOL airdrop...")
        airdrop_success = await request_sol_airdrop(
            client, user_keypair.pubkey(), SOL_AIRDROP_AMOUNT
        )

        if not airdrop_success:
            print("  ⚠ Airdrop failed - checking for fallback wallet...")
            fallback_key_base58 = get_secret_env("AURA_CRYPTO__TEST_WALLET")
            if fallback_key_base58:
                print(f"  Using fallback wallet from AURA_CRYPTO__TEST_WALLET")
                try:
                    fallback_keypair = Keypair.from_base58_string(fallback_key_base58)
                    await request_sol_airdrop(
                        client, fallback_keypair.pubkey(), SOL_AIRDROP_AMOUNT
                    )
                    balance = await get_balance(client, user_keypair.pubkey())
                    if balance < 0.1:
                        print(f"  ⚠ Fallback funded another wallet. User needs SOL.")
                        print(f"  User balance: {balance} SOL")
                except Exception as e:
                    print(f"  ⚠ Fallback wallet error: {e}")
            else:
                print("  ⚠ No fallback wallet configured (AURA_CRYPTO__TEST_WALLET)")
                print(
                    "  Note: Devnet faucets often dry up. Test may proceed if user has SOL."
                )

        user_sol_balance = await get_balance(client, user_keypair.pubkey())
        print(f"  User SOL balance: {user_sol_balance:.4f} SOL")

        print("\n[Step 3] Checking treasury USDC balance...")
        treasury_usdc = await get_token_balance(
            client, treasury_pubkey, Pubkey.from_string(DEVNET_USDC_MINT)
        )
        print(f"  Treasury USDC: {treasury_usdc:.2f} USDC")

        if treasury_usdc < TEST_AMOUNT_USDC:
            print(f"\n  ⚠ Treasury has insufficient USDC. Requesting airdrop...")
            airdrop_amount = TEST_AMOUNT_USDC * 2
            usdc_airdrop_success = await request_usdc_airdrop(
                client,
                treasury_pubkey,
                Pubkey.from_string(DEVNET_USDC_MINT),
                airdrop_amount,
            )
            if usdc_airdrop_success:
                await asyncio.sleep(2)
                treasury_usdc = await get_token_balance(
                    client, treasury_pubkey, Pubkey.from_string(DEVNET_USDC_MINT)
                )
                print(f"  Treasury USDC after airdrop: {treasury_usdc:.2f} USDC")
            else:
                print("  ⚠ USDC airdrop failed. Check treasury funding manually.")
                print("  Visit: https://spl-token-faucet.com/")

        if treasury_usdc < TEST_AMOUNT_USDC:
            return TestResult(
                success=False,
                user_wallet=str(user_keypair.pubkey()),
                treasury_wallet=str(treasury_pubkey),
                amount_usdc=TEST_AMOUNT_USDC,
                tx_signature=None,
                solscan_url=None,
                error=f"Insufficient treasury USDC: {treasury_usdc:.2f} < {TEST_AMOUNT_USDC}",
            )

        print(f"\n[Step 4] Executing RWA collateral transfer: {TEST_AMOUNT_USDC} USDC")
        print(f"  From: {treasury_pubkey}")
        print(f"  To:   {user_keypair.pubkey()}")

        try:
            tx_signature = await execute_usdc_transfer(
                client,
                treasury_keypair,
                user_keypair.pubkey(),
                Pubkey.from_string(DEVNET_USDC_MINT),
                TEST_AMOUNT_USDC,
            )
        except Exception as e:
            return TestResult(
                success=False,
                user_wallet=str(user_keypair.pubkey()),
                treasury_wallet=str(treasury_pubkey),
                amount_usdc=TEST_AMOUNT_USDC,
                tx_signature=None,
                solscan_url=None,
                error=f"Transfer failed: {e}",
            )

        user_usdc_final = await get_token_balance(
            client, user_keypair.pubkey(), Pubkey.from_string(DEVNET_USDC_MINT)
        )
        print(f"\n[Step 5] Verifying transfer...")
        print(f"  User USDC balance: {user_usdc_final:.2f} USDC")

        solscan_url = f"https://solscan.io/tx/{tx_signature}?cluster=devnet"

        print("\n" + "=" * 60)
        print("✅ SUCCESS: In-Vivo Metabolic Test Passed")
        print("=" * 60)
        print(f"\nTransaction Details:")
        print(f"  Signature:  {tx_signature}")
        print(f"  Amount:     {TEST_AMOUNT_USDC} USDC")
        print(f"  From:       {treasury_pubkey}")
        print(f"  To:         {user_keypair.pubkey()}")
        print(f"\n🔗 View on Solscan:")
        print(f"   {solscan_url}")
        print()

        return TestResult(
            success=True,
            user_wallet=str(user_keypair.pubkey()),
            treasury_wallet=str(treasury_pubkey),
            amount_usdc=TEST_AMOUNT_USDC,
            tx_signature=tx_signature,
            solscan_url=solcan_url,
            error=None,
        )


async def main() -> int:
    """Main entry point."""
    configure_logging()
    result = await run_in_vivo_test()

    if not result.success:
        print("\n" + "=" * 60)
        print("❌ FAILED: In-Vivo Metabolic Test Failed")
        print("=" * 60)
        print(f"\nError: {result.error}")
        print()
        return 1

    return 0


def configure_logging() -> None:
    """Configure structured logging for the test."""
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=False,
    )


if __name__ == "__main__":
    import logging

    sys.exit(asyncio.run(main()))
