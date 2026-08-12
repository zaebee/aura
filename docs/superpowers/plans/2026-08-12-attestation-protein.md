# Attestation Protein Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the Hive a protein that signs decision receipts using its own key, so a deployment can attest decisions without enabling crypto payment locks.

**Architecture:** A new `attestation` protein owns one private key and one operation — turning an EIP-712 payload the Membrane built into a signature. It is registered when a key is present and absent otherwise. `Membrane._attest` calls it instead of the `transaction` protein, and the old signing path is deleted so two cannot drift.

**Tech Stack:** Python 3.12, `eth-account` (NOT `web3` — signing needs no network), pydantic-settings, pytest, structlog.

**Spec:** `docs/superpowers/specs/2026-08-12-attestation-protein-design.md`

## Global Constraints

- Package manager is `uv`. Never `pip` or `poetry`.
- Run core tests as: `PYTHONPATH=core/src:core/gen-proto:packages/aura-core/src:packages/aura-core/gen-proto uv run pytest <path> -v`
- Proteins follow the Trinity pattern: `bind(settings, provider)` → `async initialize() -> bool` → `async execute(intent, params) -> Observation`.
- Never edit generated protobuf code (`*/gen-proto/`, `aura_core_gen`).
- Biological naming. `Manager`/`Service`/`Helper`/`Handler` are forbidden.
- `make lint` must exit 0 before every commit (ruff check, ruff format --check, mypy, bandit, buf lint).
- betterproto: test absence by value (`if not msg.field:`), never by identity (`is None`) — an identity check on a message field never fires.
- Signing failure must never fail the decision. Every error path returns the receipt unsigned.
- The signer address `0x…` may appear in logs. The **private key** must never be logged, and never appear in an error message or a test fixture that is committed with a real value.

---

### Task 1: Attestation settings

**Files:**
- Create: `core/src/aura_hive/config/attestation.py`
- Modify: `core/src/aura_hive/config/__init__.py` (import block at lines 6-16, field list at lines 28-40)
- Test: `core/tests/test_attestation_settings.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `AttestationSettings` with fields `private_key: SecretStr` (default `SecretStr("")`) and `chain_id: int` (default `84532`); reachable as `Settings().attestation`.

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_attestation_settings.py`:

```python
"""
Attestation is configured on its own, not through the payments section.

Signing a decision receipt needs one key. Reaching it through `CryptoSettings`
meant a deployment that wanted attestation had to enable crypto payment locks
and supply a Solana key and a Fernet key it had no use for.
"""

from pydantic import SecretStr

from aura_hive.config import Settings
from aura_hive.config.attestation import AttestationSettings


def test_the_defaults_leave_attestation_off() -> None:
    settings = AttestationSettings()

    assert settings.private_key.get_secret_value() == ""
    assert settings.chain_id == 84532


def test_attestation_hangs_off_the_root_settings() -> None:
    settings = Settings()

    assert isinstance(settings.attestation, AttestationSettings)


def test_a_key_is_carried_as_a_secret() -> None:
    """A SecretStr so the key cannot reach a log line by being interpolated."""
    settings = AttestationSettings(private_key=SecretStr("0xdeadbeef"))

    assert "deadbeef" not in repr(settings)
    assert settings.private_key.get_secret_value() == "0xdeadbeef"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=core/src:core/gen-proto:packages/aura-core/src:packages/aura-core/gen-proto uv run pytest core/tests/test_attestation_settings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'aura_hive.config.attestation'`

- [ ] **Step 3: Write minimal implementation**

Create `core/src/aura_hive/config/attestation.py`:

```python
from pydantic import BaseModel, SecretStr


class AttestationSettings(BaseModel):
    """
    The key that signs decision receipts, and the domain it signs under.

    Separate from `CryptoSettings` deliberately. Attesting a decision and
    moving money are different jobs with different blast radii, and the flag
    that gated signing was a flag about payment locks: a deployment wanting
    attested receipts had to turn on crypto and supply a Solana key and a
    Fernet key it never used.

    There is no `enabled` field. The protein is registered when a key is
    present and not otherwise, so there is no way to configure "on but not
    working" — which is the state this section exists to remove.
    """

    private_key: SecretStr = SecretStr("")

    # Required by EIP-712's domain separator; nothing is submitted on-chain.
    # The signature block on a receipt records the chain id it was signed
    # under, and `verify()` rebuilds the domain from the receipt itself, so
    # changing this does not invalidate receipts already signed.
    chain_id: int = 84532
```

In `core/src/aura_hive/config/__init__.py`, add to the import block (alphabetical, before `from .blockchain_data import ...`):

```python
from .attestation import AttestationSettings
```

and add the field after `blockchain_data`:

```python
    attestation: AttestationSettings = Field(
        default_factory=lambda: AttestationSettings()
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=core/src:core/gen-proto:packages/aura-core/src:packages/aura-core/gen-proto uv run pytest core/tests/test_attestation_settings.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Lint and commit**

```bash
make lint
git add core/src/aura_hive/config/attestation.py core/src/aura_hive/config/__init__.py core/tests/test_attestation_settings.py
git commit -m "feat(config): give attestation its own section, off the payments flag"
```

---

### Task 2: The attestation protein

**Files:**
- Create: `core/src/aura_hive/hive/proteins/attestation/__init__.py`
- Create: `core/src/aura_hive/hive/proteins/attestation/engine.py`
- Create: `core/src/aura_hive/hive/proteins/attestation/skill.py`
- Modify: `core/pyproject.toml` (dependency list, around line 41)
- Test: `core/tests/test_attestation_protein.py`

**Interfaces:**
- Consumes: `AttestationSettings` from Task 1.
- Produces:
  - `AttestationEngine(private_key_hex: str)` with `.address -> str` and `.sign(payload: dict[str, Any]) -> dict[str, str]` returning keys `signer` and `signature`.
  - `AttestationSkill()` with `get_name() -> "attestation"`, capability `"sign_receipt"` taking `{"payload": dict}` and returning `Observation(success=True, metadata={"signer": ..., "signature": ...})`.

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_attestation_protein.py`:

```python
"""
The protein that holds the key.

It signs a document it is handed and does not build one. The Membrane owns
what a receipt says; having one side assemble a document the other signs blind
is how the two drift into signing different things.
"""

from typing import Any

import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data

from aura_hive.config.attestation import AttestationSettings
from aura_hive.hive.proteins.attestation.engine import AttestationEngine
from aura_hive.hive.proteins.attestation.skill import AttestationSkill


def a_payload(chain_id: int = 84532) -> dict[str, Any]:
    """The EIP-712 shape `signing_payload()` produces, built by hand here."""
    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
            ],
            "DecisionReceipt": [{"name": "content", "type": "string"}],
        },
        "domain": {
            "name": "AuraDecisionReceipt",
            "version": "2",
            "chainId": chain_id,
        },
        "primaryType": "DecisionReceipt",
        "message": {"content": "some-canonical-content"},
    }


def _recover(payload: dict[str, Any], signature: str) -> str:
    raw = bytes.fromhex(signature.removeprefix("0x"))
    return str(Account.recover_message(encode_typed_data(full_message=payload), signature=raw))


class TestTheEngine:
    def test_the_signature_recovers_to_the_signer_it_reports(self) -> None:
        """
        The property, not the presence. Asserting the string is non-empty
        would pass for a signature by the wrong key.
        """
        account = Account.create()
        engine = AttestationEngine(account.key.hex())
        payload = a_payload()

        result = engine.sign(payload)

        assert _recover(payload, result["signature"]) == account.address
        assert result["signer"] == account.address

    def test_a_different_domain_produces_a_different_signature(self) -> None:
        """
        Domain separation is what stops a receipt signature being reusable as
        anything else signed by the same key.
        """
        engine = AttestationEngine(Account.create().key.hex())

        first = engine.sign(a_payload(chain_id=84532))
        second = engine.sign(a_payload(chain_id=1))

        assert first["signature"] != second["signature"]

    def test_the_address_is_readable_without_signing_anything(self) -> None:
        """The Cortex logs it at startup, before any decision exists."""
        account = Account.create()

        assert AttestationEngine(account.key.hex()).address == account.address


class TestTheSkill:
    @pytest.mark.asyncio
    async def test_it_signs_the_payload_it_is_given(self) -> None:
        account = Account.create()
        skill = AttestationSkill()
        skill.bind(AttestationSettings(), AttestationEngine(account.key.hex()))
        payload = a_payload()

        obs = await skill.execute("sign_receipt", {"payload": payload})

        assert obs.success
        meta = obs.metadata.to_dict()
        assert meta["signer"] == account.address
        assert _recover(payload, meta["signature"]) == account.address

    @pytest.mark.asyncio
    async def test_a_missing_payload_is_reported_not_raised(self) -> None:
        skill = AttestationSkill()
        skill.bind(AttestationSettings(), AttestationEngine(Account.create().key.hex()))

        obs = await skill.execute("sign_receipt", {})

        assert not obs.success
        assert obs.error == "payload_missing"

    @pytest.mark.asyncio
    async def test_an_unknown_intent_is_reported_not_raised(self) -> None:
        skill = AttestationSkill()
        skill.bind(AttestationSettings(), AttestationEngine(Account.create().key.hex()))

        obs = await skill.execute("spend_money", {})

        assert not obs.success

    @pytest.mark.asyncio
    async def test_a_signing_failure_is_reported_not_raised(self) -> None:
        """
        The Membrane emits an unsigned receipt rather than losing the decision,
        so this must come back as a failed Observation, never as an exception.
        """

        class _Broken:
            address = "0x0"

            def sign(self, payload: dict[str, Any]) -> dict[str, str]:
                raise RuntimeError("hsm unreachable")

        skill = AttestationSkill()
        skill.bind(AttestationSettings(), _Broken())

        obs = await skill.execute("sign_receipt", {"payload": a_payload()})

        assert not obs.success
        assert "hsm unreachable" in (obs.error or "")

    def test_the_protein_answers_to_its_name(self) -> None:
        assert AttestationSkill().get_name() == "attestation"
        assert "sign_receipt" in AttestationSkill().get_capabilities()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=core/src:core/gen-proto:packages/aura-core/src:packages/aura-core/gen-proto uv run pytest core/tests/test_attestation_protein.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'aura_hive.hive.proteins.attestation'`

- [ ] **Step 3: Write minimal implementation**

Create `core/src/aura_hive/hive/proteins/attestation/engine.py`:

```python
from typing import Any

from eth_account import Account
from eth_account.messages import encode_typed_data


class AttestationEngine:
    """
    The key, and nothing else.

    Deliberately has no RPC client, no chain connection and no `web3` import.
    Signing an EIP-712 payload needs an account and the encoder; the provider
    this was extracted from built an `AsyncWeb3` connection, checksummed token
    addresses and loaded an ERC20 ABI, none of which signing ever touched.
    """

    def __init__(self, private_key_hex: str) -> None:
        self.account = Account.from_key(private_key_hex)

    @property
    def address(self) -> str:
        """The signer, readable before anything has been signed."""
        return str(self.account.address)

    def sign(self, payload: dict[str, Any]) -> dict[str, str]:
        """
        Sign the payload as handed over.

        The document arrives fully formed. The Membrane owns what a receipt
        says and this owns the key, and the domain in the payload is what makes
        a receipt signature unusable as any other kind of authorisation — so
        this must not second-guess the domain it was given.
        """
        signed_message = encode_typed_data(full_message=payload)
        signature = self.account.sign_message(signed_message)
        return {
            "signer": str(self.account.address),
            "signature": signature.signature.hex(),
        }
```

Create `core/src/aura_hive/hive/proteins/attestation/skill.py`:

```python
from typing import Any

import structlog
from aura_core import SkillProtocol, make_struct
from aura_core_gen.aura.core.v1 import Observation

from aura_hive.config.attestation import AttestationSettings

from .engine import AttestationEngine

logger = structlog.get_logger(__name__)


class AttestationSkill(
    SkillProtocol[AttestationSettings, Any, dict[str, Any], Observation]
):
    """
    Attestation Protein: signs decision receipts.

    One capability, one key. Extracted from the transaction protein, which had
    accreted this alongside payments — so attesting a decision required turning
    on crypto payment locks, and the Membrane called the payments protein to
    vouch for an audit record.
    """

    def __init__(self) -> None:
        self.settings: AttestationSettings | None = None
        self.provider: Any = None
        self._capabilities = {"sign_receipt": self._sign_receipt}

    def get_name(self) -> str:
        return "attestation"

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities.keys())

    def bind(self, settings: AttestationSettings, provider: Any) -> None:
        self.settings = settings
        self.provider = provider

    async def initialize(self) -> bool:
        return True

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        handler = self._capabilities.get(intent)
        if not handler:
            return Observation(success=False, error=f"Unknown intent: {intent}")

        try:
            return await handler(params)
        except Exception as e:
            # Reported, never raised. The decision this receipt describes has
            # already been made and is already safe; losing it because a key
            # was unreachable trades the guarantee for the attestation.
            logger.error("attestation_failed", error=str(e))
            return Observation(success=False, error=str(e))

    async def _sign_receipt(self, params: dict[str, Any]) -> Observation:
        payload = params.get("payload")
        if not payload:
            return Observation(success=False, error="payload_missing")

        if not self.provider:
            return Observation(success=False, error="attestation_key_not_configured")

        result = self.provider.sign(payload)
        return Observation(success=True, metadata=make_struct(result))
```

Create `core/src/aura_hive/hive/proteins/attestation/__init__.py`:

```python
from .engine import AttestationEngine
from .skill import AttestationSkill

__all__ = ["AttestationEngine", "AttestationSkill"]
```

In `core/pyproject.toml`, add to the dependency list beside `"web3>=7.0.0"`:

```toml
    "eth-account>=0.13.7",
```

(It arrives transitively through `web3` today. Declared directly because this protein depends on it directly and deliberately does not depend on `web3`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=core/src:core/gen-proto:packages/aura-core/src:packages/aura-core/gen-proto uv run pytest core/tests/test_attestation_protein.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Lint and commit**

```bash
make lint
git add core/src/aura_hive/hive/proteins/attestation core/tests/test_attestation_protein.py core/pyproject.toml
git commit -m "feat(attestation): a protein that holds one key and signs what it is handed"
```

---

### Task 3: Wire it into the Cortex, and say so at startup

**Files:**
- Modify: `core/src/aura_hive/hive/cortex.py` (import block near line 22; protein construction after the GoldRush block at lines 239-241; registration list at lines 244-254)
- Test: `core/tests/test_attestation_wiring.py`

**Interfaces:**
- Consumes: `AttestationSkill`, `AttestationEngine` (Task 2); `Settings().attestation` (Task 1).
- Produces: the protein registered under `"attestation"` in `HiveCell.registry` when a key is configured, and absent when not.

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_attestation_wiring.py`:

```python
"""
A deployment must be able to tell, at boot, whether it is attesting.

Before this, the only evidence that production was not signing was a
`membrane_receipt_unsigned` warning on every receipt — a symptom, not a
statement. The difference between "we chose not to attest" and "we believed we
were attesting" belongs in the startup log.
"""

import structlog
from eth_account import Account

from aura_hive.hive.proteins.attestation import AttestationEngine, AttestationSkill


def build_attestation(settings_key: str) -> tuple[AttestationSkill | None, list[str]]:
    """
    Calls the Cortex's own decision function and captures what it logged.

    Written against an import that does not exist yet — that is the failing
    test. Step 3 adds `build_attestation` to `cortex.py`, and this wrapper only
    supplies the settings and the log capture.
    """
    from aura_hive.config.attestation import AttestationSettings
    from aura_hive.hive.cortex import build_attestation as _build

    captured: list[str] = []

    def _capture(logger: object, method_name: str, event_dict: dict) -> dict:
        captured.append(str(event_dict.get("event", "")))
        return event_dict

    structlog.configure(processors=[_capture])
    try:
        return _build(settings_key, AttestationSettings()), captured
    finally:
        # Reset, or every test that runs after this one inherits the capture
        # processor and logs nothing.
        structlog.reset_defaults()


class TestTheProteinIsRegisteredOnlyWithAKey:
    def test_a_configured_key_produces_a_bound_protein(self) -> None:
        account = Account.create()

        skill, events = build_attestation(account.key.hex())

        assert skill is not None
        assert skill.get_name() == "attestation"
        assert "attestation_signer_ready" in events

    def test_no_key_produces_no_protein_and_says_so(self) -> None:
        skill, events = build_attestation("")

        assert skill is None
        assert "attestation_disabled_no_key" in events

    def test_the_startup_line_carries_the_address_not_the_key(self) -> None:
        """
        The address is the durable fact — it is what a signature recovers to,
        and what the provenance record ties to an environment. The key must
        never reach a log line.
        """
        account = Account.create()
        engine = AttestationEngine(account.key.hex())

        assert engine.address == account.address
        assert account.key.hex() not in engine.address
```

Replace the `build_attestation` stub with an import once Step 3 lands (see Step 3).

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=core/src:core/gen-proto:packages/aura-core/src:packages/aura-core/gen-proto uv run pytest core/tests/test_attestation_wiring.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_attestation' from 'aura_hive.hive.cortex'`

- [ ] **Step 3: Write minimal implementation**

In `core/src/aura_hive/hive/cortex.py`, add to the protein import block:

```python
from aura_hive.hive.proteins.attestation import AttestationEngine, AttestationSkill
```

Add this module-level function above the `HiveCell` class, so the decision is testable without booting a cell:

```python
def build_attestation(
    private_key_hex: str, settings: AttestationSettings
) -> AttestationSkill | None:
    """
    The attestation protein, or nothing.

    Registered on key presence rather than on a feature flag. A flag that can
    be set true without a key is another "enabled but not working" state, and
    that is exactly what this replaces: signing used to be gated on
    `crypto.enabled`, a flag about payment locks, which was false everywhere
    and would not have signed anything if it were true, because no EVM key was
    ever plumbed into the deployment.

    A module-level function rather than a method, so the decision can be tested
    without booting a cell.
    """
    if not private_key_hex:
        logger.info("attestation_disabled_no_key")
        return None

    engine = AttestationEngine(private_key_hex)
    skill = AttestationSkill()
    skill.bind(settings, engine)
    # The address, never the key. This is the only place a deployment states
    # which signer its receipts will recover to.
    logger.info("attestation_signer_ready", address=engine.address)
    return skill
```

`cortex.py` does not import `get_settings` and must not start: settings are already on `self.settings`
at the call site. Add `from aura_hive.config.attestation import AttestationSettings` to the imports
for the type annotation.

Inside the assembly method, after the GoldRush block (line ~239):

```python
        # 10. Attestation (registered only when a key is present)
        attestation = build_attestation(
            get_raw_key(self.settings.attestation.private_key),
            self.settings.attestation,
        )
```

And in the registration list, beside the existing conditional registration:

```python
        if attestation:
            self.registry.register("attestation", attestation)
```

The test helper written in Step 1 already imports this function; no test changes are needed.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=core/src:core/gen-proto:packages/aura-core/src:packages/aura-core/gen-proto uv run pytest core/tests/test_attestation_wiring.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the whole core suite**

Run: `PYTHONPATH=core/src:core/gen-proto:packages/aura-core/src:packages/aura-core/gen-proto uv run pytest core/tests/ -q`
Expected: all pass. The `structlog.reset_defaults()` in the helper matters here — a leaked configuration changes logging for every test that follows.

- [ ] **Step 6: Lint and commit**

```bash
make lint
git add core/src/aura_hive/hive/cortex.py core/tests/test_attestation_wiring.py
git commit -m "feat(cortex): register attestation on key presence, and say at boot which signer is live"
```

---

### Task 4: Point the Membrane at it, and delete the old path

**Files:**
- Modify: `core/src/aura_hive/hive/membrane/main.py:434-470` (`_attest`)
- Modify: `core/src/aura_hive/hive/proteins/transaction/skill.py` (remove `"sign_receipt"` from `_capabilities` near line 51 and the `_sign_receipt` method at lines 218-239)
- Modify: `core/src/aura_hive/hive/proteins/transaction/engine.py` (remove `sign_receipt` at lines 203-223)
- Modify: `core/tests/test_transaction_skill.py` (drop any `sign_receipt` cases)
- Test: `core/tests/test_attestation_membrane.py`

**Interfaces:**
- Consumes: the `"attestation"` protein registered in Task 3; `signing_payload(receipt, chain_id)` and `signed(receipt, signer, signature, chain_id)` from `aura_hive.hive.membrane.receipt` (unchanged).
- Produces: `Membrane._attest` calling `"attestation"` and reading `chain_id` from `settings.attestation`.

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_attestation_membrane.py`:

```python
"""
The Membrane asks the attestation protein, not the payments protein.

Nothing in production was signed, because signing lived behind
`crypto.enabled`. This asserts the new address of the key AND the promise that
survives it: a signing failure never costs the decision.
"""

from typing import Any

import pytest
from aura_core import SkillRegistry
from aura_core.struct_utils import make_struct
from aura_core_gen.aura.core.v1 import (
    ActionType,
    Context,
    HiveContextData,
    Intent,
    NegotiationIntent,
)
from eth_account import Account
from eth_account.messages import encode_typed_data

from aura_hive.config.attestation import AttestationSettings
from aura_hive.config.policy import SafetySettings
from aura_hive.hive.membrane.main import HiveMembrane
from aura_hive.hive.membrane.receipt import signing_payload
from aura_hive.hive.proteins.attestation import AttestationEngine, AttestationSkill
from aura_hive.hive.proteins.guard import GuardSkill
from aura_hive.hive.proteins.guard.engine import OutputGuard


class _Safety:
    min_profit_margin = 0.10
    ui_trigger_price = 100000.0
    trade_risk_threshold = 0.10


class _Settings:
    """
    What the Membrane reads off `self.settings`.

    `safety` is carried even though these tests never reach it: `inspect_outbound`
    reads `self.settings.safety.trade_risk_threshold` on the trade path, and a
    stub missing it fails only for whoever adds the first trade test here.
    """

    def __init__(self, chain_id: int = 84532) -> None:
        self.attestation = AttestationSettings(chain_id=chain_id)
        self.safety = SafetySettings()


def membrane_with(attestation: Any | None) -> HiveMembrane:
    registry = SkillRegistry()
    guard = GuardSkill()
    guard.bind(_Safety(), OutputGuard(safety_settings=_Safety()))
    registry.register(guard.get_name(), guard)
    if attestation is not None:
        registry.register("attestation", attestation)
    membrane = HiveMembrane(registry=registry)
    membrane.settings = _Settings()
    return membrane


def context() -> Context:
    return Context(
        metadata=make_struct({"floor_price": "1000.0", "internal_cost": "777.0"}),
        hive=HiveContextData(request_id="req-attest"),
    )


def counter(price: float) -> Intent:
    return Intent(
        action=ActionType.ACTION_TYPE_COUNTER,
        reasoning="LLM reasoning",
        negotiation=NegotiationIntent(price=price, message="Here is my offer"),
    )


def bound_skill(account: Any) -> AttestationSkill:
    skill = AttestationSkill()
    skill.bind(AttestationSettings(), AttestationEngine(account.key.hex()))
    return skill


class TestTheMembraneAttests:
    @pytest.mark.asyncio
    async def test_a_signed_receipt_recovers_to_the_configured_signer(self) -> None:
        account = Account.create()

        decision = await membrane_with(bound_skill(account)).inspect_outbound(
            counter(price=2000.0), context()
        )

        receipt = decision.receipt
        assert receipt.version == "AURA-RECEIPT-V2"
        assert receipt.signature.signer == account.address

        payload = signing_payload(receipt, chain_id=receipt.signature.chain_id)
        raw = bytes.fromhex(receipt.signature.signature.removeprefix("0x"))
        recovered = Account.recover_message(
            encode_typed_data(full_message=payload), signature=raw
        )
        assert recovered == account.address

    @pytest.mark.asyncio
    async def test_no_attestation_protein_leaves_the_receipt_unsigned(self) -> None:
        decision = await membrane_with(None).inspect_outbound(
            counter(price=2000.0), context()
        )

        assert decision.receipt.version == "AURA-RECEIPT-V2-UNSIGNED"
        assert decision.negotiation.price == 2000.0

    @pytest.mark.asyncio
    async def test_a_signing_failure_does_not_cost_the_decision(self) -> None:
        class _Broken(AttestationSkill):
            async def execute(self, intent: str, params: dict[str, Any]):
                raise RuntimeError("key unreachable")

        decision = await membrane_with(_Broken()).inspect_outbound(
            counter(price=2000.0), context()
        )

        assert decision.receipt.version == "AURA-RECEIPT-V2-UNSIGNED"
        assert decision.action == ActionType.ACTION_TYPE_COUNTER
        assert decision.negotiation.price == 2000.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=core/src:core/gen-proto:packages/aura-core/src:packages/aura-core/gen-proto uv run pytest core/tests/test_attestation_membrane.py -v`
Expected: FAIL — `test_a_signed_receipt_recovers_to_the_configured_signer` fails because `_attest` calls `"transaction"`, which is not registered, so the receipt stays `AURA-RECEIPT-V2-UNSIGNED`.

- [ ] **Step 3: Write minimal implementation**

In `core/src/aura_hive/hive/membrane/main.py`, inside `_attest`, replace the settings read and the registry call:

```python
            # Looked up rather than accessed: settings with no attestation
            # section is a configuration a deployment may legitimately have,
            # and an expected absence should not be discovered by throwing.
            attestation = getattr(self.settings, "attestation", None)
            chain_id = int(getattr(attestation, "chain_id", 0) or 0)
            obs = await self.registry.execute(
                "attestation",
                "sign_receipt",
                {"payload": signing_payload(receipt, chain_id=chain_id)},
            )
```

Then delete the old path. In `core/src/aura_hive/hive/proteins/transaction/skill.py`, remove the `"sign_receipt": self._sign_receipt,` entry from `_capabilities` and delete the whole `_sign_receipt` method. In `core/src/aura_hive/hive/proteins/transaction/engine.py`, delete the `sign_receipt` method from `EVMProvider`.

Leaving them would keep a second signing path with no caller, which drifts from the live one and then gets used by someone who found it first.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=core/src:core/gen-proto:packages/aura-core/src:packages/aura-core/gen-proto uv run pytest core/tests/test_attestation_membrane.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Confirm the deleted capability had no test of its own**

Run: `grep -rn "sign_receipt" core/tests/`
Expected: **no matches.** No test covered the capability being deleted — which is itself worth
noticing, since it is the reason nothing caught that signing was unreachable in every deployed
configuration. Task 2 is the first test this behaviour has ever had.

If the grep does return a hit, delete that case rather than adapting it to call the new protein:
`test_attestation_protein.py` already covers the behaviour, and two tests of one thing drift.

Then run the neighbouring suites to catch anything that touched the transaction protein's capability
list: `PYTHONPATH=core/src:core/gen-proto:packages/aura-core/src:packages/aura-core/gen-proto uv run pytest core/tests/test_transaction_skill.py core/tests/test_receipt_transport.py -v`

- [ ] **Step 6: Run the whole core suite**

Run: `PYTHONPATH=core/src:core/gen-proto:packages/aura-core/src:packages/aura-core/gen-proto uv run pytest core/tests/ -q`
Expected: all pass.

- [ ] **Step 7: Lint and commit**

```bash
make lint
git add core/src/aura_hive/hive/membrane/main.py core/src/aura_hive/hive/proteins/transaction core/tests/
git commit -m "feat(membrane): attest through the protein that holds the key, and delete the other path"
```

---

### Task 5: Deployment, provenance, and the doc that was already claiming this

**Files:**
- Modify: `deploy/aura/templates/core-deployment.yaml` (env list, beside the `AURA_CRYPTO__*` entries at lines 74-84)
- Create: `docs/attestation-signers.md`
- Modify: `docs/DECISION_RECEIPT.md` (§7, the "Recovering the signer" section)
- Modify: `.env.example`
- Test: `core/tests/test_attestation_rotation.py`

**Interfaces:**
- Consumes: everything from Tasks 1-4.
- Produces: no code interface. This task makes the feature reachable in a deployment and truthful in the docs.

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_attestation_rotation.py`:

```python
"""
Rotating the key must not invalidate what the old key signed.

This is the premise the whole design rests on: verifying a past signature needs
only the address it recovers to, never the private key. If it were false,
signing before a consumer exists would be worthless, because the key would have
to outlive the gap.
"""

import pytest
from aura_core import SkillRegistry
from aura_core.struct_utils import make_struct
from aura_core_gen.aura.core.v1 import (
    ActionType,
    Context,
    HiveContextData,
    Intent,
    NegotiationIntent,
)
from eth_account import Account
from eth_account.messages import encode_typed_data

from aura_hive.config.attestation import AttestationSettings
from aura_hive.config.policy import SafetySettings
from aura_hive.hive.membrane.main import HiveMembrane
from aura_hive.hive.membrane.receipt import signing_payload
from aura_hive.hive.proteins.attestation import AttestationEngine, AttestationSkill
from aura_hive.hive.proteins.guard import GuardSkill
from aura_hive.hive.proteins.guard.engine import OutputGuard


class _Safety:
    min_profit_margin = 0.10
    ui_trigger_price = 100000.0
    trade_risk_threshold = 0.10


class _Settings:
    def __init__(self, chain_id: int) -> None:
        self.attestation = AttestationSettings(chain_id=chain_id)


async def mint(account, chain_id: int):
    registry = SkillRegistry()
    guard = GuardSkill()
    guard.bind(_Safety(), OutputGuard(safety_settings=_Safety()))
    registry.register(guard.get_name(), guard)
    skill = AttestationSkill()
    skill.bind(AttestationSettings(), AttestationEngine(account.key.hex()))
    registry.register("attestation", skill)
    membrane = HiveMembrane(registry=registry)
    membrane.settings = _Settings(chain_id)

    decision = await membrane.inspect_outbound(
        Intent(
            action=ActionType.ACTION_TYPE_COUNTER,
            reasoning="LLM reasoning",
            negotiation=NegotiationIntent(price=2000.0, message="Here is my offer"),
        ),
        Context(
            metadata=make_struct({"floor_price": "1000.0", "internal_cost": "777.0"}),
            hive=HiveContextData(request_id="req-rotate"),
        ),
    )
    return decision.receipt


def verifies(receipt) -> bool:
    payload = signing_payload(receipt, chain_id=receipt.signature.chain_id)
    raw = bytes.fromhex(receipt.signature.signature.removeprefix("0x"))
    recovered = Account.recover_message(
        encode_typed_data(full_message=payload), signature=raw
    )
    return bool(recovered == receipt.signature.signer)


@pytest.mark.asyncio
async def test_an_old_receipt_still_verifies_after_the_key_is_rotated() -> None:
    old_account = Account.create()
    old_receipt = await mint(old_account, chain_id=84532)

    # The deployment rotates: a new key, and a different domain chain id.
    new_receipt = await mint(Account.create(), chain_id=1)

    assert verifies(old_receipt)
    assert verifies(new_receipt)
    assert old_receipt.signature.signer != new_receipt.signature.signer
    assert old_receipt.signature.chain_id == 84532
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=core/src:core/gen-proto:packages/aura-core/src:packages/aura-core/gen-proto uv run pytest core/tests/test_attestation_rotation.py -v`
Expected: PASS immediately if Tasks 1-4 are correct. **This one is a characterisation test, not a red-green cycle** — it pins a property the design claims rather than driving new code. If it FAILS, the signature block is not recording its own domain and the design's rotation premise is broken: stop and report rather than patching the test.

- [ ] **Step 3: Plumb the secret into the deployment**

In `deploy/aura/templates/core-deployment.yaml`, add beside the existing crypto env entries:

```yaml
            - name: AURA_ATTESTATION__PRIVATE_KEY
              valueFrom:
                secretKeyRef:
                  name: "{{ .Release.Name }}-secrets"
                  key: "attestation-private-key"
                  optional: true
```

`optional: true` matters: the deployment must keep starting before anyone creates the secret, logging `attestation_disabled_no_key` and behaving exactly as it does today.

In `.env.example`, add:

```bash
# Signs decision receipts (docs/DECISION_RECEIPT.md §7). Its own key, not the
# crypto spending key: a deployment can attest decisions without enabling
# payment locks. Unset means receipts are emitted AURA-RECEIPT-V2-UNSIGNED,
# which is a legitimate configuration, not a failure.
AURA_ATTESTATION__PRIVATE_KEY=
AURA_ATTESTATION__CHAIN_ID=84532
```

- [ ] **Step 4: Create the provenance record**

Create `docs/attestation-signers.md`:

```markdown
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

| address | environment | active from | status |
|---------|-------------|-------------|--------|
| _(none yet — no key has been placed)_ | | | |
```

- [ ] **Step 5: Correct the receipt doc**

In `docs/DECISION_RECEIPT.md`, the "Recovering the signer" section says `AURA-RECEIPT-V2-UNSIGNED` means "the deployment had no key configured". Until now that was false — it meant crypto payments were off. Replace that sentence with:

```markdown
**Read `version` first.** `AURA-RECEIPT-V2-UNSIGNED` means the deployment had no attestation key
configured and `signature` is `null`. That is a legitimate configuration rather than a fault: the key
lives in `AURA_ATTESTATION__PRIVATE_KEY`, a deployment may run without one, and the decision is
emitted either way — losing a negotiation because a key was unreachable would trade the guarantee for
the attestation. Which address a deployment signs with is recorded in
`docs/attestation-signers.md` and stated in its startup log. Everything else in the receipt is still
checkable to the extent described above, but nobody has vouched for it. Treating one as the other is
the downgrade the two names exist to prevent.
```

- [ ] **Step 6: Run the whole suite and lint**

```bash
PYTHONPATH=core/src:core/gen-proto:packages/aura-core/src:packages/aura-core/gen-proto uv run pytest core/tests/ -q
make lint
```

Expected: all core tests pass, lint exits 0.

- [ ] **Step 7: Commit**

```bash
git add deploy/aura/templates/core-deployment.yaml .env.example docs/attestation-signers.md docs/DECISION_RECEIPT.md core/tests/test_attestation_rotation.py
git commit -m "feat(deploy): make attestation reachable, and record which address is ours"
```

---

## After the plan

The code is inert until an operator generates a key, puts it in the release secret as
`attestation-private-key`, and adds its address to `docs/attestation-signers.md`. That is deliberate
and out of scope here: the plan ships the mechanism, a human decides when a deployment starts
vouching for its decisions.

Verify after the key is placed: the pod logs `attestation_signer_ready address=0x…` once at boot, and
`make verify-receipts LOG=<path>` over fresh logs reports receipts as `attested` rather than
unverifiable.
