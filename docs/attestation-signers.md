# Attestation signers

Which address signed which receipts, and when it was ours.

A receipt is self-describing about *which* key signed it — the signature
recovers to an address — but it cannot say that the address was ours. This file
is that missing half, and it is the only long-lived artefact in the attestation
design: verifying a past signature never needs the private key, so keys may
rotate and be lost freely, while this record must not.

Add a row when a key is put into service. Set a retirement date when it leaves,
and mark it `compromised` — not `retired` — if that is why. A leaked key can
forge receipts that recover to an address recorded here as ours, so the status
column is the part that matters.

The address a running deployment signs with is on its startup log line,
`attestation_signer_ready address=0x…`. A deployment with no key logs
`attestation_disabled_no_key` instead and emits `AURA-RECEIPT-V2-UNSIGNED`,
which is a legitimate configuration rather than a fault.

| address | environment | active from | status |
|---------|-------------|-------------|--------|
| _(none yet — no key has been placed)_ | | | |
