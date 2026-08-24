# 2026-08-12 Receipt Durability Design

## Overview
This specification outlines the design for ensuring receipt durability in the Aura Hive. Receipts are critical for dispute resolution and auditability, so they must be tamper-proof and persistently stored.

## Requirements
1. **Tamper-Proofing**: Receipts must be cryptographically signed to ensure integrity.
2. **Persistence**: Receipts must be stored in a durable medium (e.g., database, blockchain).
3. **Accessibility**: Receipts must be retrievable for dispute resolution and audits.
4. **Attestation Key**: An attestation key must be placed in the Hive to sign receipts. Without this key, receipts will accumulate unsigned, leading to potential disputes or audit failures.

## Design
### Receipt Signing
- Receipts are signed using an attestation key managed by the Hive.
- The attestation key is rotated periodically for security.
- Signatures are stored alongside receipts in the database.

### Receipt Storage
- Receipts are stored in the `receipts` table in the database.
- The table includes columns for `receipt_id`, `deal_id`, `signature`, `timestamp`, and `payload`.
- Receipts are also emitted to the NATS JetStream for real-time processing.

### Attestation Key Management
- The attestation key is stored in a secure vault or environment variable.
- Key rotation is automated and logged for auditability.
- If the attestation key is missing or invalid, the Hive must fail loudly to prevent unsigned receipts from accumulating.

## Implementation Plan
1. **Key Placement**: Deploy the attestation key to the Hive's secure storage.
2. **Signing Logic**: Integrate signing into the receipt generation process.
3. **Storage Logic**: Ensure receipts are stored in the database and NATS JetStream.
4. **Validation**: Add checks to verify receipt signatures during dispute resolution.

## Acceptance Criteria
- [ ] Attestation key is deployed and accessible to the Hive.
- [ ] Receipts are signed before storage.
- [ ] Unsigned receipts are rejected and logged as errors.
- [ ] Receipts are retrievable for dispute resolution and audits.
- [ ] Key rotation is tested and documented.