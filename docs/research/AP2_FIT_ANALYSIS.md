# AP2 Fit Analysis: Google Agents-to-Payments vs. Aura

Status: **research note — no code changed.** Written 2026-08-19 as an independent,
code-grounded assessment of whether Google's Agents-to-Payments (AP2) protocol
matches Aura's architecture. Where a claim about Aura appears, it cites the file
and line it was verified against at the time of writing; where a claim about AP2
appears, it refers to AP2 v0.2 (2026-04-28, now standardised under the FIDO
Alliance together with Mastercard's Verifiable Intent).

The companion chat-level summary that motivated this document is deliberately
not reproduced here. This file stands on its own and is written for a reader who
knows Aura but not AP2.

## TL;DR

**AP2 is a buyer-side authorization protocol (User → Agent → Merchant). Aura is
a seller-side realization of the same architectural philosophy (LLM → Membrane →
deterministic guard → signed receipt). They are not competitors — they are two
mirror half-layers of the same stack.** AP2 answers "does this agent have
cryptographically provable authority to make this purchase for this user?"; Aura
answers "is this seller's LLM proposal safe, and what rules judged it?" Both
share the load-bearing invariant: *trust the cryptographic chain, never the
LLM.*

The point where the two become directly relevant to each other is the "Thought
Trading" pivot already recorded in `HIVE_STATE.md`: the Hive selling API
credits / code artifacts to autonomous agents for SOL. That is precisely an
AP2 *Human-Not-Present* purchase — and today Aura has none of the machinery a
merchant needs to verify an agent's right to spend (no user, no mandates, no
budgets, no checkout object).

## 1. What AP2 is, in ten lines

- AP2 is a **security feature inside a Commerce Protocol** (UCP), not a payment
  rail and not a payment API. Catalog, checkout and role communication live
  outside it.
- Core primitive: the **Mandate** — a signed statement of what an agent is
  authorized to do. Two types in v0.2: **Checkout Mandate** (what is being
  bought) and **Payment Mandate** (with what / how it is paid).
- Mandates exist **open** (constraints on a class of future transactions) and
  **closed** (one concrete transaction). Every verifier ultimately sees closed
  mandates; open mandates prove the closed one fits inside the user's
  delegation.
- Five roles: **Shopping Agent** (agentic), **Trusted Surface** (must be
  non-agentic — the deterministic place where the user signs), **Merchant**,
  **Credential Provider**, **Merchant Payment Processor**.
- In autonomous mode the user signs an open mandate binding **`cnf` (confirmation
  claim) to the agent's public key**; the agent later signs the closed mandate
  with its own key. Verifier checks: closed signer == key the open mandate
  delegated to.
- **Cryptographic binding** between layers: the closed Checkout Mandate carries
  `checkout_hash = hash(merchant-signed Checkout JWT)`, and the Payment Mandate
  carries the same hash. You cannot authorize a €100 checkout and pay a €1000
  one. AP2 even requires a *non-deterministic* signature scheme (ECDSA ok,
  Ed25519 not) so a low-entropy checkout hash can't be precomputed offline
  (rainbow-table defence).
- Mandates carry typed **constraints** (`checkout.allowed_merchants`,
  `checkout.line_items` evaluated as a max-flow matching, `payment.amount_range`,
  `payment.budget`, `payment.agent_recurrence`, …). Constraint evaluation is a
  **deterministic policy engine**, not an LLM judgement.
- Some constraints are **stateful** (budget accumulation, occurrence counts), so
  a verifier is a cryptographic verifier + policy engine + transaction-state
  store, not a stateless JWT check.
- **Receipts** are first-class evidence: a mandate + the receipt of what a
  verifier did with it (ACCEPT/REJECT) forms an audit trail for disputes.
- AP2 explicitly does **not** solve semantic intent alignment, prompt injection,
  or liability allocation. The Trusted Surface being non-agentic is the answer
  to the first and part of the second; the rest is out of scope.

## 2. Role mapping: AP2 roles → Aura

| AP2 role | Aura today | Evidence |
|---|---|---|
| User (principal, owner of money) | **Absent.** Agents are self-sovereign, ephemeral `did:key:` keys with no human binding; the frontend re-mints a key on every page load | `tools/simulators/agent_identity.py:53-56`, `frontend/src/hive/connector/wallet.ts:21` |
| Shopping Agent (buyer, agentic) | The external buyer agents. Identity = Ed25519 `did:key:` + signed headers, verified at the gateway | `api-gateway/src/api_gateway/security.py:51` |
| Trusted Surface (non-agentic consent UI) | **Stub.** JIT UI (`high_value_confirm`) renders a confirm modal but its approval is local React state only and never returns a signed authorization; the core collapses `EVALUATE` into `rejected(UI_REQUIRED)` | `frontend/src/hive/transformer/engine.tsx:132`, `frontend/src/components/AgentConsole.tsx:137-139,157-177`, `core/src/aura_hive/hive/connector/main.py:195-199` |
| Merchant | **The Hive itself** — it is the seller/negotiation counterparty. It signs nothing today (no checkout object) | `core/src/aura_hive/hive/proteins/transaction/solana_engine.py:107` (payment into the Hive) |
| Credential Provider | **Absent.** Buyers pay directly (SOL/USDC + memo); no credential issuance or per-use authorization | `solana_engine.py:215` (`generate_payment_request`) |
| Merchant Payment Processor | Solana / EVM rails behind the Hive treasury (`EVMProvider`, `SolanaProvider`) | `engine.py:70`, `solana_engine.py:28` |

The clean way to read the table: **Aura implements the Merchant-side trust
boundary of AP2, not the Shopping-Agent-side one.** The Hive's Membrane +
DecisionReceipt is what AP2 would call the Trusted-Surface boundary — but on the
seller's side of the transaction, judging the seller's own LLM.

## 3. What already matches (8/10 on the philosophy)

| AP2 idea | Aura counterpart | Evidence |
|---|---|---|
| "Don't trust the LLM, trust the cryptographic chain" | The Membrane is a deterministic barrier between the Transformer (LLM) and the Connector (action) | `docs/ARCHITECTURE.md` (ATCG-M), `docs/DECISION_RECEIPT.md` §1 |
| Trusted Surface must be non-agentic | All outbound guards + ψ postcondition are deterministic Python, never LLM | `core/src/aura_hive/hive/proteins/guard/ruleset.yaml` |
| Verification/processing logic must be deterministic code | The guard engine and the receipt verifier are pure, deterministic, keyless | `guard/engine.py`, `membrane/receipt.py:377` (`verify()`) |
| Verifiable, self-describing evidence | `DecisionReceipt` AURA-RECEIPT-V2: EIP-712, self-describing domain, verifier needs no key material | `proto/aura/core/v1/metabolism.proto:256`, `receipt.py:335` |
| Domain separation (a receipt is not an authorization) | `AuraDecisionReceipt` domain deliberately differs from `HackathonRiskRouter` (TradeIntent) | `membrane/receipt.py:66-69` |
| Versioned, discriminable schemas (`vct`) | Versioned, content-hashed rule set: `guard/negotiation@2.0.0+<hex>`; cross-checked both ways | `ruleset.yaml`, `DECISION_RECEIPT.md` §3.3 |
| Constraint evaluation as a separate primitive | G1–G4 gates + ψ postcondition, fail-closed, declared-then-cross-checked | `ruleset.yaml:58-75` |
| Honest boundary: "proves authorization, not intent" | Aura documents the same limit: `claim_hash` covers decidable content, prose is stripped; a receipt cannot prove the decision "ever happened" to a stranger | `DECISION_RECEIPT.md` §3.2, §7 |

Aura is *ahead* of AP2 in one respect: it ships a **postcondition (ψ)** checked
on the emission after the verdict — a guarantee about what got out, not just
about what was checked in. AP2 v0.2 has gates-by-constraint but no equivalent
postcondition-on-emission.

## 4. The critical gaps

### 4.1 No user, no delegation — the structural gap

Everything AP2 is about — user delegation, open mandates, agent key ≠ user key,
budgets, spend limits, consent — is **absent** from Aura's protocol. A grep for
`mandate / authorization / delegation / consent / budget` across the payment
layer returns nothing. The only "authorization" today is *authentication*: the
Ed25519 request signature proves who the agent is, not what it may spend.

The three closest constructs are all narrow:

- `max_x402_payment = 5.0` USDC cap on data purchases (`config/policy.py:13`) —
  a fixed platform constant, not per-agent delegation;
- `ui_trigger_price = 1000.0` (`config/policy.py:12`) — routes high-value bids
  to the (non-functional) JIT UI;
- `AutonomousBuyer(budget_limit)` — a client-side simulator variable
  (`tools/simulators/autonomous_buyer.py:33`), not protocol.

### 4.2 Payment binding is memo-match, not a hash chain

AP2 binds the payment to the checkout cryptographically (payment mandate
carries the checkout hash; ECDSA-only for the binding signature). Aura binds a
payment to a deal by an 8-char **memo string** matched on-chain within an amount
tolerance (`solana_engine.py:158`). There is no checkout object, no signed
checkout JWT, no hash linking mandate → checkout → payment.

### 4.3 Receipts are auditor-only, not counterparty evidence

A deliberate, documented decision (`DECISION_RECEIPT.md` §1.1): the receipt is
addressed to an auditor, never to the counterparty. The counterparty (the buyer
agent) receives only a random `dispute_token`. AP2's receipts exist precisely so
a counterparty (merchant / credential provider) can verify a buyer's mandate.
These are opposite audiences. Making Aura's receipts AP2-counterparty-verifiable
is a real design change, not a flag flip — it would need freshness by nonce,
published signer identity, and a transparency log (all explicitly deferred in
`DECISION_RECEIPT.md` §1.1).

### 4.4 Replay protection is timestamp-only

The gateway accepts ±60 s (`security.py:22`, `:107`); receipts use `issued_at`
freshness, not a nonce (`metabolism.proto:298-302`). AP2 requires explicit
single-use/consume-once semantics plus runtime nonces for closed mandates. The
per-receipt random nonce is already recorded as future work
(`DECISION_RECEIPT.md:1227-1231`).

### 4.5 Ed25519 vs. the binding-signature rule

AP2 forbids Ed25519 for the checkout-binding signature (deterministic → rainbow
table precomputation on low-entropy payloads). Aura signs every agent request
with Ed25519 (`agent_identity.py:70-106`). That is fine while Aura is only the
seller (agent signatures authenticate; they don't bind a payment to a checkout),
but it becomes a direct conflict the day Aura verifies agent payment mandates.

### 4.6 Edge drift: the MCP adapter is unauthenticated

The MCP server embeds a full `HiveCell` in-process and hardcodes the identity
`"mcp-agent"` (`synapses/mcp-server/src/aura_mcp/translator.py:39`,
`main.py:40-47`). Its README describes a signed-gateway design the code does not
implement. Rate limiting and sessions are described in `docs/SECURITY.md` but
not implemented. AP2's whole premise is that the agent channel is untrusted; an
unauthenticated adapter contradicts that premise where it exists.

## 5. Opportunity map: Aura as an AP2 Merchant

`HIVE_STATE.md` records the pivot: "Shift from Travel to Compute: Thought-Trading
protocol; asset definition API Credits & Code Artifacts; unit of account SOL /
Stars." When the Hive sells compute to autonomous agents, it *becomes* an AP2
Merchant in a Human-Not-Present flow, and each of these becomes concrete work:

1. **Checkout object with hash binding.** Today a deal is a `LockedDeal`
   (`persistence/engine.py:59`) + memo. A signed, hash-bound checkout is the
   missing primitive that lets the Hive prove "this payment corresponds to this
   deal" cryptographically rather than by memo.
2. **Open Payment Mandates.** "This agent may spend up to X SOL/month" is the
   direct answer to Aura's complete lack of budgets/spend limits — and it is the
   *buyer's* problem to solve, which means Aura needs a buyer-side credential
   issuer or needs to verify mandates issued by others.
3. **Trusted Surface.** The JIT UI scaffolding (`high_value_confirm`) is the
   seed of one; AP2 dictates the shape: non-agentic, deterministic, user-signed,
   cryptographically bound to the mandate content, and *wired back* (today the
   approval is discarded).
4. **Constraint evaluation is already Aura-shaped.** The guard engine (gates +
   ψ + versioned ruleset) is architecturally the same thing as AP2 constraint
   evaluation. Adding `payment.amount_range` / `payment.budget` /
   `payment.agent_recurrence` constraints is native rather than novel.
5. **x402 already exists.** HTTP 402 + `X-Payment-Instructions` with a 5 USDC
   cap (`blockchain_data/skill.py:104-138`) — and x402 is one of AP2's supported
   payment methods. This is the one concrete protocol touchpoint that is live
   today.

## 6. What AP2 will never give Aura

AP2 is buyer-side authorization. It does not solve Aura's core problems:

- **Hidden Knowledge** (floor price never reaching agents) and the accept/reject
  oracle it implies — see `DECISION_RECEIPT.md` §3.4;
- **Negotiation strategy** (DSPy-trained pricing brains);
- **Semantic alignment of bids** — AP2's own limit, which Aura has independently
  reached: a receipt proves a signature, not intent (`DECISION_RECEIPT.md` §3.2);
- **Prompt injection** — AP2 bounds the damage (constraint mismatch → reject) but
  cannot stop a poisoned agent from choosing a worse-but-legal option.

The correct security model for Aura stays the one already implied by the
architecture: deterministic guard + cryptographic attestation + runtime policy,
with AP2 as the buyer-side complement, not a replacement.

## 7. Fit scorecard

| Area | Match | Note |
|---|---|---|
| Don't-trust-the-LLM philosophy | 9/10 | Membrane + ψ + receipt is a reference implementation |
| Deterministic policy engine | 8/10 | gates + postcondition + versioned ruleset |
| Cryptographically signed evidence | 8/10 | EIP-712, self-describing; but auditor-only |
| Payment ↔ checkout binding | 2/10 | memo-match, no hash chain |
| User delegation / mandates | 0/10 | entirely absent |
| Trusted Surface | 1/10 | JIT UI stub, approval not propagated |
| Replay / nonce | 3/10 | timestamp-only |
| Ecosystem (x402, A2A, UCP, FIDO) | 4/10 | x402 live; MCP unauthenticated; no UCP/FIDO |

## 8. Sources / evidence index

| Claim | File:line |
|---|---|
| Agent DID = `did:key:` + Ed25519 pubkey hex | `tools/simulators/agent_identity.py:53-56` |
| Request signing scheme | `tools/simulators/agent_identity.py:70-106` |
| Gateway signature verification | `api-gateway/src/api_gateway/security.py:51` |
| ±60 s timestamp tolerance | `api-gateway/src/api_gateway/security.py:22,107` |
| Public-Membrane dual path (unused by frontend) | `api-gateway/src/api_gateway/security.py:180` |
| Frontend key re-minted per page load | `frontend/src/hive/connector/wallet.ts:21` |
| JIT UI render + stub approval | `frontend/src/hive/transformer/engine.tsx:132`, `frontend/src/components/AgentConsole.tsx:137-139,157-177` |
| `EVALUATE` collapsed to `rejected(UI_REQUIRED)` | `core/src/aura_hive/hive/connector/main.py:195-199` |
| MCP hardcoded `"mcp-agent"` identity | `synapses/mcp-server/src/aura_mcp/translator.py:39` |
| MCP embeds HiveCell in-process | `synapses/mcp-server/src/aura_mcp/main.py:40-47` |
| Payments into the Hive by memo match | `core/src/aura_hive/hive/proteins/transaction/solana_engine.py:107,158` |
| Payment request URI builder | `solana_engine.py:215` |
| EIP-712 TradeIntent signing | `core/src/aura_hive/hive/proteins/transaction/engine.py:134` |
| Compliance gate (KYC/AML) for treasury transfers | `core/src/aura_hive/hive/proteins/transaction/compliance.py:18` |
| Attestation key (pure, EIP-712, KeyProbe) | `core/src/aura_hive/hive/proteins/attestation/engine.py:20-28,30-60` |
| Receipt two formats + domain separation | `core/src/aura_hive/hive/membrane/receipt.py:58-69` |
| Receipt signed content fields | `receipt.py:197-222` |
| Receipt `verify()` keyless | `receipt.py:377` |
| Attestation asked from `attestation`, not `transaction` | `core/src/aura_hive/hive/membrane/main.py:447-450` |
| Outbound membrane boundary | `membrane/main.py:631` |
| Guard gates + ψ postcondition | `core/src/aura_hive/hive/proteins/guard/ruleset.yaml:58-75` |
| `DecisionReceipt` proto | `proto/aura/core/v1/metabolism.proto:256` |
| `Intent` proto | `metabolism.proto:360` |
| High-value UI trigger / x402 cap | `core/src/aura_hive/config/policy.py:12-13` |
| x402 path (HTTP 402 + instructions) | `core/src/aura_hive/hive/proteins/blockchain_data/skill.py:104-138` |
| `LockedDeal` / `SanctifiedWallet` persistence | `core/src/aura_hive/hive/proteins/persistence/engine.py:59,92` |
| Thought-Trading pivot | `HIVE_STATE.md` ("Economy (The Pivot)") |
| Receipt audience decision (auditor-only) | `docs/DECISION_RECEIPT.md` §1.1 |
| Receipt boundary honesty ("cannot be checked independently") | `docs/DECISION_RECEIPT.md` §7 |
| Per-receipt nonce deferred | `docs/DECISION_RECEIPT.md` §3.1 |
