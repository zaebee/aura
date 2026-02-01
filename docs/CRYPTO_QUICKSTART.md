# Crypto Payment Quick Start Guide

## Prerequisites

✅ **All code implemented** - Ready to test!
- Protocol buffers generated
- Database models created
- Solana provider implemented
- API endpoints integrated

## Step 1: Apply Database Migration

```bash
# Start database
docker-compose up -d db

# Wait for database to be ready
docker-compose exec db pg_isready -U user -d aura_db

# Apply migration
docker-compose exec core-service alembic upgrade head

# Verify table created
docker-compose exec db psql -U user -d aura_db -c "\d locked_deals"
```

Expected output:
```
                Table "public.locked_deals"
     Column        |            Type             | ...
-------------------+-----------------------------+-----
 id                | uuid                        | ...
 item_id           | character varying           | ...
 payment_memo      | character varying           | ... unique
 status            | dealstatus                  | ...
 ...
```

## Step 2: Generate Solana Keypair (Devnet)

```bash
# Install Solana CLI (if not already installed)
sh -c "$(curl -sSfL https://release.solana.com/stable/install)"
export PATH="$HOME/.local/share/solana/install/active_release/bin:$PATH"

# Generate devnet keypair
solana-keygen new --outfile ~/.config/solana/devnet-keypair.json

# Get public key (this is where payments will be sent)
solana-keygen pubkey ~/.config/solana/devnet-keypair.json
# Example output: 7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU

# Export private key as base58
PRIVATE_KEY=$(solana-keygen export ~/.config/solana/devnet-keypair.json)
echo "Your private key: $PRIVATE_KEY"

# Request devnet airdrop (free test SOL)
solana airdrop 5 $(solana-keygen pubkey ~/.config/solana/devnet-keypair.json) --url devnet

# Check balance
solana balance $(solana-keygen pubkey ~/.config/solana/devnet-keypair.json) --url devnet
```

## Step 3: Configure Environment

```bash
# Create .env file
cat > .env << EOF
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/aura_db

# LLM (use rule-based for testing)
LLM_MODEL=rule

# OpenTelemetry
OTEL_SERVICE_NAME=aura-core
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# Crypto Payments (ENABLE HERE)
CRYPTO_ENABLED=true
CRYPTO_PROVIDER=solana
CRYPTO_CURRENCY=SOL

# Solana Configuration (DEVNET)
SOLANA_PRIVATE_KEY=<YOUR_BASE58_PRIVATE_KEY>
SOLANA_RPC_URL=https://api.devnet.solana.com
SOLANA_NETWORK=devnet
SOLANA_USDC_MINT=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v

# Deal expiration
DEAL_TTL_SECONDS=3600
EOF

# Load environment
export $(cat .env | grep -v '^#' | xargs)
```

## Step 4: Start Services

```bash
# Build and start all services
docker-compose up --build

# In another terminal, check logs
docker-compose logs -f core-service | grep crypto

# Expected log output:
# crypto_provider_initialized provider="solana" network="devnet" ...
# server_started ... crypto_enabled=True
```

## Step 5: Test Payment Flow

### 5.1 Negotiate Deal (Get Payment Instructions)

```bash
# Create a test item first (if needed)
docker-compose exec db psql -U user -d aura_db -c "
INSERT INTO inventory_items (id, name, base_price, floor_price, is_active)
VALUES ('room-101', 'Beach Villa', 200.0, 150.0, true)
ON CONFLICT DO NOTHING;
"

# Negotiate
curl -X POST http://localhost:8000/v1/negotiate \
  -H "Content-Type: application/json" \
  -d '{
    "item_id": "room-101",
    "bid_amount": 160.0,
    "currency": "USD",
    "agent_did": "did:key:test123"
  }'
```

Expected response:
```json
{
  "session_token": "sess_...",
  "status": "accepted",
  "payment_required": true,
  "data": {
    "final_price": 160.0,
    "payment_instructions": {
      "deal_id": "123e4567-e89b-12d3-a456-426614174000",
      "wallet_address": "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
      "amount": 160.0,
      "currency": "SOL",
      "memo": "abc12345",
      "network": "devnet",
      "expires_at": 1738234567
    }
  }
}
```

**Save the `deal_id` and `memo`!**

### 5.2 Send Payment

**Option A: Using Solana CLI**
```bash
# Replace with actual values from response
WALLET_ADDRESS="7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"
AMOUNT=160
MEMO="abc12345"

# Send payment with memo
solana transfer $WALLET_ADDRESS $AMOUNT \
  --with-memo "$MEMO" \
  --url devnet \
  --keypair ~/.config/solana/devnet-keypair.json

# Example output:
# Signature: 5Kn7... (transaction hash)
```

**Option B: Using Phantom Wallet**
1. Connect to Devnet in Phantom
2. Send $AMOUNT SOL to $WALLET_ADDRESS
3. Add $MEMO in the memo field

### 5.3 Check Payment Status

```bash
# Replace with actual deal_id
DEAL_ID="123e4567-e89b-12d3-a456-426614174000"

# Poll status (repeat every 5 seconds)
curl -X POST http://localhost:8000/v1/deals/$DEAL_ID/status

# Initial response (PENDING):
{
  "status": "PENDING",
  "payment_instructions": { ... }
}

# After ~30 seconds (PAID):
{
  "status": "PAID",
  "secret": {
    "reservation_code": "RESERVATION-CODE-HERE",
    "item_name": "Beach Villa",
    "final_price": 160.0,
    "paid_at": 1738234567
  },
  "proof": {
    "transaction_hash": "5Kn7...",
    "block_number": "12345678",
    "from_address": "YourWalletAddress",
    "confirmed_at": 1738234567
  }
}
```

## Step 6: Verify in Database

```bash
# Check locked_deals table
docker-compose exec db psql -U user -d aura_db -c "
SELECT
  id,
  item_name,
  final_price,
  currency,
  payment_memo,
  status,
  transaction_hash,
  paid_at
FROM locked_deals
ORDER BY created_at DESC
LIMIT 5;
"
```

## Step 7: Monitor with Jaeger

```bash
# Open Jaeger UI
open http://localhost:16686

# Search for:
# - Service: aura-core
# - Operation: CheckDealStatus
# - Look for traces showing payment verification
```

## Troubleshooting

### Error: "SOLANA_PRIVATE_KEY required when CRYPTO_ENABLED=true"
- Make sure you exported the private key correctly
- Check `.env` file has `SOLANA_PRIVATE_KEY=<base58-key>`

### Error: "Payment verification failed"
- Check RPC URL is correct: `https://api.devnet.solana.com`
- Verify wallet has sufficient balance for transaction fees
- Ensure memo matches exactly (case-sensitive)

### Error: "Deal not found"
- Verify deal_id is correct UUID
- Check deal hasn't expired (default: 1 hour)
- Confirm crypto is enabled: `CRYPTO_ENABLED=true`

### Payment stuck on PENDING
- Wait 30-60 seconds for Solana finality
- Check transaction on Solana Explorer: `https://explorer.solana.com/?cluster=devnet`
- Verify memo was included in transaction
- Check amount matches (floating-point tolerance: ±0.01%)

### No payment instructions returned
- Verify `CRYPTO_ENABLED=true` in environment
- Check core-service logs: `docker-compose logs core-service | grep crypto_enabled`
- Restart services: `docker-compose restart core-service`

## Testing Different Scenarios

### Test 1: Successful Payment
```bash
# Bid above floor price → Accepted → Pay → Get secret
curl -X POST http://localhost:8000/v1/negotiate -d '{"item_id":"room-101","bid_amount":160,"currency":"USD","agent_did":"test1"}'
# Send payment with memo
# Check status → PAID
```

### Test 2: Deal Expiration
```bash
# Set short TTL
export DEAL_TTL_SECONDS=60  # 1 minute
docker-compose restart core-service

# Negotiate → Wait 61 seconds → Check status → EXPIRED
```

### Test 3: Invalid Deal ID
```bash
curl -X POST http://localhost:8000/v1/deals/invalid-uuid/status
# Expected: 400 Bad Request
```

### Test 4: Crypto Disabled
```bash
export CRYPTO_ENABLED=false
docker-compose restart core-service

curl -X POST http://localhost:8000/v1/negotiate -d '{"item_id":"room-101","bid_amount":160,"currency":"USD","agent_did":"test1"}'
# Expected: reservation_code in response (no payment required)
```

## Next Steps

1. ✅ **You are here** - Local testing on devnet
2. 🔜 Write unit tests (`core-service/tests/test_market_service.py`)
3. 🔜 Write integration tests (`core-service/tests/test_crypto_integration.py`)
4. 🔜 Deploy to staging with testnet
5. 🔜 Deploy to production with mainnet

## Production Checklist

Before enabling on mainnet:
- [ ] Use dedicated RPC provider (Helius, QuickNode, Alchemy)
- [ ] Generate production keypair (secure storage)
- [ ] Set `SOLANA_NETWORK=mainnet-beta`
- [ ] Set `SOLANA_RPC_URL=https://api.mainnet-beta.solana.com`
- [ ] Add rate limiting on CheckDealStatus endpoint
- [ ] Implement monitoring alerts (payment verification failures)
- [ ] Set up backup RPC endpoints (failover)
- [ ] Test with small amounts first

## Support

- Documentation: `CRYPTO_INTEGRATION_SUMMARY.md`
- Code examples: `core-service/src/crypto/`, `core-service/src/services/`
- Logs: `docker-compose logs -f core-service | grep -E "deal_created|payment_verified"`
- Traces: http://localhost:16686

---

**Ready to test!** 🚀

Start with Step 1 (database migration) and work through each step sequentially.
