# Attestation protein — design

**Status:** approved, not implemented
**Date:** 2026-08-12
**Follows:** `2026-08-11-decision-receipt-v2-design.md`

## Why

Nothing in production signs a decision receipt, and nothing has since the receipt existed.

`cortex.py` registers the `transaction` protein only under `if self.settings.crypto.enabled`. That
flag is `false` in `deploy/aura/values.yaml:87`, `false` by default in `CryptoSettings`, and `false`
in `compose.yml`. With no `transaction` protein registered, `Membrane._attest` cannot reach a signer
and every receipt is emitted as `AURA-RECEIPT-V2-UNSIGNED`.

The flag gating attestation is a flag about **crypto payment locks**. A deployment that wants its
decisions attested and does not want to move money on Solana has no way to say so — and if it sets
`enabled=true` to get signing, `CryptoSettings.validate_crypto_config` demands a Solana private key
and a Fernet encryption key it has no use for.

The coupling is worse than a misnamed flag. Even with `enabled=true`, receipts would still not be
signed: `AURA_CRYPTO__EVM_PRIVATE_KEY` is not plumbed into `deploy/aura/templates/core-deployment.yaml`
at all, so `EVMProvider` would be constructed with an empty key and `_sign_receipt` would return
`evm_provider_not_configured`. Signing has never been reachable in the deployed configuration.

`docs/DECISION_RECEIPT.md` §7 already states the intended meaning — "`AURA-RECEIPT-V2-UNSIGNED` means
the deployment had no key configured" — which today is false. It means the deployment did not enable
crypto payments.

## What this is not

There is **no consumer of the signature yet**. No counterparty presents a receipt, no arbiter checks
one, no compliance process consumes them. This design deliberately does not build key publication,
key rotation infrastructure, a signer registry service, or a dispute flow.

The value being bought is retrospective: receipts minted from now on are attestable when a consumer
appears. Everything here is sized to that and no larger.

## The key insight that sizes the work

**Verifying a past signature does not need the private key.** EIP-712 verification recovers the
signer *address* from the receipt. So losing or rotating a signing key does not make older receipts
unverifiable — it only stops new ones being signed.

Two consequences:

1. Key durability is not what needs protecting. Per-environment keys and rotation are fine.
2. What can be lost is the knowledge that a recovered address **was ours**. A receipt is
   self-describing about *which* key signed it and cannot say whose key that was. That fact is the
   only durable artefact this design produces, and it is a text file.

A second insight sizes the code: `EVMProvider.sign_receipt` (`transaction/engine.py:203`) uses only
`self.account` — `Account.from_key()` and `encode_typed_data()`. It needs no RPC, no `AsyncWeb3`, no
USDC address, no network. `EVMProvider.__init__` builds all of that and signing uses none of it.

## Decisions

**A separate `attestation` protein, not a flag change.** Considered and rejected: (a) registering
`TransactionSkill` on key-presence rather than `crypto.enabled` — smallest diff, but yields a
half-bound `TransactionSkill` holding an EVM provider and no payment providers, a new implicit state
inside the protein `docs/CLAUDE.md` already names a god-protein that has "accreted many
responsibilities"; (b) a new settings section with signing left in `TransactionSkill` — fixes the
config confusion but leaves the Membrane calling the *payments* protein to attest a decision, so
configuration and ontology disagree.

Extraction is aligned with the repository's stated direction ("one enzyme, one reaction") and removes
a responsibility from the god-protein rather than adding a mode to it. It costs no more work than the
alternatives: the secret, the settings and the tests are needed either way, and only the file
boundary differs.

**Its own key, not the spending key.** `EVMProvider.sign_receipt`'s docstring argues that domain
separation makes reusing the agent's spending key acceptable, and that argument is sound — a receipt
signature is not a valid trade authorisation because the domain differs. But reuse defeats the goal:
a deployment would still need crypto credentials to attest. Domain separation remains as
defence-in-depth for anyone who does configure the same key material in both places.

**No `enabled` flag.** The protein is registered when a key is present and not otherwise. A flag that
can be set true without a key is another "enabled but not working" state, which is the class of
defect this design exists to remove.

## Architecture

```
Membrane._attest
  └─ registry.execute("attestation", "sign_receipt", {payload})   ← was "transaction"
       └─ AttestationSkill._sign_receipt
            └─ AttestationEngine.sign(payload) → {signer, signature}
                 └─ eth_account: Account.from_key, encode_typed_data
```

`Membrane` builds the payload via `signing_payload(receipt, chain_id=...)` exactly as today. The
protein must not second-guess the document it is handed: one side building a document the other signs
blind is how the two drift into signing different things.

### Components

**`AttestationSkill`** (`core/src/aura_hive/hive/proteins/attestation/skill.py`)
Trinity pattern — `bind(settings, provider)` → `initialize()` → `execute()`. One capability,
`sign_receipt`, taking `{"payload": dict}` and returning `Observation(success, metadata={signer,
signature})`. Owns no payload construction and no network access.

**`AttestationEngine`** (`core/src/aura_hive/hive/proteins/attestation/engine.py`)
Holds the `eth_account` `Account`. One method: `sign(payload) -> {"signer", "signature"}`. Depends on
`eth_account` only — explicitly not on `web3`.

**`AttestationSettings`** (`core/src/aura_hive/config/attestation.py`)

| field | type | default | note |
|---|---|---|---|
| `private_key` | `SecretStr` | `""` | Absent means no protein is registered |
| `chain_id` | `int` | `84532` | For the EIP-712 domain only; nothing is submitted on-chain |

No `model_validator`: there is nothing to require conditionally. The key is present or the protein
does not exist.

**Removals.** `TransactionSkill._sign_receipt`, its `"sign_receipt"` capability entry, and
`EVMProvider.sign_receipt` are deleted. `sign_receipt` has exactly one caller in the repository —
`Membrane._attest` — and it moves. Leaving them would keep two signing paths that drift.

### Wiring

`cortex.py` builds and registers `attestation` alongside the other proteins, outside the
`if self.settings.crypto.enabled` block. The crypto branch is untouched and keeps owning payments.

`Membrane._attest` changes the protein name it calls and reads `chain_id` from
`settings.attestation` rather than `settings.crypto`. The rest of the method — the lookup-not-access
comment, the try/except, the three unsigned-fallback branches — is correct and stays.

### Deployment

`AURA_ATTESTATION__PRIVATE_KEY` is plumbed into `core-deployment.yaml` from the release secret under
a new key, `attestation-private-key`.

**Generating and placing the key is an operator action, outside the implementation plan.** The code
lands first and is inert without it: the deployment logs `attestation_disabled_no_key` and behaves
exactly as it does today. Signing begins when a human puts a key in the secret and records its
address in the provenance file. The plan creates that file with its header row and no entries.

## Observability

This is what makes signing-before-a-consumer worth doing rather than theatre.

**At startup, exactly once:**
- key present → `attestation_signer_ready address=0x…`. Without this, "which key is that deployment
  signing with" is unanswerable without access to the secret itself.
- key absent → `attestation_disabled_no_key`. Today the only evidence that production is not signing
  is a `membrane_receipt_unsigned` warning on every receipt — a symptom, not a statement. The
  difference between "we chose not to attest" and "we believed we were attesting" must be visible at
  boot.

**Per receipt:** unchanged. `membrane_receipt_unsigned` already logs at warning on every unsigned
receipt.

**The provenance record** (`docs/attestation-signers.md`) — a table maintained by hand:

| address | environment | active from | status |
|---|---|---|---|

`status` is one of `active`, `retired`, `compromised`, with the date. A leaked private key means
forged receipts recover to an address recorded as ours, so retirement dates are part of the record,
not an afterthought.

This file is the only long-lived artefact in the design. It survives key rotation, key loss, and
staff turnover, which is precisely what the receipts themselves cannot do.

## Error handling

**Fail-open, unchanged.** A signing failure must not lose the decision it describes. The decision has
already been made and is already safe; trading the guarantee for the attestation is the wrong trade,
and `_sign_receipt`'s docstring says so today.

Every failure path returns the receipt unsigned and logs `membrane_receipt_unsigned`:
missing registry, protein absent, signing raises, or the signer reports neither field. `verify()` does
not treat an unsigned receipt as a failure — it reports `signature` as unverifiable, which is the
honest answer.

## Testing

- **A signature recovers to the expected address.** Recover via `eth_account` rather than asserting
  the string is non-empty; the property under test is that the signature is *the signer's*.
- **The domain in the signature block matches the domain that was signed.** The verification recipe
  in `DECISION_RECEIPT.md` §7 rebuilds the domain from the receipt itself; this is what makes that
  work.
- **A changed `chain_id` does not break verification of a previously signed receipt.** Already
  implied by the block recording its own domain, but asserted explicitly because the whole
  rotatable-key premise rests on it.
- **No key configured:** the protein is not registered, the receipt is `V2-UNSIGNED`, the decision is
  still emitted, and `verify().ok` is true.
- **The engine raising** leaves the decision unchanged and the receipt unsigned.
- **Startup logging:** both branches emit their line.

## Risks

**A leaked private key forges receipts retroactively** against an address the provenance record calls
ours. Mitigated only by recording retirement, which is why the record has a status column rather than
just a date.

**Signing something that is never verified.** If no consumer ever materialises, this work bought
nothing but the startup log. Accepted deliberately: the cost is small and the alternative is a corpus
that can never be attested, which cannot be fixed later.

**`chain_id` is meaningless-looking.** It is required by EIP-712 and nothing is submitted on-chain. A
reader will ask; the settings comment must answer, or someone will "clean it up".

## Out of scope

Key publication, rotation automation, a signer registry service, the `dispute_token` resolver, and
the §3.4 residual (`proposed_price` in the response, the jitter bound decaying with N). Each is its
own piece of work.
