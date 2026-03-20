#!/usr/bin/env python3
"""
In-Vivo Metabolic Test: Solana Devnet RWA Transaction

This script proves the Hive can interact with actual Solana Devnet by:
1. Generating ephemeral Keypairs for user and treasury wallets
2. Funding via SOL airdrop (falls back to treasury SOL transfer if faucet dry)
3. Executing a real SPL token transfer (USDC or fallback token)
4. Printing the Solscan Explorer URL

Usage:
    AURA_CRYPTO__SOLANA_PRIVATE_KEY=<key> python core/scripts/invivo_solana_test.py
    python core/scripts/invivo_solana_test.py --fresh  # Generate fresh wallets

Environment Variables:
    AURA_CRYPTO__SOLANA_PRIVATE_KEY  - Treasury wallet (required for treasury mode)
    AURA_CRYPTO__TEST_WALLET       - Fallback funded wallet (if airdrop fails)
    AURA_CRYPTO__SOLANA_RPC_URL    - RPC endpoint (default: devnet)
    AURA_CRYPTO__SOLANA_USDC_MINT  - Token mint to use (default: devnet USDC)
"""

import argparse
import asyncio
import os
import sys

import httpx
import structlog
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Finalized
from solders.keypair import Keypair
from solders.message import Message
from solders.pubkey import Pubkey
from solders.system_program import TransferParams, transfer
from solders.transaction import Transaction
from spl.token.constants import TOKEN_PROGRAM_ID
from spl.token.instructions import (
    TransferCheckedParams,
    create_associated_token_account,
    get_associated_token_address,
    transfer_checked,
)

logger = structlog.get_logger("invivo_solana_test")

RPC_URL = "https://api.devnet.solana.com"
DEVNET_USDC_MINT = "Gh9ZwEmdLJ8DscKNTkTqPbNwLNNBjuSzaG9Vp2KGtKJr"  # nosec B105
FALLBACK_TOKEN_MINT = "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU"  # nosec B105
SOL_DECIMALS = 9
USDC_DECIMALS = 6
TEST_AMOUNT_USDC = 10.0
SOL_AIRDROP_AMOUNT = 0.02
USDC_AIRDROP_AMOUNT = 100.0


def get_token_mint() -> str:
    """Get the token mint to use (USDC or fallback)."""
    return os.getenv("AURA_CRYPTO__SOLANA_USDC_MINT", DEVNET_USDC_MINT)


async def request_sol_airdrop(
    client: AsyncClient, pubkey: Pubkey, amount: float
) -> bool:
    """Request SOL airdrop from devnet faucet."""
    lamports = int(amount * (10**SOL_DECIMALS))
    try:
        resp = await client.request_airdrop(pubkey, lamports)
        await client.confirm_transaction(resp.value, commitment=Finalized)
        return True
    except Exception:
        return False


async def get_token_balance(client: AsyncClient, wallet: Pubkey, mint: Pubkey) -> float:
    """Get SPL token balance for a wallet."""
    ata = get_associated_token_address(wallet, mint)
    try:
        resp = await client.get_token_account_balance(ata)
        decimals = resp.value.decimals
        return int(resp.value.amount) / (10**decimals)
    except Exception:
        return 0.0


async def get_sol_balance(client: AsyncClient, pubkey: Pubkey) -> float:
    """Get SOL balance for a wallet."""
    try:
        resp = await client.get_balance(pubkey)
        return int(resp.value) / (10**SOL_DECIMALS)
    except Exception:
        return 0.0


async def transfer_sol(
    client: AsyncClient,
    sender_keypair: Keypair,
    recipient_pubkey: Pubkey,
    amount: float,
) -> str:
    """Transfer SOL from sender to recipient."""
    transfer_ix = transfer(
        TransferParams(
            from_pubkey=sender_keypair.pubkey(),
            to_pubkey=recipient_pubkey,
            lamports=int(amount * (10**SOL_DECIMALS)),
        )
    )

    recent_blockhash = (await client.get_latest_blockhash()).value.blockhash
    msg = Message([transfer_ix], sender_keypair.pubkey())
    tx = Transaction([sender_keypair], msg, recent_blockhash)

    resp = await client.send_raw_transaction(bytes(tx))
    tx_sig = resp.value
    await client.confirm_transaction(tx_sig, commitment=Finalized)

    return str(tx_sig)


async def create_ata_if_needed(
    client: AsyncClient, payer: Keypair, owner: Pubkey, mint: Pubkey
) -> Pubkey:
    """Create associated token account if it doesn't exist."""
    ata = get_associated_token_address(owner, mint)

    # Check if ATA exists
    try:
        await client.get_token_account_balance(ata)
        return ata  # Already exists
    except Exception:  # nosec B110 - Gracefully handle missing account
        pass

    # Create ATA
    create_ix = create_associated_token_account(
        payer=payer.pubkey(), owner=owner, mint=mint
    )

    recent_blockhash = (await client.get_latest_blockhash()).value.blockhash
    msg = Message([create_ix], payer.pubkey())
    tx = Transaction([payer], msg, recent_blockhash)

    resp = await client.send_raw_transaction(bytes(tx))
    await client.confirm_transaction(resp.value, commitment=Finalized)

    return ata


async def request_usdc_faucet(
    client: AsyncClient, pubkey: Pubkey, mint: Pubkey, amount: float
) -> bool:
    """
    Request USDC airdrop via SPL token faucet.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as http:
            # Try the SPL token faucet API
            resp = await http.post(
                "https://spl-token-faucet.com/airdrop",
                json={"wallet": str(pubkey), "amount": amount, "mint": str(mint)},
            )
            if resp.status_code == 200:
                return True
    except Exception:  # nosec B110 - Gracefully handle faucet failures
        pass

    # Alternative: Try via RPC
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "request_faucet_funds",
            "params": [str(pubkey)],
        }
        r = await client._provider.session.post(RPC_URL, json=payload)
        if r.status_code == 200:
            return True
    except Exception:  # nosec B110 - Gracefully handle RPC failures
        pass

    return False


async def execute_usdc_transfer(
    client: AsyncClient,
    sender_keypair: Keypair,
    recipient_pubkey: Pubkey,
    mint: Pubkey,
    amount: float,
) -> str:
    """Execute USDC transfer from sender to recipient."""
    # Ensure ATAs exist
    await create_ata_if_needed(client, sender_keypair, sender_keypair.pubkey(), mint)
    await create_ata_if_needed(client, sender_keypair, recipient_pubkey, mint)

    await asyncio.sleep(1)  # Allow ATA creation to settle

    sender_ata = get_associated_token_address(sender_keypair.pubkey(), mint)
    recipient_ata = get_associated_token_address(recipient_pubkey, mint)

    transfer_ix = transfer_checked(
        TransferCheckedParams(
            source=sender_ata,
            mint=mint,
            dest=recipient_ata,
            owner=sender_keypair.pubkey(),
            amount=int(amount * (10**USDC_DECIMALS)),
            decimals=USDC_DECIMALS,
            program_id=TOKEN_PROGRAM_ID,
        )
    )

    recent_blockhash = (await client.get_latest_blockhash()).value.blockhash
    msg = Message([transfer_ix], sender_keypair.pubkey())
    tx = Transaction([sender_keypair], msg, recent_blockhash)

    resp = await client.send_raw_transaction(bytes(tx))
    tx_sig = resp.value
    await client.confirm_transaction(tx_sig, commitment=Finalized)

    return str(tx_sig)


async def run_fresh_test() -> int:
    """Run test with fresh wallets and faucet airdrops."""
    print("\n" + "=" * 60)
    print("In-Vivo Metabolic Test: Solana Devnet (Fresh Wallets)")
    print("=" * 60)
    print("Network:    Solana Devnet")
    print(f"RPC:        {RPC_URL}")
    print(f"USDC Mint:  {DEVNET_USDC_MINT}")
    print(f"Amount:     {TEST_AMOUNT_USDC} USDC")
    print()

    async with AsyncClient(RPC_URL) as client:
        # Generate fresh wallets
        print("[1/7] Generating ephemeral wallets...")
        treasury_keypair = Keypair()
        user_keypair = Keypair()
        print(f"  Treasury: {treasury_keypair.pubkey()}")
        print(f"  User:     {user_keypair.pubkey()}")
        print()

        # Fund treasury with SOL
        print("[2/7] Funding treasury with SOL...")
        await request_sol_airdrop(client, treasury_keypair.pubkey(), SOL_AIRDROP_AMOUNT)
        await asyncio.sleep(2)
        treasury_sol = await get_sol_balance(client, treasury_keypair.pubkey())
        print(
            f"  Treasury SOL: {treasury_sol:.4f} {'✅' if treasury_sol > 0.5 else '⚠️'}"
        )
        print()

        # Create treasury USDC ATA
        print("[3/7] Setting up treasury USDC account...")
        mint_pubkey = Pubkey.from_string(DEVNET_USDC_MINT)
        await create_ata_if_needed(
            client, treasury_keypair, treasury_keypair.pubkey(), mint_pubkey
        )
        treasury_usdc = await get_token_balance(
            client, treasury_keypair.pubkey(), mint_pubkey
        )
        print(f"  Treasury USDC: {treasury_usdc:.2f}")
        print()

        # Fund treasury with USDC if needed
        if treasury_usdc < TEST_AMOUNT_USDC:
            print("[4/7] Requesting USDC airdrop for treasury...")

            # Try fallback wallet first
            fallback_key = os.getenv("AURA_CRYPTO__TEST_WALLET", "")
            if fallback_key:
                try:
                    fallback_kp = Keypair.from_base58_string(fallback_key)
                    print("  Using fallback wallet...")

                    # Fund fallback with SOL
                    await request_sol_airdrop(client, fallback_kp.pubkey(), 1.0)
                    await asyncio.sleep(2)

                    # Create ATA for fallback
                    await create_ata_if_needed(
                        client, fallback_kp, fallback_kp.pubkey(), mint_pubkey
                    )
                    await asyncio.sleep(1)

                    # Request USDC to fallback
                    await request_usdc_faucet(
                        client, fallback_kp.pubkey(), mint_pubkey, USDC_AIRDROP_AMOUNT
                    )
                    await asyncio.sleep(3)

                    fallback_usdc = await get_token_balance(
                        client, fallback_kp.pubkey(), mint_pubkey
                    )
                    print(f"  Fallback USDC: {fallback_usdc:.2f}")

                    # Transfer from fallback to treasury
                    if fallback_usdc >= TEST_AMOUNT_USDC:
                        print(f"  Transferring {TEST_AMOUNT_USDC} USDC to treasury...")
                        tx = await execute_usdc_transfer(
                            client,
                            fallback_kp,
                            treasury_keypair.pubkey(),
                            mint_pubkey,
                            TEST_AMOUNT_USDC,
                        )
                        print(f"  Transfer signature: {tx[:30]}... ✅")
                        await asyncio.sleep(3)

                except Exception as e:
                    print(f"  Fallback failed: {e}")
            else:
                print("  No fallback wallet (AURA_CRYPTO__TEST_WALLET)")
                print("  Trying direct USDC faucet...")
                await request_usdc_faucet(
                    client, treasury_keypair.pubkey(), mint_pubkey, USDC_AIRDROP_AMOUNT
                )
                await asyncio.sleep(3)

            treasury_usdc = await get_token_balance(
                client, treasury_keypair.pubkey(), mint_pubkey
            )
            print(f"  Treasury USDC: {treasury_usdc:.2f}")

        treasury_usdc = await get_token_balance(
            client, treasury_keypair.pubkey(), mint_pubkey
        )
        print()

        if treasury_usdc < TEST_AMOUNT_USDC:
            print("❌ Insufficient treasury USDC for transfer")
            print(f"   Required: {TEST_AMOUNT_USDC} USDC")
            print(f"   Available: {treasury_usdc:.2f} USDC")
            print()
            print("   Visit https://spl-token-faucet.com/ to fund:")
            print(f"   Treasury: {treasury_keypair.pubkey()}")
            return 1

        # Fund user with SOL
        print("[5/7] Funding user wallet with SOL...")
        await request_sol_airdrop(client, user_keypair.pubkey(), SOL_AIRDROP_AMOUNT)
        await asyncio.sleep(2)
        user_sol = await get_sol_balance(client, user_keypair.pubkey())
        print(f"  User SOL: {user_sol:.4f}")

        # Create user USDC ATA
        await create_ata_if_needed(
            client, user_keypair, user_keypair.pubkey(), mint_pubkey
        )
        await asyncio.sleep(1)
        print()

        # Execute transfer
        print("[6/7] Executing RWA collateral transfer...")
        print(f"  Amount: {TEST_AMOUNT_USDC} USDC")
        print(f"  From:   {str(treasury_keypair.pubkey())[:20]}...")
        print(f"  To:     {str(user_keypair.pubkey())[:20]}...")
        print()

        try:
            tx_sig = await execute_usdc_transfer(
                client,
                treasury_keypair,
                user_keypair.pubkey(),
                mint_pubkey,
                TEST_AMOUNT_USDC,
            )
        except Exception as e:
            print(f"  ❌ Transfer failed: {e}")
            return 1

        # Verify
        print("[7/7] Verifying transfer...")
        await asyncio.sleep(2)
        user_usdc = await get_token_balance(client, user_keypair.pubkey(), mint_pubkey)
        print(f"  User USDC: {user_usdc:.2f}")

        if user_usdc < TEST_AMOUNT_USDC * 0.99:
            print("  ⚠️ Transfer may not have completed fully")

        print()

        # Success
        solscan_url = f"https://solscan.io/tx/{tx_sig}?cluster=devnet"

        print("=" * 60)
        print("✅ SUCCESS: In-Vivo Metabolic Test Passed")
        print("=" * 60)
        print()
        print("Transaction Details:")
        print(f"  Signature: {tx_sig}")
        print(f"  Amount:   {TEST_AMOUNT_USDC} USDC")
        print(f"  From:     {treasury_keypair.pubkey()}")
        print(f"  To:       {user_keypair.pubkey()}")
        print()
        print("🔗 View on Solscan:")
        print(f"   {solscan_url}")
        print()
        print("⚠️  Debug keys (hex):")
        print(f"   Treasury: {bytes(treasury_keypair).hex()[:40]}...")
        print(f"   User:     {bytes(user_keypair).hex()[:40]}...")
        print()

        return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description="In-Vivo Solana Devnet RWA Test")
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Generate fresh wallets (no treasury key needed)",
    )
    args = parser.parse_args()

    if args.fresh or not os.getenv("AURA_CRYPTO__SOLANA_PRIVATE_KEY"):
        return await run_fresh_test()

    # Treasury mode (existing behavior)
    treasury_key = os.getenv("AURA_CRYPTO__SOLANA_PRIVATE_KEY", "")
    try:
        treasury_keypair = Keypair.from_base58_string(treasury_key)
    except Exception as e:
        print(f"Error: Invalid treasury key: {e}")
        return 1

    print("\n" + "=" * 60)
    print("In-Vivo Metabolic Test: Solana Devnet (Treasury Mode)")
    print("=" * 60)
    print(f"Treasury: {treasury_keypair.pubkey()}")
    print(f"Amount:   {TEST_AMOUNT_USDC} USDC")
    print()

    async with AsyncClient(RPC_URL) as client:
        print("[1/4] Generating user wallet...")
        user_keypair = Keypair()
        print(f"  User: {user_keypair.pubkey()}")

        print("[2/4] Funding user with SOL...")

        # Try airdrop first
        airdrop_ok = await request_sol_airdrop(
            client, user_keypair.pubkey(), SOL_AIRDROP_AMOUNT
        )
        await asyncio.sleep(2)

        if not airdrop_ok:
            print("  Airdrop failed - using treasury to fund...")
            # Transfer SOL from treasury to user
            await transfer_sol(
                client, treasury_keypair, user_keypair.pubkey(), SOL_AIRDROP_AMOUNT
            )
            await asyncio.sleep(2)

        user_sol = await get_sol_balance(client, user_keypair.pubkey())
        print(f"  User SOL: {user_sol:.4f}")

        # Determine which token mint to use
        treasury_usdc = await get_token_balance(
            client, treasury_keypair.pubkey(), Pubkey.from_string(DEVNET_USDC_MINT)
        )
        treasury_fallback = await get_token_balance(
            client, treasury_keypair.pubkey(), Pubkey.from_string(FALLBACK_TOKEN_MINT)
        )

        if treasury_usdc >= TEST_AMOUNT_USDC:
            token_mint = DEVNET_USDC_MINT
            token_name = "USDC"  # nosec B105
            print(f"  Using USDC (balance: {treasury_usdc:.2f})")
        elif treasury_fallback >= TEST_AMOUNT_USDC:
            token_mint = FALLBACK_TOKEN_MINT
            token_name = "TEST"  # nosec B105
            print(f"  Using TEST token (balance: {treasury_fallback:.2f})")
        else:
            print(f"  Treasury USDC: {treasury_usdc:.2f}")
            print(f"  Treasury TEST: {treasury_fallback:.2f}")
            print("  ❌ Insufficient tokens for transfer")
            return 1

        # Create user ATA using treasury as payer (treasury has SOL)
        print(f"  Creating user {token_name} token account...")
        await create_ata_if_needed(
            client,
            treasury_keypair,  # Use treasury as payer
            user_keypair.pubkey(),
            Pubkey.from_string(token_mint),
        )
        await asyncio.sleep(1)

        print(f"[3/4] Executing {token_name} transfer...")
        try:
            tx_sig = await execute_usdc_transfer(
                client,
                treasury_keypair,
                user_keypair.pubkey(),
                Pubkey.from_string(token_mint),
                TEST_AMOUNT_USDC,
            )
        except Exception as e:
            print(f"  ❌ Failed: {e}")
            return 1

        print("[4/4] Verifying...")
        await asyncio.sleep(2)
        user_balance = await get_token_balance(
            client, user_keypair.pubkey(), Pubkey.from_string(token_mint)
        )
        print(f"  User {token_name}: {user_balance:.2f}")

        solscan_url = f"https://solscan.io/tx/{tx_sig}?cluster=devnet"
        print()
        print("=" * 60)
        print("✅ SUCCESS: In-Vivo Metabolic Test Passed")
        print("=" * 60)
        print(f"  Token: {token_name}")
        print(f"  Amount: {TEST_AMOUNT_USDC}")
        print(f"  Signature: {tx_sig}")
        print(f"🔗 {solscan_url}")
        return 0


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="%H:%M:%S"),
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
    sys.exit(asyncio.run(main()))
