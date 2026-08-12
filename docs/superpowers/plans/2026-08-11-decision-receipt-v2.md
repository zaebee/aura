# Decision Receipt V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the negotiation guard prove a stated post-condition on the value it actually emits, and move the decision receipt to a format that binds to the decision it describes.

**Architecture:** The guard (`proteins/guard/`) owns the rules and gains a declared post-condition ψ, checked in the Membrane against the settled emission on both the pass and override paths. The substitute price is recomputed in `Decimal` with ceiling rounding and per-session jitter so it cannot breach ψ and cannot be inverted to the hidden floor. The receipt (`membrane/receipt.py`) moves to `AURA-RECEIPT-V2` with a timestamp and identifiers in its signed content, and its verifier starts naming what it could not check.

**Tech Stack:** Python 3.12, `uv`, protobuf via `buf` → betterproto (`aura_core_gen`), pytest, structlog, `eth_account` for EIP-712.

**Spec:** `docs/superpowers/specs/2026-08-11-decision-receipt-v2-design.md`. Read it before Task 1; the Decisions table is the authority when this plan and your instincts disagree.

## Global Constraints

- Branch: `feat/decision-receipt-v2`, already created, based on `main` @ `4d1d70d`.
- Python **3.12+**, package manager **`uv`** — never `pip`, never `poetry`.
- Core tests run as: `PYTHONPATH=core/src:core/gen-proto:packages/aura-core/src:packages/aura-core/gen-proto uv run pytest core/tests/ -v`. This plan writes that prefix as `$CORE` — expand it every time.
- Gateway tests run as: `PYTHONPATH=api-gateway/src:api-gateway/gen-proto:packages/aura-core/src:packages/aura-core/gen-proto uv run pytest api-gateway/tests/ -v`. Written below as `$GW`.
- **Never hand-edit generated protobuf code** (`*/gen-proto/`, `aura_core_gen`). Edit `proto/aura/**` and run `make generate`.
- **Generated code is gitignored.** `core/gen-proto` and `packages/aura-core/gen-proto` are not tracked, so a `git add` naming them fails with "paths are ignored". Stage `proto/`, hand-written sources and tests only.
- **A new `DecisionOutcome` value needs a name in `packages/aura-core/src/aura_core/wire_names.py`.** That mapping is signed content — an unnamed outcome signs as `outcome_4`, and the name is the whole reason the integer is not what gets signed. `test_every_declared_outcome_has_a_name` catches the drift.
- **betterproto: absence is not `None`.** `msg.field is None` is always false for a message field and is dead code. Test absence by value: `if not receipt:`. For oneofs use `betterproto.which_one_of()`. See `docs/CLAUDE.md` § "betterproto".
- All money arithmetic inside the guard is `decimal.Decimal`. Never `float`, never `round()`. Prices cross the protobuf boundary as `double`, so convert at the edge with `Decimal(str(value))` and return `float(result)`.
- Every task ends green: `make lint` and the relevant test suite pass before the commit.
- Commit messages: imperative subject, no trailing period, and end with the `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` trailer.

---

## File Structure

| file | responsibility | tasks |
|---|---|---|
| `proto/aura/core/v1/metabolism.proto` | wire contract: new outcome, receipt fields, currency fields | 1, 9 |
| `core/src/aura_hive/hive/proteins/guard/ruleset.yaml` | the declared rules and ψ | 2 |
| `core/src/aura_hive/hive/proteins/guard/ruleset.py` | parse, validate and digest the rule set | 2 |
| `core/src/aura_hive/hive/proteins/guard/engine.py` | gates, `safe_offer`, ψ predicates, `GuardUnavailable` | 3, 4 |
| `core/src/aura_hive/hive/proteins/guard/skill.py` | protein surface for the above | 4 |
| `core/src/aura_hive/hive/membrane/main.py` | calls ψ, stamps receipt fields, neutralises messages | 5, 6, 8 |
| `core/src/aura_hive/hive/membrane/receipt.py` | V2 format, `mint`, `verify` | 7, 8 |
| `core/src/aura_hive/hive/aggregator/main.py` | carries currency into context | 9 |
| `api-gateway/src/api_gateway/main.py` | public vs full receipt rendering | 10 |
| `tools/verify_receipts.py` | the auditor's reader | 11 |
| `docs/DECISION_RECEIPT.md` | the corrected record | 12 |

Task order is a dependency order. Tasks 1–8 must run in sequence; 9, 10, 11, 12 may run in any order after 8.

---

### Task 1: Proto — the unavailable outcome and the four receipt fields

**Files:**
- Modify: `proto/aura/core/v1/metabolism.proto:193-198` (enum), `:241-287` (`DecisionReceipt`)
- Test: `core/tests/test_receipt_v2_proto.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `DecisionOutcome.DECISION_OUTCOME_UNAVAILABLE` (value `4`); `DecisionReceipt.issued_at: str`, `.decision_id: str`, `.request_id: str`, `.override_scope: str` at field numbers 12–15.

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_receipt_v2_proto.py`:

```python
"""
The wire contract V2 depends on.

A separate file from test_receipt.py because this asserts the shape of the
generated types rather than any behaviour over them, and it is the first thing
to look at when a regeneration goes wrong.
"""

from aura_core_gen.aura.core.v1 import DecisionOutcome, DecisionReceipt


def test_unavailable_is_a_distinct_outcome() -> None:
    """
    A verdict nobody could establish is not a verdict against the decision.
    Sharing a value with REFUSE would make the two indistinguishable to a reader.
    """
    assert DecisionOutcome.DECISION_OUTCOME_UNAVAILABLE == 4
    assert DecisionOutcome.DECISION_OUTCOME_UNAVAILABLE != DecisionOutcome.DECISION_OUTCOME_REFUSE


def test_receipt_carries_the_binding_fields() -> None:
    """
    Without these a receipt describes an equivalence class of decisions rather
    than one decision: two negotiations for the same item at the same price
    produced a byte-identical receipt, signature included.
    """
    receipt = DecisionReceipt()
    assert receipt.issued_at == ""
    assert receipt.decision_id == ""
    assert receipt.request_id == ""
    assert receipt.override_scope == ""
```

- [ ] **Step 2: Run it and watch it fail**

Run: `$CORE uv run pytest core/tests/test_receipt_v2_proto.py -v`
Expected: FAIL — `AttributeError: DECISION_OUTCOME_UNAVAILABLE` on the first test.

- [ ] **Step 3: Extend the enum**

In `proto/aura/core/v1/metabolism.proto`, replace the `DecisionOutcome` body:

```protobuf
enum DecisionOutcome {
  DECISION_OUTCOME_UNSPECIFIED = 0;
  DECISION_OUTCOME_EMIT = 1;       // passed every gate unaltered
  DECISION_OUTCOME_OVERRIDE = 2;   // a gate fired; a safe value was substituted
  DECISION_OUTCOME_REFUSE = 3;     // a gate fired; the action was rejected

  // No verdict could be established: the guard's own post-condition did not
  // hold, or a fact it needed could not be looked up. Distinct from REFUSE
  // because a rule judging against a decision and a judgment that never
  // happened send an operator to different places. AR4SI calls this tier
  // "none"; its -1 is "a verifier malfunction occurred".
  DECISION_OUTCOME_UNAVAILABLE = 4;
}
```

- [ ] **Step 4: Add the receipt fields**

In `message DecisionReceipt`, immediately after the `signature = 11;` field, add:

```protobuf
  // When the Membrane settled this decision, RFC3339 UTC. Freshness by the
  // synchronized-clock route of RFC 9334 §10. It is our clock and means nothing
  // to a party that does not trust us — which the audience decision says is not
  // the reader this is for.
  string issued_at = 12;

  // The Intent this receipt describes, and the negotiation session it belongs
  // to. Without them a receipt is about a shape of decision rather than one
  // decision, and an auditor cannot reconcile it against anything.
  string decision_id = 13;
  string request_id = 14;

  // Why claim and emission hash alike under an override: "prose" when the
  // substitution touched only free text, "value" when it touched the decidable
  // content. Empty unless outcome is OVERRIDE. Lets a verifier check the pairing
  // in both directions without a hardcoded list of gates that goes stale.
  string override_scope = 15;
```

- [ ] **Step 5: Regenerate**

Run: `make generate`
Expected: `buf generate` completes; `core/gen-proto/` and `packages/aura-core/gen-proto/` update.

- [ ] **Step 6: Run the test and watch it pass**

Run: `$CORE uv run pytest core/tests/test_receipt_v2_proto.py -v`
Expected: PASS, 2 tests.

- [ ] **Step 7: Confirm nothing else broke**

Run: `$CORE uv run pytest core/tests/ -q`
Expected: PASS. Adding an enum value and four optional string fields is backward compatible; if anything fails here, the failure is real and must be fixed before committing.

- [x] **Step 8: Commit** — done, `df0db4b`. Generated code is gitignored, so the staged set is:

```bash
git add proto/aura/core/v1/metabolism.proto packages/aura-core/src/aura_core/wire_names.py core/tests/test_receipt_v2_proto.py
```

---

### Task 2: Rule set — declare ψ, collapse the strategy to one

**Files:**
- Modify: `core/src/aura_hive/hive/proteins/guard/ruleset.py`, `core/src/aura_hive/hive/proteins/guard/ruleset.yaml`
- Test: `core/tests/test_guard_ruleset.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `Clause(id: str, expr: str, consumes: tuple[str, ...])`; `Postcondition(id: str, clauses: tuple[Clause, ...])`; `Ruleset.safe_price: str`; `Ruleset.postcondition: Postcondition`; `Ruleset.validate_against(gates: set[str], clauses: set[str]) -> None`; `Gate` **loses** its `safe_price` attribute; `SAFE_PRICE_STRATEGIES == frozenset({"safe_offer"})`.

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_guard_ruleset.py`:

```python
class TestPostcondition:
    """
    What the rule set guarantees, as opposed to which rules it applies.

    The gates say what was checked; psi says what the checking was for. Without
    it `ruleset_version` names a set of rules and nobody has stated what holds
    when they pass — which is how a below-margin override price shipped under a
    receipt that verified.
    """

    def test_the_postcondition_is_parsed_with_its_clauses(self) -> None:
        ruleset = load_ruleset()
        assert ruleset.postcondition.id == "PSI_NEGOTIATION_V1"
        assert [c.id for c in ruleset.postcondition.clauses] == [
            "PSI_PRICE_POSITIVE",
            "PSI_ABOVE_FLOOR",
            "PSI_MIN_MARGIN",
        ]

    def test_the_margin_clause_is_multiplicative(self) -> None:
        """
        The ratio form is not decidable in binary floats on money: where the
        price is exactly right, (price - cost)/price evaluates to
        0.09999999999999995 against 0.1. psi is fail-closed, so that artefact
        costs a live negotiation.
        """
        ruleset = load_ruleset()
        clause = next(
            c for c in ruleset.postcondition.clauses if c.id == "PSI_MIN_MARGIN"
        )
        assert "/" not in clause.expr
        assert clause.expr == "price * (1 - min_profit_margin) >= internal_cost"

    def test_editing_a_clause_changes_the_digest(self) -> None:
        """
        psi is part of what the rule set promises, so a receipt citing a version
        must cite a different one when the promise changes.
        """
        base = load_ruleset()
        edited = {
            "family": base.family,
            "version": base.version,
            "safe_price": base.safe_price,
            "postcondition": {
                "id": base.postcondition.id,
                "clauses": [
                    {"id": c.id, "expr": c.expr + " ", "consumes": list(c.consumes)}
                    for c in base.postcondition.clauses
                ],
            },
            "gates": [
                {"id": g.id, "code": g.code, "consumes": list(g.consumes)}
                for g in base.gates
            ],
        }
        assert ruleset_from_mapping(edited).digest != base.digest

    def test_a_missing_postcondition_is_refused(self) -> None:
        without = {
            "family": "guard/negotiation",
            "version": "2.0.0",
            "safe_price": "safe_offer",
            "gates": [{"id": "G1", "code": "C1", "consumes": []}],
        }
        with pytest.raises(RulesetError, match="postcondition"):
            ruleset_from_mapping(without)


class TestStrategyCollapse:
    """
    One substitute strategy, declared once for the set.

    Two strategies whose guarantees are indistinguishable is the crack the
    below-margin price came through: G2 fired, short-circuited G4, and the
    floor-markup substitute was never judged against the margin rule.
    """

    def test_the_strategy_is_declared_once_for_the_set(self) -> None:
        ruleset = load_ruleset()
        assert ruleset.safe_price == "safe_offer"
        assert not any(hasattr(gate, "safe_price") for gate in ruleset.gates)

    def test_a_per_gate_strategy_is_refused_not_ignored(self) -> None:
        """
        Rejected rather than ignored on purpose: a per-gate `safe_price` key is
        exactly what a stale pre-collapse ruleset.yaml still carries, and
        ignoring it would load a file describing two strategies into an engine
        that implements one.
        """
        stale = {
            "family": "guard/negotiation",
            "version": "2.0.0",
            "safe_price": "safe_offer",
            "postcondition": {"id": "P", "clauses": [{"id": "C", "expr": "x", "consumes": []}]},
            "gates": [
                {"id": "G1", "code": "C1", "consumes": [], "safe_price": "margin"}
            ],
        }
        with pytest.raises(RulesetError, match="safe_price"):
            ruleset_from_mapping(stale)

    def test_an_unknown_set_strategy_is_refused(self) -> None:
        unknown = {
            "family": "guard/negotiation",
            "version": "2.0.0",
            "safe_price": "floor_markup",
            "postcondition": {"id": "P", "clauses": [{"id": "C", "expr": "x", "consumes": []}]},
            "gates": [{"id": "G1", "code": "C1", "consumes": []}],
        }
        with pytest.raises(RulesetError, match="safe_offer"):
            ruleset_from_mapping(unknown)


class TestClauseCrossCheck:
    def test_an_undeclared_clause_predicate_is_refused(self) -> None:
        ruleset = load_ruleset()
        declared = {c.id for c in ruleset.postcondition.clauses}
        with pytest.raises(RulesetError, match="not declared"):
            ruleset.validate_against(
                {g.id for g in ruleset.gates}, declared | {"PSI_INVENTED"}
            )

    def test_a_clause_with_no_predicate_is_refused(self) -> None:
        ruleset = load_ruleset()
        declared = {c.id for c in ruleset.postcondition.clauses}
        with pytest.raises(RulesetError, match="not implemented"):
            ruleset.validate_against(
                {g.id for g in ruleset.gates}, declared - {"PSI_MIN_MARGIN"}
            )
```

Add `load_ruleset` and `RulesetError` to the existing import block at the top of the file if they are not already there.

- [ ] **Step 2: Run and watch them fail**

Run: `$CORE uv run pytest core/tests/test_guard_ruleset.py -v`
Expected: FAIL — `AttributeError: 'Ruleset' object has no attribute 'postcondition'`.

- [ ] **Step 3: Rewrite `ruleset.yaml`**

Replace the whole file body below the header comment:

```yaml
family: guard/negotiation
version: 2.0.0

# One substitute strategy for the whole set, not one per gate.
#
# `floor_markup` and `margin` used to differ, and the difference was the bug:
# max(floor*1.05, max(floor, internal_cost)/(1-m)) is >= what `margin` produced
# in every case, so keeping both bought nothing and let a gate pick the weaker
# one. Every gate now errs toward the seller by construction.
safe_price: safe_offer

# What the guard guarantees about the value it lets out — as opposed to the
# gates, which say what it checked about the value the model proposed. Those
# are different claims, and only the second one was ever written down.
#
# Checked on the emission, on both the pass and override paths. Clause ids are
# the contract with the engine exactly as gate ids are: the predicates are
# Python, matched by id, cross-checked in both directions at construction.
#
# PSI_MIN_MARGIN is multiplicative rather than (price - cost)/price >= m. The
# ratio form is not decidable in binary floats on money, and psi is fail-closed,
# so a 5e-17 artefact would refuse a correct decision.
postcondition:
  id: PSI_NEGOTIATION_V1
  clauses:
    - id: PSI_PRICE_POSITIVE
      expr: "price > 0"
      consumes: [price]

    - id: PSI_ABOVE_FLOOR
      expr: "price >= floor_price"
      consumes: [price, floor_price]

    - id: PSI_MIN_MARGIN
      expr: "price * (1 - min_profit_margin) >= internal_cost"
      consumes: [price, internal_cost]

# Evaluated in this order. The first gate to fail is the binding reason, and it
# is the one recorded on the receipt; the rest are not evaluated. The order
# reproduces the if-chain that shipped before the rules were extracted, so
# decisions keep the reason they were refused under.
#
# `consumes` names premise keys, never their values.
gates:
  - id: G1_PRICE_POSITIVE
    code: INVALID_PRICE
    consumes: [price]

  - id: G2_FLOOR_VIOLATION
    code: FLOOR_PRICE_VIOLATION
    consumes: [price, floor_price]

  # Fail-closed: a deployment that cannot read its own margin setting must not
  # answer at all rather than answer with a formula it cannot evaluate.
  - id: G3_SETTINGS_PRESENT
    code: SETTINGS_MISSING
    consumes: []

  - id: G4_MARGIN_VIOLATION
    code: MIN_MARGIN_VIOLATION
    consumes: [price, internal_cost]
```

- [ ] **Step 4: Teach `ruleset.py` the new shape**

In `core/src/aura_hive/hive/proteins/guard/ruleset.py`:

Replace the strategy constant:

```python
# The only substitute strategy. Kept as a set rather than a bare string so an
# unrecognised value reads as "a rule set claiming behaviour the engine has no
# implementation for" — the same failure as an undeclared gate.
SAFE_PRICE_STRATEGIES = frozenset({"safe_offer"})
```

Remove `safe_price` from `Gate`:

```python
@dataclass(frozen=True)
class Gate:
    """One declared rule, in the order it is evaluated."""

    id: str
    code: str
    consumes: tuple[str, ...]
```

Add the two new dataclasses above `Ruleset`:

```python
@dataclass(frozen=True)
class Clause:
    """One conjunct of the post-condition, in the order it is evaluated."""

    id: str
    expr: str
    consumes: tuple[str, ...]


@dataclass(frozen=True)
class Postcondition:
    """
    What the rule set guarantees about an emitted decision.

    `expr` is prose for a human reader and for the digest, never evaluated: an
    expression evaluator in the guard would be a second implementation of the
    rules, and the point of declaring them once is to not have that.
    """

    id: str
    clauses: tuple[Clause, ...]
```

Replace `Ruleset` and `validate_against`:

```python
@dataclass(frozen=True)
class Ruleset:
    family: str
    version: str
    safe_price: str
    postcondition: Postcondition
    gates: tuple[Gate, ...]
    digest: str

    @property
    def version_string(self) -> str:
        """`guard/negotiation@2.0.0+9c1de4a70b3f5821` — family, semver, digest."""
        return f"{self.family}@{self.version}+{self.digest}"

    def validate_against(self, gates: set[str], clauses: set[str]) -> None:
        """
        Confirm the declaration and the implementation describe the same rules.

        Both directions are errors, for gates and for post-condition clauses
        alike. A declared rule with no predicate would never fire while the rule
        set advertises that it does; an implemented predicate that is not
        declared runs outside anything a receipt can account for. Either way the
        version string would name behaviour that is not the behaviour.
        """
        for kind, declared, implemented in (
            ("gates", {gate.id for gate in self.gates}, gates),
            ("postcondition clauses", {c.id for c in self.postcondition.clauses}, clauses),
        ):
            undeclared = sorted(implemented - declared)
            if undeclared:
                raise RulesetError(
                    f"{kind} implemented but not declared in ruleset.yaml: {undeclared}"
                )

            unimplemented = sorted(declared - implemented)
            if unimplemented:
                raise RulesetError(
                    f"{kind} declared in ruleset.yaml but not implemented: {unimplemented}"
                )
```

Rewrite `ruleset_from_mapping`:

```python
def _clauses_from(raw_postcondition: Any) -> tuple[str, tuple[Clause, ...]]:
    """Parse the postcondition block, rejecting anything malformed."""
    if not isinstance(raw_postcondition, dict):
        raise RulesetError("ruleset key 'postcondition' must be a mapping")

    for key in ("id", "clauses"):
        if key not in raw_postcondition:
            raise RulesetError(f"postcondition is missing required key: {key!r}")

    raw_clauses = raw_postcondition["clauses"]
    if not isinstance(raw_clauses, list) or not raw_clauses:
        raise RulesetError("postcondition key 'clauses' must be a non-empty list")

    clauses: list[Clause] = []
    seen: set[str] = set()
    for position, raw in enumerate(raw_clauses):
        if not isinstance(raw, dict):
            raise RulesetError(f"clause at position {position} must be a mapping")
        for key in ("id", "expr", "consumes"):
            if key not in raw:
                raise RulesetError(f"clause at position {position} is missing {key!r}")
        if not isinstance(raw["consumes"], list):
            raise RulesetError(
                f"clause at position {position} declares 'consumes' as "
                f"{type(raw['consumes']).__name__}, expected a list"
            )
        clause_id = str(raw["id"])
        if clause_id in seen:
            raise RulesetError(f"duplicate clause id in postcondition: {clause_id!r}")
        seen.add(clause_id)
        clauses.append(
            Clause(
                id=clause_id,
                expr=str(raw["expr"]),
                consumes=tuple(str(key) for key in raw["consumes"]),
            )
        )

    return str(raw_postcondition["id"]), tuple(clauses)


def ruleset_from_mapping(mapping: dict[str, Any]) -> Ruleset:
    """Build a Ruleset from already-parsed YAML, rejecting anything malformed."""
    for key in ("family", "version", "safe_price", "postcondition", "gates"):
        if key not in mapping:
            raise RulesetError(f"ruleset is missing required key: {key!r}")

    strategy = str(mapping["safe_price"])
    if strategy not in SAFE_PRICE_STRATEGIES:
        raise RulesetError(
            f"ruleset declares unknown safe_price strategy {strategy!r}; "
            f"expected one of {sorted(SAFE_PRICE_STRATEGIES)}"
        )

    postcondition_id, clauses = _clauses_from(mapping["postcondition"])

    raw_gates = mapping["gates"]
    if not isinstance(raw_gates, list) or not raw_gates:
        raise RulesetError("ruleset key 'gates' must be a non-empty list")

    gates: list[Gate] = []
    seen: set[str] = set()
    for position, raw in enumerate(raw_gates):
        if not isinstance(raw, dict):
            raise RulesetError(f"gate at position {position} must be a mapping")

        for key in ("id", "code", "consumes"):
            if key not in raw:
                raise RulesetError(f"gate at position {position} is missing {key!r}")

        # Refused rather than ignored: this key is what a stale pre-collapse
        # ruleset.yaml still carries, and ignoring it would load a file that
        # describes two strategies into an engine that implements one.
        if "safe_price" in raw:
            raise RulesetError(
                f"gate at position {position} declares a per-gate 'safe_price'; "
                "the strategy is declared once for the set"
            )

        if not isinstance(raw["consumes"], list):
            raise RulesetError(
                f"gate at position {position} declares 'consumes' as "
                f"{type(raw['consumes']).__name__}, expected a list"
            )

        gate_id = str(raw["id"])
        if gate_id in seen:
            raise RulesetError(f"duplicate gate id in ruleset: {gate_id!r}")
        seen.add(gate_id)

        gates.append(
            Gate(
                id=gate_id,
                code=str(raw["code"]),
                consumes=tuple(str(key) for key in raw["consumes"]),
            )
        )

    family = str(mapping["family"])
    version = str(mapping["version"])
    canonical = {
        "family": family,
        "version": version,
        "safe_price": strategy,
        "postcondition": {
            "id": postcondition_id,
            "clauses": [
                {"id": c.id, "expr": c.expr, "consumes": list(c.consumes)}
                for c in clauses
            ],
        },
        "gates": [
            {"id": gate.id, "code": gate.code, "consumes": list(gate.consumes)}
            for gate in gates
        ],
    }

    return Ruleset(
        family=family,
        version=version,
        safe_price=strategy,
        postcondition=Postcondition(id=postcondition_id, clauses=clauses),
        gates=tuple(gates),
        digest=hashlib.sha256(_canonical(canonical)).hexdigest()[:_DIGEST_CHARS],
    )
```

- [ ] **Step 5: Fix the callers this breaks**

`OutputGuard.__init__` in `engine.py` calls `validate_against` with one argument and builds `_safe_price_strategies` from per-gate values. Both are now wrong. Change only enough to compile — Task 3 rewrites this properly:

```python
        self.ruleset.validate_against(set(self.gate_ids()), set(self.clause_ids()))
```

and delete the `self._safe_price_strategies = {...}` line. Add a placeholder classmethod beside `gate_ids`:

```python
    @classmethod
    def clause_ids(cls) -> tuple[str, ...]:
        """The post-condition clauses this engine can evaluate."""
        return ("PSI_PRICE_POSITIVE", "PSI_ABOVE_FLOOR", "PSI_MIN_MARGIN")
```

In `calculate_safe_price`, replace the strategy lookup with the old margin branch so behaviour is unchanged until Task 3:

```python
        floor = _numeric(context, "floor_price")
        min_m = self._configured_margin()
        return float(round(floor / (1 - min_m), 2))
```

- [ ] **Step 6: Update the pinned digest**

Run: `$CORE uv run pytest core/tests/test_guard_ruleset.py -v`
The pin test fails with the new digest in the message. Copy that value into the pin in `test_the_shipped_version_string_is_the_pinned_one`, and update the `version_string` it expects to `guard/negotiation@2.0.0+<new digest>`.

- [ ] **Step 7: Run the guard suite**

Run: `$CORE uv run pytest core/tests/test_guard_ruleset.py core/tests/test_guard_gates.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add core/src/aura_hive/hive/proteins/guard/ core/tests/test_guard_ruleset.py
git commit -m "feat(guard): declare the post-condition and collapse the substitute strategy

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: `safe_offer` — Decimal, ceiling, internal_cost, per-session jitter

**Files:**
- Modify: `core/src/aura_hive/hive/proteins/guard/engine.py`
- Test: `core/tests/test_guard_safe_offer.py` (create)

**Interfaces:**
- Consumes: `Ruleset.safe_price` from Task 2.
- Produces: `OutputGuard.calculate_safe_price(self, context: dict, reason: str = "", request_id: str = "") -> float`. The signature stays compatible with the existing two call sites so nothing breaks before Task 6; `reason` is now unused and `request_id` defaults to `""` (no jitter).

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_guard_safe_offer.py`:

```python
"""
The substitute price, and the two ways the arithmetic used to betray it.

`round(floor/(1-m), 2)` rounds toward the nearest cent, which for a margin
substitute means half the time toward breaching it, and a lower price is a lower
margin. And the substitute was a function of `floor` alone while the margin rule
is about `internal_cost`, so where cost exceeded floor no substitute could
satisfy it at all. Both produced prices the guard's own post-condition rejects.
"""

from decimal import Decimal

import pytest
from aura_hive.hive.proteins.guard.engine import OutputGuard


class Settings:
    def __init__(self, margin: float = 0.1) -> None:
        self.min_profit_margin = margin


def holds(price: float, floor: float, cost: float, margin: float) -> bool:
    """psi, in Decimal, exactly as the rule set declares it."""
    p, c, m = Decimal(str(price)), Decimal(str(cost)), Decimal(str(margin))
    return p > 0 and p >= Decimal(str(floor)) and p * (1 - m) >= c


class TestRounding:
    def test_the_default_configuration_satisfies_the_margin_rule(self) -> None:
        """
        floor=100, cost=100, m=0.1 requires 111.1111..., and rounding to the
        nearest cent gave 111.11 — margin 0.099991, under the minimum. This is
        the case the audit broke the first design on.
        """
        guard = OutputGuard(safety_settings=Settings(0.1))
        price = guard.calculate_safe_price({"floor_price": 100.0, "internal_cost": 100.0})
        assert price == 111.12
        assert holds(price, 100.0, 100.0, 0.1)

    @pytest.mark.parametrize("margin", [0.0, 0.01, 0.05, 0.1, 0.15, 0.2, 0.25, 0.33, 0.5, 0.75, 0.99])
    def test_every_admissible_margin_satisfies_the_rule(self, margin: float) -> None:
        guard = OutputGuard(safety_settings=Settings(margin))
        price = guard.calculate_safe_price({"floor_price": 100.0, "internal_cost": 100.0})
        assert holds(price, 100.0, 100.0, margin)


class TestCostAboveFloor:
    def test_a_cost_above_the_floor_still_yields_a_satisfying_price(self) -> None:
        """
        The substitute used to read only `floor`, so at cost > floor it produced
        a price the margin rule rejects — the guard refusing its own safe offer.
        """
        guard = OutputGuard(safety_settings=Settings(0.1))
        price = guard.calculate_safe_price({"floor_price": 100.0, "internal_cost": 120.0})
        assert holds(price, 100.0, 120.0, 0.1)
        assert price >= 120.0


class TestJitter:
    def test_the_price_is_stable_within_one_session(self) -> None:
        """
        Redrawing per decision would let a counterparty average the noise away
        over rounds. Keyed on request_id, it cannot.
        """
        guard = OutputGuard(safety_settings=Settings(0.1))
        ctx = {"floor_price": 100.0, "internal_cost": 100.0}
        prices = {guard.calculate_safe_price(ctx, request_id="sess-abc") for _ in range(5)}
        assert len(prices) == 1

    def test_the_price_differs_across_sessions(self) -> None:
        guard = OutputGuard(safety_settings=Settings(0.1))
        ctx = {"floor_price": 100.0, "internal_cost": 100.0}
        prices = {
            guard.calculate_safe_price(ctx, request_id=f"sess-{n}") for n in range(20)
        }
        assert len(prices) > 1

    def test_jitter_never_lowers_the_price(self) -> None:
        """
        psi survives jitter only because (1 + j) >= 1 and the rounding is a
        ceiling. A jitter that could subtract would reintroduce the whole bug.
        """
        guard = OutputGuard(safety_settings=Settings(0.1))
        ctx = {"floor_price": 100.0, "internal_cost": 100.0}
        base = guard.calculate_safe_price(ctx)
        for n in range(50):
            assert guard.calculate_safe_price(ctx, request_id=f"s-{n}") >= base

    def test_every_jitter_draw_satisfies_the_rule(self) -> None:
        guard = OutputGuard(safety_settings=Settings(0.1))
        for n in range(200):
            floor, cost = 100.0 + n, 90.0 + n
            price = guard.calculate_safe_price(
                {"floor_price": floor, "internal_cost": cost}, request_id=f"s-{n}"
            )
            assert holds(price, floor, cost, 0.1)
```

- [ ] **Step 2: Run and watch them fail**

Run: `$CORE uv run pytest core/tests/test_guard_safe_offer.py -v`
Expected: FAIL — the first test gets `111.11`, and the jitter tests get identical prices for every `request_id`.

- [ ] **Step 3: Rewrite the substitute in `engine.py`**

Add at the top of the imports:

```python
import hmac
import secrets
from decimal import ROUND_CEILING, Decimal
```

Replace the `_FLOOR_MARKUP` / `_DEFAULT_MARGIN` constants:

```python
# Markup floor for the substitute. Not operator-tunable: unlike
# min_profit_margin this is the shape of the fallback rather than a policy dial.
_FLOOR_MARKUP = Decimal("1.05")

# Used when the configured margin cannot be read or is out of range. Matches the
# default on SafetySettings, so a deployment that loses its setting behaves like
# one that never overrode it.
_DEFAULT_MARGIN = Decimal("0.1")

# Cent, as the quantum every emitted price is rounded to.
_CENT = Decimal("0.01")

# Upper bound on the multiplicative noise applied to a substitute price.
#
# Without it the substitute is a deterministic function of the hidden floor, and
# a counterparty who receives one inverts it exactly. This bounds the disclosure
# rather than closing it: the constant is public, so they still learn the floor
# to within 3%. Closing the channel outright means refusing instead of
# countering, which is a product decision taken the other way.
_SAFE_OFFER_JITTER = Decimal("0.03")

# Keyed on request_id so the noise is constant within a negotiation — redrawn
# per decision, a counterparty averages it away over rounds.
#
# Process-lifetime random rather than configured, because nothing needs to
# reproduce the price: the post-condition checks the value. So there is no
# setting to add, no fail-closed branch for a missing secret, and nothing to
# rotate. A restart mid-session reshuffles it, which only adds noise.
_JITTER_SECRET = secrets.token_bytes(32)
```

Add the helper beside `_numeric`:

```python
def _decimal(mapping: dict, key: str, default: Decimal = Decimal(0)) -> Decimal:
    """
    Read a money value as Decimal, tolerating a caller who did not send one.

    Via `str` rather than the float directly: Decimal(0.1) is
    0.1000000000000000055511151231257827, and money arithmetic that starts there
    ends somewhere a cent away.
    """
    value = mapping.get(key, None)
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        logger.warning("guard_unusable_numeric_input", key=key, value=repr(value))
        return default


def _jitter(request_id: str) -> Decimal:
    """
    Multiplicative noise in [0, _SAFE_OFFER_JITTER), stable for one request_id.

    An empty request_id yields zero rather than a random draw: a caller with no
    session to key on gets the deterministic price, and the absence is visible
    in the number rather than hidden behind noise nobody can reproduce.
    """
    if not request_id:
        return Decimal(0)
    digest = hmac.new(_JITTER_SECRET, request_id.encode("utf-8"), "sha256").digest()
    return _SAFE_OFFER_JITTER * Decimal(int.from_bytes(digest, "big")) / Decimal(2**256)
```

Replace `_configured_margin` and `calculate_safe_price`:

```python
    def _configured_margin(self) -> Decimal:
        """
        The configured minimum margin as Decimal, clamped to a range that keeps
        the substitute at or above the floor.

        A margin at or above 1.0 makes the formula undefined or negative. A
        margin below 0.0 is worse: floor/(1-(-0.5)) is floor/1.5, so a floor of
        1000 came back as a "safe" price of 666.67, and the substitute exists
        precisely to be the thing that cannot undercut the floor.
        """
        raw = getattr(self.settings, "min_profit_margin", None) if self.settings else None
        if raw is None:
            return _DEFAULT_MARGIN

        try:
            margin = Decimal(str(raw))
        except (TypeError, ValueError, ArithmeticError):
            logger.error("guard_margin_setting_unreadable_using_default", raw=raw)
            return _DEFAULT_MARGIN

        if not Decimal(0) <= margin < Decimal(1):
            logger.error("guard_margin_setting_out_of_range", margin=str(margin))
            return _DEFAULT_MARGIN

        return margin

    def calculate_safe_price(
        self, context: dict, reason: str = "", request_id: str = ""
    ) -> float:
        """
        The deterministic substitute, by the one strategy the rule set declares.

        Rounds UP. `round()` goes to the nearest cent, which for a margin
        substitute is toward breaching it half the time — at floor=100 and m=0.1
        it produced 111.11 for a required 111.1111..., and a lower price is a
        lower margin. A value that exists to be safe rounds toward the guarantee.

        Reads `internal_cost`, not just the floor: the margin rule is stated
        against cost, and where cost exceeds floor no price derived from the
        floor alone can satisfy it.

        `reason` is unused since the strategies collapsed. It stays in the
        signature because two call sites pass it positionally, and removing it
        is churn in a change that is already touching the arithmetic.
        """
        floor = _decimal(context, "floor_price")
        cost = _decimal(context, "internal_cost")
        margin = self._configured_margin()

        base = max(_FLOOR_MARKUP * floor, max(floor, cost) / (1 - margin))
        jittered = base * (1 + _jitter(request_id))
        return float(jittered.quantize(_CENT, rounding=ROUND_CEILING))
```

- [ ] **Step 4: Run the new tests and watch them pass**

Run: `$CORE uv run pytest core/tests/test_guard_safe_offer.py -v`
Expected: PASS, 8 tests.

- [ ] **Step 5: Run the whole guard and membrane suite**

Run: `$CORE uv run pytest core/tests/ -q -k "guard or membrane"`
Expected: some existing tests asserting the old `floor * 1.05` substitute now fail. Update each to the new value — the price is higher, and that is the fix, not a regression. Do **not** weaken an assertion to a range where an exact value is available; call `calculate_safe_price` with no `request_id` in tests that need determinism.

- [ ] **Step 6: Commit**

```bash
git add core/src/aura_hive/hive/proteins/guard/engine.py core/tests/
git commit -m "fix(guard): round the substitute price up, and toward the margin rule

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: ψ predicates, `check_postcondition`, `GuardUnavailable`

**Files:**
- Modify: `core/src/aura_hive/hive/proteins/guard/engine.py`, `core/src/aura_hive/hive/proteins/guard/skill.py`
- Test: `core/tests/test_guard_postcondition.py` (create), `core/tests/test_guard_lookup_failure.py`

**Interfaces:**
- Consumes: `Ruleset.postcondition` (Task 2), `_decimal` (Task 3).
- Produces: `GuardUnavailable(message: str, code: str = "GUARD_UNAVAILABLE")`; `PostconditionResult(holds: bool, failed_clause: str | None)`; `OutputGuard.check_postcondition(self, emission: dict, context: dict) -> PostconditionResult`; guard intent `"check_postcondition"` taking `{"emission": {...}, "context": {...}}` and returning an `Observation` whose metadata carries `{"holds": bool, "failed_clause": str}`.

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_guard_postcondition.py`:

```python
"""
What the guard guarantees about the value it lets out.

The gates judge what the model proposed. Nothing judged what the Membrane
substituted, and that gap is how a price below the minimum margin shipped under
a receipt that verified: G2 fired on the proposal, short-circuited G4, and the
substitute was emitted unexamined.
"""

import pytest
from aura_hive.hive.proteins.guard.engine import (
    GuardUnavailable,
    OutputGuard,
    SafetyViolation,
)


class Settings:
    def __init__(self, margin: float = 0.1) -> None:
        self.min_profit_margin = margin


CONTEXT = {"floor_price": 100.0, "internal_cost": 100.0}


class TestClauses:
    def test_a_satisfying_price_holds(self) -> None:
        guard = OutputGuard(safety_settings=Settings())
        result = guard.check_postcondition({"price": 111.12}, CONTEXT)
        assert result.holds
        assert result.failed_clause is None

    def test_a_non_positive_price_names_its_clause(self) -> None:
        guard = OutputGuard(safety_settings=Settings())
        result = guard.check_postcondition({"price": 0.0}, CONTEXT)
        assert not result.holds
        assert result.failed_clause == "PSI_PRICE_POSITIVE"

    def test_a_price_below_the_floor_names_its_clause(self) -> None:
        guard = OutputGuard(safety_settings=Settings())
        result = guard.check_postcondition({"price": 99.99}, CONTEXT)
        assert not result.holds
        assert result.failed_clause == "PSI_ABOVE_FLOOR"

    def test_a_price_below_the_margin_names_its_clause(self) -> None:
        """
        105.00 is above the floor and was what the old floor-markup substitute
        emitted. It breaches the margin rule, and nothing caught it.
        """
        guard = OutputGuard(safety_settings=Settings())
        result = guard.check_postcondition({"price": 105.0}, CONTEXT)
        assert not result.holds
        assert result.failed_clause == "PSI_MIN_MARGIN"

    def test_clauses_are_reported_in_declared_order(self) -> None:
        """
        A price failing two clauses reports the first, so the reason a decision
        was stopped does not depend on evaluation accidents.
        """
        guard = OutputGuard(safety_settings=Settings())
        result = guard.check_postcondition({"price": -5.0}, CONTEXT)
        assert result.failed_clause == "PSI_PRICE_POSITIVE"


class TestTheSubstituteSatisfiesIt:
    @pytest.mark.parametrize("margin", [0.0, 0.05, 0.1, 0.2, 0.33, 0.5, 0.9])
    @pytest.mark.parametrize("cost", [10.0, 99.99, 100.0, 100.01, 250.0])
    def test_the_guards_own_substitute_always_holds(
        self, margin: float, cost: float
    ) -> None:
        """
        The regression for the whole exercise. If this ever fails, the guard is
        refusing the price it computed as safe.
        """
        guard = OutputGuard(safety_settings=Settings(margin))
        context = {"floor_price": 100.0, "internal_cost": cost}
        for n in range(10):
            price = guard.calculate_safe_price(context, request_id=f"s-{n}")
            assert guard.check_postcondition({"price": price}, context).holds


class TestUnavailableIsNotAViolation:
    def test_guard_unavailable_is_not_a_safety_violation(self) -> None:
        """
        A question the guard could not answer is not a rule it answered against.
        A caller catching one must not silently catch the other.
        """
        assert not issubclass(GuardUnavailable, SafetyViolation)
        assert not issubclass(SafetyViolation, GuardUnavailable)

    def test_it_carries_a_code(self) -> None:
        error = GuardUnavailable("persistence is down", code="SANCTIFICATION_UNAVAILABLE")
        assert error.code == "SANCTIFICATION_UNAVAILABLE"
```

- [ ] **Step 2: Run and watch them fail**

Run: `$CORE uv run pytest core/tests/test_guard_postcondition.py -v`
Expected: FAIL — `ImportError: cannot import name 'GuardUnavailable'`.

- [ ] **Step 3: Add the exception and the result type to `engine.py`**

Beside `SafetyViolation`:

```python
class GuardUnavailable(Exception):
    """
    Raised when the guard could not establish a verdict at all.

    A sibling of SafetyViolation rather than a subclass. A rule judging against
    a decision and a judgment that never happened send an operator to different
    places — one to the offer, one to the dependency that is down — and a caller
    that catches one must not silently catch the other. AR4SI calls this tier
    "none"; its -1 is "a verifier malfunction occurred".
    """

    def __init__(self, message: str, code: str = "GUARD_UNAVAILABLE") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PostconditionResult:
    """Whether the emitted value satisfies psi, and which clause stopped it."""

    holds: bool
    failed_clause: str | None
```

- [ ] **Step 4: Add the clause predicates and the walker**

In `OutputGuard`, beside the gate predicates:

```python
    # Clause id -> the predicate that decides it. The ids are the contract with
    # ruleset.yaml exactly as the gate ids are: `validate_against` refuses to
    # construct if the two drift in either direction.
    #
    # Every one of these reads the EMITTED value. That is the whole distinction
    # from the gates, which read what the model proposed.
    def _clause_price_positive(self, emission: dict, context: dict) -> bool:
        return _decimal(emission, "price") > 0

    def _clause_above_floor(self, emission: dict, context: dict) -> bool:
        return _decimal(emission, "price") >= _decimal(context, "floor_price")

    def _clause_min_margin(self, emission: dict, context: dict) -> bool:
        # Multiplicative, not (price - cost)/price >= m. The ratio form is not
        # decidable in binary floats on money: where the price is exactly right,
        # it evaluates to 0.09999999999999995 against 0.1. psi is fail-closed,
        # so that artefact would cost a live negotiation.
        price = _decimal(emission, "price")
        cost = _decimal(context, "internal_cost")
        return price * (1 - self._configured_margin()) >= cost

    @classmethod
    def clause_ids(cls) -> tuple[str, ...]:
        """The post-condition clauses this engine can evaluate."""
        return ("PSI_PRICE_POSITIVE", "PSI_ABOVE_FLOOR", "PSI_MIN_MARGIN")

    def _clause_predicate(self, clause_id: str) -> Callable[[dict, dict], bool]:
        return {
            "PSI_PRICE_POSITIVE": self._clause_price_positive,
            "PSI_ABOVE_FLOOR": self._clause_above_floor,
            "PSI_MIN_MARGIN": self._clause_min_margin,
        }[clause_id]

    def check_postcondition(self, emission: dict, context: dict) -> PostconditionResult:
        """
        Whether what is about to be sent satisfies what the rule set guarantees.

        Walked in declared order and stopped at the first failure, so the reason
        a decision was held back does not depend on evaluation accidents.

        A raising predicate is a failure, not an exception to propagate: a
        post-condition that could not be evaluated has not been established, and
        the emission must not proceed on the strength of a crash.
        """
        for clause in self.ruleset.postcondition.clauses:
            try:
                held = self._clause_predicate(clause.id)(emission, context)
            except Exception as exc:
                logger.error(
                    "guard_postcondition_unevaluable", clause=clause.id, error=str(exc)
                )
                return PostconditionResult(holds=False, failed_clause=clause.id)
            if not held:
                logger.warning("guard_postcondition_failed", clause=clause.id)
                return PostconditionResult(holds=False, failed_clause=clause.id)

        return PostconditionResult(holds=True, failed_clause=None)
```

Remove the placeholder `clause_ids` added in Task 2 Step 5 if it is still present as a duplicate.

- [ ] **Step 5: Run the tests and watch them pass**

Run: `$CORE uv run pytest core/tests/test_guard_postcondition.py -v`
Expected: PASS.

- [ ] **Step 6: Expose it on the protein and reclassify the lookup failure**

In `core/src/aura_hive/hive/proteins/guard/skill.py`, register the intent in the dispatch table beside `"validate_decision"`:

```python
            "check_postcondition": self._check_postcondition,
```

and add the handler:

```python
    async def _check_postcondition(self, params: dict[str, Any]) -> Observation:
        assert self.provider is not None
        result = self.provider.check_postcondition(
            params.get("emission", {}), params.get("context", {})
        )
        return Observation(
            success=True,
            metadata=make_struct(
                {"holds": result.holds, "failed_clause": result.failed_clause or ""}
            ),
        )
```

In `_wallet_is_sanctified`, change the raise from `SafetyViolation` to `GuardUnavailable`, keeping the message and code unchanged, and update the import.

- [ ] **Step 7: Update the lookup-failure tests**

`core/tests/test_guard_lookup_failure.py` asserts `SafetyViolation` for the sanctification path. Change those expectations to `GuardUnavailable`. The `code_of(obs) == "SANCTIFICATION_UNAVAILABLE"` assertions stay as they are.

- [ ] **Step 8: Run the guard suite**

Run: `$CORE uv run pytest core/tests/ -q -k guard`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add core/src/aura_hive/hive/proteins/guard/ core/tests/
git commit -m "feat(guard): check the post-condition, and separate unavailable from violated

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Membrane checks ψ on both paths

**Files:**
- Modify: `core/src/aura_hive/hive/membrane/main.py`
- Test: `core/tests/test_membrane_postcondition.py` (create)

**Interfaces:**
- Consumes: guard intent `"check_postcondition"` (Task 4), `DECISION_OUTCOME_UNAVAILABLE` (Task 1).
- Produces: `_Verdict` records `DECISION_OUTCOME_UNAVAILABLE` with gate `POSTCONDITION_VIOLATION`; a failing ψ emits a rejection Intent and never the offending price.

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_membrane_postcondition.py`.

> The helpers below are **module-level factories, not pytest fixtures** — that is the style `core/tests/test_membrane_derivation.py` uses, and the registry keys skills by name (`registry.register(skill.get_name(), skill)`), so there is no `membrane.registry.guard` attribute to reach through. A test that needs a stubbed predicate builds the `OutputGuard` itself and passes it to `bind`. Each test gets a fresh Membrane, registry and guard, because anything surviving between them is state a verifier does not have.

```python
"""
The post-condition, checked where the value actually leaves.

Gates judge the model's proposal. Before this, nothing judged the Membrane's
substitute, so a below-margin override shipped under a receipt that verified.
"""

import pytest
from aura_core import SkillRegistry, make_struct
from aura_core_gen.aura.core.v1 import (
    ActionType,
    Context,
    DecisionOutcome,
    HiveContextData,
    Intent,
    NegotiationIntent,
)
from aura_hive.hive.membrane.main import HiveMembrane
from aura_hive.hive.proteins.guard.engine import OutputGuard
from aura_hive.hive.proteins.guard.skill import GuardSkill

FLOOR = 1000.0
COST = 777.0


class _Safety:
    min_profit_margin = 0.10
    ui_trigger_price = 100000.0
    trade_risk_threshold = 0.10


def guarded_membrane(guard: OutputGuard | None = None) -> HiveMembrane:
    """A Membrane over a real guard, optionally one the caller has tampered with."""
    registry = SkillRegistry()
    skill = GuardSkill()
    skill.bind(_Safety(), guard or OutputGuard(safety_settings=_Safety()))
    registry.register(skill.get_name(), skill)
    return HiveMembrane(registry=registry)


def negotiation_context(request_id: str = "") -> Context:
    """
    Floor and cost live in metadata, as the Membrane reads them.

    The `hive` oneof is populated because the substitute price keys its jitter
    on `request_id`, and the existing helpers in test_membrane_derivation.py
    build a metadata-only Context where that field does not exist.
    """
    return Context(
        metadata=make_struct(
            {"floor_price": str(FLOOR), "internal_cost": str(COST)}
        ),
        hive=HiveContextData(request_id=request_id),
    )


def counter_intent(price: float) -> Intent:
    return Intent(
        action=ActionType.ACTION_TYPE_COUNTER,
        reasoning="LLM reasoning",
        negotiation=NegotiationIntent(price=price, message="Here is my offer"),
    )


class TestBothPaths:
    @pytest.mark.asyncio
    async def test_a_passing_decision_is_checked_too(self) -> None:
        """
        Checking only the override path would miss a broken gate on the pass
        path: a predicate stubbed to True lets a bad proposal through untouched,
        and psi is the only thing left that would notice.
        """
        guard = OutputGuard(safety_settings=_Safety())
        guard._gate_floor_violation = lambda decision, context: True  # type: ignore[method-assign]
        membrane = guarded_membrane(guard)

        result = await membrane.inspect_outbound(
            counter_intent(price=1.0), negotiation_context()
        )

        assert result.receipt.outcome == DecisionOutcome.DECISION_OUTCOME_UNAVAILABLE
        assert result.receipt.outcome_gate == "POSTCONDITION_VIOLATION"

    @pytest.mark.asyncio
    async def test_the_override_substitute_is_checked(self) -> None:
        """
        The regression for the found bug. A substitute that breaches the margin
        rule must not leave, even though the gates were right to stop the
        proposal that caused it. 1050.00 is floor * 1.05 — what the old strategy
        produced, and 0.26 below the margin rule at a cost of 777.
        """
        guard = OutputGuard(safety_settings=_Safety())
        guard.calculate_safe_price = lambda *args, **kwargs: 800.0  # type: ignore[method-assign]
        membrane = guarded_membrane(guard)

        result = await membrane.inspect_outbound(
            counter_intent(price=500.0), negotiation_context()
        )

        assert result.receipt.outcome == DecisionOutcome.DECISION_OUTCOME_UNAVAILABLE
        assert result.action == ActionType.ACTION_TYPE_REJECT

    @pytest.mark.asyncio
    async def test_a_satisfying_override_still_emits(self) -> None:
        membrane = guarded_membrane()

        result = await membrane.inspect_outbound(
            counter_intent(price=500.0), negotiation_context()
        )

        assert result.receipt.outcome == DecisionOutcome.DECISION_OUTCOME_OVERRIDE
        assert result.negotiation.price >= 1111.12


class TestNothingLeaks:
    @pytest.mark.asyncio
    async def test_the_offending_price_never_reaches_the_emission(self) -> None:
        guard = OutputGuard(safety_settings=_Safety())
        guard.calculate_safe_price = lambda *args, **kwargs: 800.0  # type: ignore[method-assign]
        membrane = guarded_membrane(guard)

        result = await membrane.inspect_outbound(
            counter_intent(price=500.0), negotiation_context()
        )

        assert "800" not in str(result.to_dict())
```

- [ ] **Step 2: Run and watch it fail**

Run: `$CORE uv run pytest core/tests/test_membrane_postcondition.py -v`
Expected: FAIL — the override path returns `DECISION_OUTCOME_OVERRIDE` with price `105.0`.

- [ ] **Step 3: Add the outcome constant and the check**

At the top of `membrane/main.py`, beside `_OVERRIDE`:

```python
_UNAVAILABLE = DecisionOutcome.DECISION_OUTCOME_UNAVAILABLE
```

Add the method to `HiveMembrane`:

```python
    async def _postcondition_holds(
        self, price: float, guard_context: dict[str, Any], verdict: _Verdict
    ) -> bool:
        """
        Whether the value about to be sent satisfies what the rule set promises.

        Fails closed on every path that is not an explicit pass, including a
        guard that could not be reached: a post-condition nobody evaluated has
        not been established, and this is the last checkpoint before the wire.
        """
        if not self.registry:
            return True

        try:
            obs = await self.registry.execute(
                "guard",
                "check_postcondition",
                {"emission": {"price": price}, "context": guard_context},
            )
        except Exception as exc:
            logger.error("membrane_postcondition_unreachable", error=str(exc))
            verdict.record(_UNAVAILABLE, "POSTCONDITION_VIOLATION")
            return False

        meta = obs.metadata.to_dict() if obs.metadata is not None else {}
        if obs.success and bool(meta.get("holds")):
            return True

        logger.error(
            "membrane_postcondition_violated",
            clause=str(meta.get("failed_clause") or ""),
            price=price,
        )
        verdict.record(_UNAVAILABLE, "POSTCONDITION_VIOLATION")
        return False
```

- [ ] **Step 4: Call it on the pass path**

In `inspect_outbound`, replace the final `return await self._finish(claim, decision, verdict)` that follows a successful guard call:

```python
        price = neg_intent.price if neg_intent else 0.0
        if not await self._postcondition_holds(price, guard_context, verdict):
            return await self._finish(
                claim, _replacing(decision, _rejection()), verdict
            )

        return await self._finish(claim, decision, verdict)
```

Add the helper beside `_replacing`:

```python
def _rejection() -> Intent:
    """
    What leaves when the post-condition did not hold.

    Deliberately carries no price and no reason the counterparty can read: the
    decision was stopped because we could not establish our own guarantee, and
    saying which clause failed would describe the policy boundary to the party
    the policy exists to hold at arm's length.
    """
    return Intent(
        action=ActionType.ACTION_TYPE_REJECT,
        reasoning="Membrane: post-condition not established",
    )
```

- [ ] **Step 5: Call it on the override path**

In `_override_with_safe_offer`, after `rounded_price` is computed and before the replacement Intent is built:

```python
        if not await self._postcondition_holds(rounded_price, guard_context, verdict):
            return await self._finish(
                claim or original, _replacing(original, _rejection()), verdict
            )
```

`_override_with_safe_offer` does not currently receive `guard_context`. Add it as a parameter and thread it from both call sites; the FAILURE_RECOVERY site builds it the same way the guard block does:

```python
guard_context = {"floor_price": floor_price, "internal_cost": internal_cost}
```

- [ ] **Step 6: Run the test and watch it pass**

Run: `$CORE uv run pytest core/tests/test_membrane_postcondition.py -v`
Expected: PASS.

- [ ] **Step 7: Run the core suite**

Run: `$CORE uv run pytest core/tests/ -q`
Expected: PASS. Tests asserting the old `105.0` substitute fail here if Task 3 Step 5 missed any — fix them the same way.

- [ ] **Step 8: Commit**

```bash
git add core/src/aura_hive/hive/membrane/main.py core/tests/
git commit -m "fix(membrane): judge the value that leaves, not only the one proposed

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Session-stable jitter and neutral override messages

**Files:**
- Modify: `core/src/aura_hive/hive/membrane/main.py:545-560` (DLP message), `:648-660` (override message)
- Test: `core/tests/test_membrane_override_message.py` (create)

**Interfaces:**
- Consumes: `calculate_safe_price(context, reason, request_id)` (Task 3).
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_membrane_override_message.py`:

```python
"""
What the counterparty reads when the guard intervened.

Withholding the receipt's `outcome` field does nothing while the message says
"I've reached my final limit": the override announced itself in plain English,
and the substitute price is a function of the hidden floor. The message is one
half of that; the jitter in the price is the other.
"""

import pytest
from aura_hive.hive.membrane.main import HiveMembrane

from .test_membrane_postcondition import (
    counter_intent,
    guarded_membrane,
    negotiation_context,
)


class TestTheMessageDoesNotAnnounceTheGuard:
    @pytest.mark.asyncio
    async def test_no_finality_language(self) -> None:
        membrane = guarded_membrane()
        result = await membrane.inspect_outbound(
            counter_intent(price=500.0), negotiation_context()
        )
        message = result.negotiation.message.lower()
        for tell in ("final limit", "best offer", "cannot disclose", "membrane"):
            assert tell not in message

    @pytest.mark.asyncio
    async def test_a_price_is_still_stated(self) -> None:
        """
        Neutral is not silent. The counterparty needs the number; what they must
        not get is a label saying which rule produced it.
        """
        membrane = guarded_membrane()
        result = await membrane.inspect_outbound(
            counter_intent(price=500.0), negotiation_context()
        )
        assert f"{result.negotiation.price:.2f}" in result.negotiation.message


class TestJitterIsSessionStable:
    @pytest.mark.asyncio
    async def test_repeated_rounds_return_the_same_price(self) -> None:
        """
        Redrawn per decision, a counterparty averages the noise away over rounds
        and recovers the floor anyway.
        """
        prices = set()
        for _ in range(5):
            membrane = guarded_membrane()
            result = await membrane.inspect_outbound(
                counter_intent(price=500.0), negotiation_context(request_id="sess-abc")
            )
            prices.add(result.negotiation.price)
        assert len(prices) == 1

    @pytest.mark.asyncio
    async def test_a_different_session_returns_a_different_price(self) -> None:
        prices = set()
        for n in range(20):
            membrane = guarded_membrane()
            result = await membrane.inspect_outbound(
                counter_intent(price=500.0), negotiation_context(request_id=f"r-{n}")
            )
            prices.add(result.negotiation.price)
        assert len(prices) > 1
```

The helpers are imported from `test_membrane_postcondition.py` rather than duplicated. If `core/tests/` has no `__init__.py`, add the three factories to a shared `core/tests/membrane_helpers.py` and import from there instead — do not copy them into both files, or the two copies drift.

- [ ] **Step 2: Run and watch it fail**

Run: `$CORE uv run pytest core/tests/test_membrane_override_message.py -v`
Expected: FAIL — the message contains "final limit", and every session returns the same price.

- [ ] **Step 3: Thread `request_id` into the substitute**

In `inspect_outbound`, read it from the context beside `floor_price`:

```python
        hive = betterproto.which_one_of(context, "data")[1]
        request_id = getattr(hive, "request_id", "") if hive else ""
```

Pass it to both `get_safe_price` registry calls as `"request_id": request_id`, and have `proteins/guard/skill.py`'s `_get_safe_price` handler forward it to `calculate_safe_price`.

- [ ] **Step 4: Neutralise the messages**

Replace the override message at `:655`:

```python
            negotiation=NegotiationIntent(
                # Deliberately indistinguishable from an ordinary counter. The
                # old text announced "I've reached my final limit", which told
                # the counterparty a guard had fired — and since the substitute
                # is a function of the hidden floor, that is most of the way to
                # inverting it. This reduces distinguishability rather than
                # removing it: a template still reads differently from the
                # model's own prose.
                price=rounded_price,
                message=f"My counter-offer for this item is ${rounded_price:.2f}.",
            ),
```

Replace the DLP sanitised message at `:554` with the same neutral phrasing, keeping the model's price:

```python
                    message=f"My counter-offer for this item is ${neg_intent.price:.2f}."
                    if neg_intent
                    else "",
```

Leave `reasoning` and `thought` alone — they are internal and never reach a client.

- [ ] **Step 5: Run the test and watch it pass**

Run: `$CORE uv run pytest core/tests/test_membrane_override_message.py -v`
Expected: PASS.

- [ ] **Step 6: Run the core suite**

Run: `$CORE uv run pytest core/tests/ -q`
Expected: PASS. Any test asserting the old message text fails; update it — the old text is the defect.

- [ ] **Step 7: Commit**

```bash
git add core/src/aura_hive/hive/ core/tests/
git commit -m "fix(membrane): stop the substitute price announcing which rule produced it

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: Receipt V2 — versions, binding fields, content fields

**Files:**
- Modify: `core/src/aura_hive/hive/membrane/receipt.py`, `core/src/aura_hive/hive/membrane/main.py`
- Test: `core/tests/test_receipt.py`

**Interfaces:**
- Consumes: the four proto fields (Task 1).
- Produces: `RECEIPT_VERSION == "AURA-RECEIPT-V2-UNSIGNED"`; `SIGNED_VERSION == "AURA-RECEIPT-V2"`; `mint(claim, emission, outcome, outcome_gate="", ruleset_version="", derivation=None, issued_at="", decision_id="", request_id="", override_scope="") -> DecisionReceipt`; `_content_fields` in the eleven-line order below.

- [ ] **Step 1: Write the failing tests**

Add to `core/tests/test_receipt.py`:

```python
class TestVersionNames:
    def test_the_number_is_the_generation_and_the_suffix_is_attestation(self) -> None:
        """
        V0-UNSIGNED and V1 encoded attestation in the generation number, so the
        two looked like successive formats when they were one format signed and
        unsigned.
        """
        assert RECEIPT_VERSION == "AURA-RECEIPT-V2-UNSIGNED"
        assert SIGNED_VERSION == "AURA-RECEIPT-V2"

    def test_the_old_formats_are_refused_not_read(self) -> None:
        """
        No persisted receipts exist, so V0/V1 are deleted rather than supported.
        A verifier that best-effort reads a format it does not know is the
        downgrade the version string exists to prevent.
        """
        for old in ("AURA-RECEIPT-V0-UNSIGNED", "AURA-RECEIPT-V1"):
            result = verify(DecisionReceipt(version=old))
            assert not result.ok
            assert any("unknown receipt version" in f for f in result.failures)


class TestBinding:
    def test_the_binding_fields_are_signed(self) -> None:
        """
        Binding that is not in the content fields is decorative: anyone can
        rewrite it and the signature still verifies.
        """
        base = mint(
            counter(100.0), counter(100.0), DecisionOutcome.DECISION_OUTCOME_EMIT,
            issued_at="2026-08-11T10:00:00Z", decision_id="d-1", request_id="r-1",
        )
        for field, value in (
            ("issued_at", "2026-08-11T11:00:00Z"),
            ("decision_id", "d-2"),
            ("request_id", "r-2"),
        ):
            altered = replace(base, **{field: value})
            assert _prefix(altered) != _prefix(base), field

    def test_two_sessions_do_not_share_a_receipt(self) -> None:
        """
        Same item, same price, different deals produced a byte-identical
        receipt, signature included — a receipt about an equivalence class of
        decisions rather than one decision.
        """
        one = mint(counter(100.0), counter(100.0), DecisionOutcome.DECISION_OUTCOME_EMIT,
                   issued_at="2026-08-11T10:00:00Z", decision_id="d-1", request_id="r-1")
        two = mint(counter(100.0), counter(100.0), DecisionOutcome.DECISION_OUTCOME_EMIT,
                   issued_at="2026-08-11T10:00:00Z", decision_id="d-2", request_id="r-2")
        assert one.canonical_prefix != two.canonical_prefix
```

Add `from dataclasses import replace` to the imports.

- [ ] **Step 2: Run and watch them fail**

Run: `$CORE uv run pytest core/tests/test_receipt.py -v -k "VersionNames or Binding"`
Expected: FAIL — `RECEIPT_VERSION` is still `AURA-RECEIPT-V0-UNSIGNED`.

- [ ] **Step 3: Rename the versions**

```python
RECEIPT_VERSION = "AURA-RECEIPT-V2-UNSIGNED"
SIGNED_VERSION = "AURA-RECEIPT-V2"
```

Update the module docstring: the number is the format generation, the suffix is attestation; V0 and V1 are gone rather than deprecated because no persisted receipts exist.

- [ ] **Step 4: Extend the content fields**

```python
def _content_fields(receipt: DecisionReceipt) -> str:
    """
    The fields the prefix and the signature commit to, in fixed order.

    Order is part of the canonical form: reordering produces a different prefix
    and fails verification, which is intended rather than inconvenient.

    `issued_at`, `decision_id` and `request_id` are here rather than alongside
    because binding that is not signed is decorative — anyone can rewrite it.
    """
    derivation = receipt.derivation or DecisionDerivation()
    return "\n".join(
        [
            receipt.version,
            receipt.issued_at,
            receipt.decision_id,
            receipt.request_id,
            receipt.claim_hash,
            receipt.ruleset_version,
            derivation.derivation_hash,
            receipt.emission_hash,
            decision_outcome_name(receipt.outcome),
            receipt.outcome_gate,
            receipt.override_scope,
        ]
    )
```

- [ ] **Step 5: Extend `mint`**

```python
def mint(
    claim: Intent,
    emission: Intent,
    outcome: DecisionOutcome,
    outcome_gate: str = "",
    ruleset_version: str = "",
    derivation: DecisionDerivation | None = None,
    issued_at: str = "",
    decision_id: str = "",
    request_id: str = "",
    override_scope: str = "",
) -> DecisionReceipt:
    """
    Build the receipt for one decision.

    `claim` is what the Transformer proposed; `emission` is what is being sent.
    Passing the same Intent for both is correct when the Membrane changed
    nothing — the two hashes agreeing is then a fact a reader can check.
    """
    receipt = DecisionReceipt(
        version=RECEIPT_VERSION,
        claim_hash=claim_digest(claim),
        ruleset_version=ruleset_version,
        emission_hash=claim_digest(emission),
        outcome=outcome,
        outcome_gate=outcome_gate,
        issued_at=issued_at,
        decision_id=decision_id,
        request_id=request_id,
        override_scope=override_scope,
    )
    if derivation is not None:
        receipt.derivation = derivation

    receipt.canonical_prefix = _prefix(receipt)
    return receipt
```

- [ ] **Step 6: Stamp the fields in the Membrane**

Add to `_Verdict`:

```python
    override_scope: str = ""
```

In `_mint_for`, pass the four new arguments. `issued_at` is `datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")`; `decision_id` is `emission.identifier`; `request_id` comes from the context read added in Task 6. `_mint_for` needs `request_id` as a parameter — thread it from `_finish`.

Set `override_scope` where the override is recorded: `"prose"` at the DLP site, `"value"` at the safe-offer site.

- [ ] **Step 7: Run the receipt suite**

Run: `$CORE uv run pytest core/tests/test_receipt.py core/tests/test_receipt_transport.py -v`
Expected: PASS after updating fixtures that hardcode the old version strings.

- [ ] **Step 8: Commit**

```bash
git add core/src/aura_hive/hive/membrane/ core/tests/
git commit -m "feat(receipt): V2 binds a receipt to the decision it describes

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: `verify` — computed unverifiable, `override_scope` both ways, required derivation

**Files:**
- Modify: `core/src/aura_hive/hive/membrane/receipt.py`
- Test: `core/tests/test_receipt.py`

**Interfaces:**
- Consumes: Task 7's format.
- Produces: `VerificationResult.unverifiable` computed per receipt and always containing `"emission_content"`; `_PROSE_ONLY_GATES` deleted.

- [ ] **Step 1: Write the failing tests**

```python
class TestVerifyNamesWhatItCannotCheck:
    def test_emission_content_is_always_unverifiable(self) -> None:
        """
        verify() receives the receipt and never the Intent, so it cannot learn
        that claim_hash digests anything real. Saying so is the honest report;
        a verifier answering "ok" while silently skipping teaches its consumer
        to rely on a guarantee nobody made.
        """
        receipt = mint(counter(100.0), counter(100.0), DecisionOutcome.DECISION_OUTCOME_EMIT)
        result = verify(receipt)
        assert result.ok
        assert "emission_content" in result.unverifiable

    def test_signature_is_listed_only_when_absent(self) -> None:
        unsigned = mint(counter(100.0), counter(100.0), DecisionOutcome.DECISION_OUTCOME_EMIT)
        assert "signature" in verify(unsigned).unverifiable


class TestOverrideScope:
    def test_a_value_override_with_equal_hashes_fails(self) -> None:
        receipt = mint(
            counter(100.0), counter(100.0), DecisionOutcome.DECISION_OUTCOME_OVERRIDE,
            override_scope="value",
        )
        assert not verify(receipt).ok

    def test_a_prose_override_with_equal_hashes_passes(self) -> None:
        receipt = mint(
            counter(100.0), counter(100.0), DecisionOutcome.DECISION_OUTCOME_OVERRIDE,
            override_scope="prose",
        )
        assert verify(receipt).ok

    def test_a_prose_override_with_differing_hashes_fails(self) -> None:
        """
        Prose is defined not to reach the decidable content, so a prose-scoped
        override whose digests differ describes something that cannot happen.
        This direction was never checked.
        """
        receipt = mint(
            counter(100.0), counter(105.0), DecisionOutcome.DECISION_OUTCOME_OVERRIDE,
            override_scope="prose",
        )
        assert not verify(receipt).ok


class TestDerivationIsRequired:
    def test_a_judged_decision_must_carry_its_derivation(self) -> None:
        """
        The witness was optional and unenforced: a receipt could claim a rule set
        judged it and record nothing about how.
        """
        receipt = mint(
            counter(100.0), counter(100.0), DecisionOutcome.DECISION_OUTCOME_EMIT,
            ruleset_version="guard/negotiation@2.0.0+abcdef0123456789",
        )
        result = verify(receipt)
        assert not result.ok
        assert any("derivation" in f for f in result.failures)

    def test_an_unavailable_outcome_needs_none(self) -> None:
        receipt = mint(
            counter(100.0), counter(100.0),
            DecisionOutcome.DECISION_OUTCOME_UNAVAILABLE,
            outcome_gate="POSTCONDITION_VIOLATION",
        )
        assert verify(receipt).ok
```

- [ ] **Step 2: Run and watch them fail**

Run: `$CORE uv run pytest core/tests/test_receipt.py -v -k "Unverifiable or OverrideScope or DerivationIsRequired"`
Expected: FAIL.

- [ ] **Step 3: Delete `_PROSE_ONLY_GATES` and rewrite the checks**

Remove the constant. In `verify`, replace the override block:

```python
    changed = receipt.claim_hash != receipt.emission_hash

    if receipt.outcome == DecisionOutcome.DECISION_OUTCOME_OVERRIDE:
        # Checked in both directions. A value-scoped override that left the
        # digests alike describes a substitution that did not happen; a
        # prose-scoped one whose digests differ describes prose reaching the
        # decidable content, which prose is defined not to do.
        if receipt.override_scope == "prose" and changed:
            failures.append(
                "override scoped to prose but the claim and emission digests differ"
            )
        elif receipt.override_scope != "prose" and not changed:
            failures.append(
                "override recorded but claim and emission hash alike, and the "
                f"scope is {receipt.override_scope or 'unset'!r} rather than 'prose'"
            )

    if receipt.outcome == DecisionOutcome.DECISION_OUTCOME_EMIT and changed:
        failures.append("emit recorded but the emission does not match the claim")

    # A rule set judged this decision, so it must say how. The witness used to
    # be optional: a receipt could name the rules and record nothing about their
    # application, and verify would pass it.
    derivation_missing = not (derivation.gate_sequence or derivation.derivation_hash)
    judged = receipt.outcome in (
        DecisionOutcome.DECISION_OUTCOME_EMIT,
        DecisionOutcome.DECISION_OUTCOME_OVERRIDE,
    )
    if judged and receipt.ruleset_version and derivation_missing:
        failures.append(
            f"receipt cites rule set {receipt.ruleset_version!r} but carries no derivation"
        )
```

- [ ] **Step 4: Compute `unverifiable`**

```python
    # Computed, not a constant. A caller reads what this verifier could not
    # establish about THIS receipt, so the list stays true as fields land.
    unverifiable: list[str] = []
    if not attested:
        unverifiable.append("signature")
    # Always. verify() is handed the receipt and never the Intent, so it cannot
    # establish that claim_hash digests the decision the model actually made.
    # Naming it is the difference between a verifier and a rubber stamp.
    unverifiable.append("emission_content")
    if not receipt.issued_at:
        unverifiable.append("freshness")
    # Still unbuilt; see DECISION_RECEIPT.md §3.1 and §3.5.
    unverifiable.extend(["premises", "policy"])
```

- [ ] **Step 5: Run the tests and watch them pass**

Run: `$CORE uv run pytest core/tests/test_receipt.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full core suite**

Run: `$CORE uv run pytest core/tests/ -q` and `make lint`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add core/src/aura_hive/hive/membrane/receipt.py core/tests/test_receipt.py
git commit -m "feat(receipt): say what verify could not check, and require the witness

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: Currency reaches the claim

> **Note for the implementer:** the spec describes this as resolving a doc/code divergence, which understated it. `NegotiateRequest.currency_code` exists at the edge and the gateway forwards it (`api-gateway/src/api_gateway/main.py:290`), but `NegotiationOffer` carries only `bid_amount`, `reputation` and `agent_did`, and `NegotiationIntent` carries no currency at all — it is dropped before the Intent exists. This task threads it through. Currency is a property of the request, not of the model's decision, so the Membrane stamps it from context; the Transformer is not touched and the model is never asked about it.

**Files:**
- Modify: `proto/aura/core/v1/metabolism.proto` (`NegotiationOffer`, `NegotiationIntent`), `core/src/aura_hive/hive/aggregator/main.py:149,227,293,365`, `core/src/aura_hive/hive/membrane/main.py`, `core/src/aura_hive/hive/membrane/receipt.py`
- Test: `core/tests/test_receipt.py`

**Interfaces:**
- Consumes: Task 7's `canonical_claim`.
- Produces: `NegotiationOffer.currency_code` (field 4), `NegotiationIntent.currency_code` (field 6); `canonical_claim` renders `action=…;item=…;price=…;currency=…`.

- [ ] **Step 1: Write the failing test**

```python
class TestCurrencyIsPartOfTheClaim:
    def test_two_currencies_are_two_claims(self) -> None:
        """
        The same number in two denominations is not the same decision, and the
        doc has promised this field since §3.2 while the code omitted it.
        """
        eur = counter(100.0)
        eur.negotiation.currency_code = "EUR"
        usd = counter(100.0)
        usd.negotiation.currency_code = "USD"
        assert claim_digest(eur) != claim_digest(usd)

    def test_the_canonical_form_matches_the_documented_one(self) -> None:
        intent = counter(100.0, item="htl-9931")
        intent.negotiation.currency_code = "EUR"
        assert canonical_claim(intent) == (
            "action=counter;item=htl-9931;price=100.00;currency=EUR"
        )
```

- [ ] **Step 2: Run and watch it fail**

Run: `$CORE uv run pytest core/tests/test_receipt.py -v -k Currency`
Expected: FAIL — `AttributeError: currency_code`.

- [ ] **Step 3: Add the proto fields**

```protobuf
message NegotiationOffer {
  double bid_amount = 1;
  float reputation = 2;
  string agent_did = 3;
  string currency_code = 4;  // ISO 4217, as it arrived on the request
}

message NegotiationIntent {
  string item_identifier = 1;
  string item_domain = 2;
  double price = 3;
  string message = 4;
  string thought = 5;

  // Stamped by the Membrane from context, never by the Transformer: the
  // denomination is a property of the request, not something the model decides.
  string currency_code = 6;
}
```

Run: `make generate`

- [ ] **Step 4: Carry it through the aggregator**

At each of the four `HiveContextData(` construction sites in `core/src/aura_hive/hive/aggregator/main.py`, pass `currency_code` through to the `NegotiationOffer` it builds.

The source is real and already reaches core: `NegotiationSignal.currency_code` is field 3 of `proto/aura/dna/v1/dna.proto`, and `core/src/aura_hive/main.py:73,91` forwards it from the gRPC request onto the signal. The aggregator is where it is dropped. So the typed sites read `payload.currency_code`, and the `getattr` fallback site reads `str(getattr(signal, "currency_code", ""))`.

Where a site genuinely has no currency — the vision-discovery path, if the signal it was built from carries none — pass `""`. Step 6 renders that as an empty currency rather than inventing one.

- [ ] **Step 5: Stamp it in the Membrane**

In `inspect_outbound`, after `neg_intent` is resolved and before `_finish`:

```python
        # From context, not from the model. Stamped here so both the claim and
        # the emission carry it and the two digests stay comparable.
        if neg_intent is not None and hive is not None:
            neg_intent.currency_code = hive.offer.currency_code
```

- [ ] **Step 6: Render it in the claim**

```python
    if params_name == "negotiation" and params_value is not None:
        negotiation: NegotiationIntent = params_value
        # An unset currency renders empty rather than defaulting to one. A
        # denomination nobody stated is not USD; inventing one would make two
        # different decisions share a digest.
        return (
            f"action={action};"
            f"item={negotiation.item_identifier};"
            f"price={negotiation.price:.2f};"
            f"currency={negotiation.currency_code}"
        )
```

- [ ] **Step 7: Run the tests**

Run: `$CORE uv run pytest core/tests/ -q` and `make lint`
Expected: PASS. Existing tests pinning a negotiation claim digest fail; update the pins.

- [ ] **Step 8: Commit**

```bash
git add proto core/gen-proto packages/aura-core/gen-proto core/src core/tests
git commit -m "fix(receipt): carry currency into the claim the doc has always promised

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 10: Gateway — the client's view shrinks

**Files:**
- Modify: `api-gateway/src/api_gateway/main.py:203-265`
- Test: `api-gateway/tests/test_receipt_json.py`

**Interfaces:**
- Consumes: Task 7's receipt.
- Produces: `receipt_to_json(receipt) -> dict | None` renders **only** `version` and `canonical_prefix`; `receipt_to_json_full(receipt) -> dict | None` renders everything, for the log.

- [ ] **Step 1: Write the failing test**

```python
def a_signed_override_receipt() -> DecisionReceipt:
    """
    A fully populated receipt, so a field surviving the trim is visible as a
    key that should not be there rather than as an empty string nobody notices.
    """
    return DecisionReceipt(
        version="AURA-RECEIPT-V2",
        canonical_prefix="c0ffee1234abcd56",
        claim_hash="a" * 64,
        emission_hash="b" * 64,
        ruleset_version="guard/negotiation@2.0.0+46cc0e38ca4f895c",
        outcome=DecisionOutcome.DECISION_OUTCOME_OVERRIDE,
        outcome_gate="FLOOR_PRICE_VIOLATION",
        override_scope="value",
        issued_at="2026-08-11T10:00:00Z",
        decision_id="d-1",
        request_id="r-1",
    )


class TestTheClientSeesAHandleAndNothingElse:
    def test_only_the_version_and_the_prefix_are_rendered(self) -> None:
        """
        The receipt is addressed to an auditor. Nothing in it means anything to
        the counterparty, and `outcome_gate` plus the price they received is
        most of the way to inverting the floor.
        """
        rendered = receipt_to_json(a_signed_override_receipt())
        assert set(rendered) == {"version", "canonical_prefix"}

    def test_the_hashes_and_the_gate_are_absent(self) -> None:
        rendered = receipt_to_json(a_signed_override_receipt())
        for gone in ("outcome", "outcome_gate", "claim_hash", "emission_hash",
                     "ruleset_version", "derivation", "signature"):
            assert gone not in rendered

    def test_a_receiptless_response_renders_null(self) -> None:
        """
        betterproto default-constructs a message field on access, so
        `receipt is None` is dead code — the check is by value.
        """
        assert receipt_to_json(DecisionReceipt()) is None


class TestTheFullRendererKeepsEverything:
    def test_it_carries_the_binding_fields(self) -> None:
        rendered = receipt_to_json_full(a_signed_override_receipt())
        for field in ("issued_at", "decision_id", "request_id", "override_scope",
                      "outcome_gate", "claim_hash", "emission_hash"):
            assert field in rendered
```

- [ ] **Step 2: Run and watch it fail**

Run: `$GW uv run pytest api-gateway/tests/test_receipt_json.py -v`
Expected: FAIL — the current renderer returns nine keys.

- [ ] **Step 3: Split the renderer**

Rename the existing function to `receipt_to_json_full`, add the four new fields to what it renders, and write the public one:

```python
def receipt_to_json(receipt: DecisionReceipt | None) -> dict[str, Any] | None:
    """
    What a negotiating counterparty gets: a handle, and nothing to invert.

    The receipt is addressed to an auditor. `outcome_gate` names which rule
    fired, the rule set maps that to a substitute strategy, and the price is
    already in the response — together that recovers the hidden floor. The
    prefix lets them cite this decision in a dispute; the auditor resolves it.

    `version` is the sentinel because `mint` always sets it: a receipt that
    never got minted has an empty one, and betterproto default-constructs the
    field on access rather than returning None.
    """
    if receipt is None or not receipt.version:
        return None

    return {
        "version": receipt.version,
        "canonical_prefix": receipt.canonical_prefix,
    }
```

- [ ] **Step 4: Run the tests**

Run: `$GW uv run pytest api-gateway/tests/ -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api-gateway/
git commit -m "fix(gateway): the counterparty gets a handle, not the guard's reasoning

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 11: The auditor's reader

**Files:**
- Modify: `core/src/aura_hive/hive/membrane/main.py` (log line), `Makefile`
- Create: `tools/verify_receipts.py`
- Test: `core/tests/test_verify_receipts_tool.py`

**Interfaces:**
- Consumes: `verify` and `VerificationResult` (Task 8). The log carries `receipt.to_dict()`, not the gateway's renderer — the tool reads betterproto's own dict form.
- Produces: `read_receipts(lines: Iterable[str]) -> Iterator[DecisionReceipt]`; `summarise(receipts: Iterable[DecisionReceipt]) -> Summary` with `checked: int`, `ok: int`, `attested: int`, `failures: list[tuple[str, str]]`, `unverifiable: Counter[str]`.

- [ ] **Step 1: Write the failing test**

```python
"""
The receipt's reader.

Until now `verify` existed only in tests: no receipts were persisted, so the
function that checks them had nothing to run against. The log line is the store
— it already fires on every decision — and this is what reads it.
"""

import json

from tools.verify_receipts import read_receipts, summarise


def line(**receipt_fields: object) -> str:
    return json.dumps({"event": "membrane_receipt", "receipt": receipt_fields})


def an_ok_receipt() -> DecisionReceipt:
    """A minted receipt, untouched — its prefix matches its content fields."""
    return mint(counter(100.0), counter(100.0), DecisionOutcome.DECISION_OUTCOME_EMIT)


def a_tampered_receipt() -> DecisionReceipt:
    """One whose content moved after minting, so the prefix no longer commits to it."""
    receipt = an_ok_receipt()
    receipt.outcome_gate = "INVENTED_AFTER_THE_FACT"
    return receipt


class TestReading:
    def test_it_ignores_lines_that_are_not_receipts(self) -> None:
        lines = [json.dumps({"event": "heartbeat"}), line(version="AURA-RECEIPT-V2-UNSIGNED")]
        assert len(list(read_receipts(lines))) == 1

    def test_it_survives_a_line_that_is_not_json(self) -> None:
        """
        A log is a stream someone else writes. A truncated line at the end of a
        rotated file must not stop the audit of everything before it.
        """
        assert len(list(read_receipts(["{not json", line(version="AURA-RECEIPT-V2-UNSIGNED")]))) == 1


class TestSummarising:
    def test_it_counts_what_verified_and_what_did_not(self) -> None:
        summary = summarise([an_ok_receipt(), a_tampered_receipt()])
        assert summary.checked == 2
        assert summary.ok == 1
        assert len(summary.failures) == 1

    def test_it_tallies_what_could_not_be_checked(self) -> None:
        summary = summarise([an_ok_receipt()])
        assert summary.unverifiable["emission_content"] == 1
```

- [ ] **Step 2: Run and watch it fail**

Run: `PYTHONPATH=core/src:core/gen-proto:packages/aura-core/src:packages/aura-core/gen-proto:. uv run pytest core/tests/test_verify_receipts_tool.py -v`
Expected: FAIL — `ModuleNotFoundError: tools.verify_receipts`.

- [ ] **Step 3: Widen the log line**

In `membrane/main.py`, replace the five scalar fields on the `membrane_receipt` line with the whole document, keeping the prefix at top level because that is what a human greps for:

```python
            logger.info(
                "membrane_receipt",
                prefix=emission.receipt.canonical_prefix,
                receipt=emission.receipt.to_dict(),
            )
```

Safe to log in full: a receipt carries digests and identifiers, never a price and never a premise value.

- [ ] **Step 4: Write the tool**

Create `tools/verify_receipts.py`:

```python
"""
Check the receipts a running Hive left in its log.

`verify` has existed since the receipt did, and until now it ran only in tests:
no receipts were persisted, so the function that checks them had nothing to
check. The `membrane_receipt` log line already fires on every decision, which
makes the log the store and this the reader.

Reports what could not be checked as prominently as what failed. Every receipt
lists `emission_content` — this tool reads receipts, never the decisions they
describe, so a clean run means "these documents are well-formed and attributable",
not "these decisions were correct".
"""

import json
import sys
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from aura_core_gen.aura.core.v1 import DecisionReceipt
from aura_hive.hive.membrane.receipt import verify

_EVENT = "membrane_receipt"


@dataclass
class Summary:
    checked: int = 0
    ok: int = 0
    attested: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)
    unverifiable: Counter[str] = field(default_factory=Counter)


def read_receipts(lines: Iterable[str]) -> Iterator[DecisionReceipt]:
    """
    Pull receipts out of a structlog JSONL stream.

    A malformed line is skipped rather than raised on. This reads a stream
    someone else writes: a truncated last line in a rotated file must not stop
    the audit of everything before it.
    """
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict) or record.get("event") != _EVENT:
            continue
        payload = record.get("receipt")
        if not isinstance(payload, dict):
            continue
        try:
            yield DecisionReceipt().from_dict(payload)
        except Exception:
            continue


def summarise(receipts: Iterable[DecisionReceipt]) -> Summary:
    """Verify each receipt and tally what held, what did not, and what was skipped."""
    summary = Summary()
    for receipt in receipts:
        summary.checked += 1
        result = verify(receipt)
        if result.ok:
            summary.ok += 1
        if result.attested:
            summary.attested += 1
        # The prefix is a handle for correlating with the log, not a commitment.
        handle = receipt.canonical_prefix or "<no prefix>"
        for reason in result.failures:
            summary.failures.append((handle, reason))
        summary.unverifiable.update(result.unverifiable)
    return summary


def render(summary: Summary) -> str:
    lines = [
        f"checked:     {summary.checked}",
        f"ok:          {summary.ok}",
        f"attested:    {summary.attested}",
        f"failed:      {len(summary.failures)}",
    ]
    if summary.failures:
        lines.append("")
        lines.append("failures")
        lines.extend(f"  {handle}: {reason}" for handle, reason in summary.failures)
    if summary.unverifiable:
        lines.append("")
        lines.append("not checked (no verifier can establish these from a receipt alone)")
        lines.extend(
            f"  {name}: {count}" for name, count in sorted(summary.unverifiable.items())
        )
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    """
    Read a log file named on the command line, or stdin when none is.

    Exits non-zero when any receipt failed, so this can gate a job. An empty
    stream is not a failure — it means nothing was decided, which is a fact
    about the log rather than about the receipts in it.
    """
    if len(argv) > 1 and argv[1] not in ("-", ""):
        lines: Iterable[str] = Path(argv[1]).read_text(encoding="utf-8").splitlines()
    else:
        lines = sys.stdin

    summary = summarise(read_receipts(lines))
    print(render(summary))
    return 1 if summary.failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 5: Add the Make target**

```makefile
verify-receipts:
	PYTHONPATH=$(TOOL_PATH):. uv run python tools/verify_receipts.py $(LOG)
```

- [ ] **Step 6: Run the tests**

Run the command from Step 2.
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tools/verify_receipts.py core/src/aura_hive/hive/membrane/main.py Makefile core/tests/
git commit -m "feat(tools): give the receipt a reader

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 12: Correct the record

**Files:**
- Modify: `docs/DECISION_RECEIPT.md`
- Test: none — prose.

- [ ] **Step 1: Record the audience decision**

Add a section after §1 stating that the receipt is addressed to an auditor, not to the counterparty, and that every field selection below follows from it.

- [ ] **Step 2: Correct §7**

The claim "a receipt a consumer cannot check independently is a receipt they have to trust, which is the thing it exists to replace" is false as built. Replace it with what `verify` establishes — that a document is well-formed and attributable to a key — and what it cannot: that `claim_hash` digests any decision that happened. Point at `unverifiable` containing `emission_content` as the machine-readable form of the same statement.

- [ ] **Step 3: Document ψ and the strategy collapse**

New subsection under §3: the post-condition, why it is checked on the emission rather than the proposal, the bug that motivated it (with the worked numbers), and why the two substitute strategies became one.

- [ ] **Step 4: Restate §3.4's leak argument honestly**

The claim "you cannot probe it for the floor" holds for the derivation field and not for the channel. Record that the substitute price is a function of the floor, that jitter bounds the disclosure at 3% rather than closing it, and that refusing instead of countering is what would close it — which §3.6 declines on product grounds.

- [ ] **Step 5: Update §3.6 and the build order**

`outcome` is now visible to the auditor and not to the client. Mark steps 5 and 6 done for the backend, note the tool as the consumer that was missing, and leave step 4 deferred with its reasoning intact.

- [ ] **Step 6: Update the worked example in §4**

Use the V2 field list, a real jittered price, and `override_scope`.

- [ ] **Step 7: Commit**

```bash
git add docs/DECISION_RECEIPT.md
git commit -m "docs: correct the receipt record to what V2 actually establishes

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Done when

- `make lint` and `make test` pass.
- `make verify-receipts LOG=<a log from a local run>` reports every receipt ok, unattested where no key is configured, and `emission_content` in the unverifiable tally on all of them.
- A local negotiation that trips the floor gate emits a price satisfying ψ, a receipt whose `decision_id` and `request_id` identify it, and an HTTP response carrying only `version` and `canonical_prefix`.
