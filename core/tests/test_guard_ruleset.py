"""
The guard's rules are declared, so they can be versioned.

A receipt has to name the rules a decision was judged under, and a name is only
worth something if it changes when the rules do (docs/DECISION_RECEIPT.md §3.3).
Two things stood in the way. The gate order lived in the control flow of
`validate_decision`, where it could be reordered without anyone noticing, and
the identity of the rule that fired was recovered downstream by looking for the
substring "margin" or "floor" in an exception message.

`ruleset.yaml` declares the gates in order, each with the code it emits. The
digest is taken over the parsed structure rather than the file bytes, so
reformatting the file does not invent a new version while any semantic edit does.
"""

import json
from pathlib import Path

import pytest
import yaml
from aura_hive.hive.proteins.guard.ruleset import (
    RulesetError,
    load_ruleset,
    ruleset_from_mapping,
)

MINIMAL = {
    "family": "guard/negotiation",
    "version": "1.0.0",
    "safe_price": "safe_offer",
    "postcondition": {
        "id": "PSI_TEST",
        "clauses": [
            {"id": "C1", "expr": "price > 0", "consumes": ["price"]},
        ],
    },
    "gates": [
        {
            "id": "G1_A",
            "code": "A_FAILED",
            "consumes": ["price"],
        },
        {
            "id": "G2_B",
            "code": "B_FAILED",
            "consumes": ["price"],
        },
    ],
}


class TestVersionString:
    def test_the_version_names_the_family_the_semver_and_the_digest(self) -> None:
        ruleset = ruleset_from_mapping(MINIMAL)

        family, _, rest = ruleset.version_string.partition("@")
        semver, _, digest = rest.partition("+")

        assert family == "guard/negotiation"
        assert semver == "1.0.0"
        assert len(digest) == 16
        assert digest == digest.lower()
        int(digest, 16)  # raises if it is not hex


class TestDigest:
    def test_reformatting_the_file_does_not_change_the_digest(self) -> None:
        """
        The digest is taken over parsed structure, not bytes.

        Hashing the file directly was the obvious implementation and the wrong
        one: a reflowed comment would mint a new rule-set version, and a version
        that changes without the rules changing is noise a verifier has to
        ignore — which trains everyone to ignore it when it matters.
        """
        dense = yaml.safe_load(json.dumps(MINIMAL))
        spaced = yaml.safe_load(
            "# a comment\n" + yaml.safe_dump(MINIMAL, default_flow_style=False)
        )

        assert ruleset_from_mapping(dense).digest == ruleset_from_mapping(spaced).digest

    def test_reordering_the_gates_changes_the_digest(self) -> None:
        """Gate order is semantic: it decides which reason a decision is refused under."""
        swapped = json.loads(json.dumps(MINIMAL))
        swapped["gates"].reverse()

        assert (
            ruleset_from_mapping(swapped).digest != ruleset_from_mapping(MINIMAL).digest
        )

    def test_a_non_semantic_top_level_key_does_not_change_the_digest(self) -> None:
        """
        Same argument as hashing bytes, one level up: a `description:` added for
        readers is not a rule, and minting a new version for it teaches everyone
        that a changed version means nothing.
        """
        annotated = json.loads(json.dumps(MINIMAL))
        annotated["description"] = "notes for whoever reads this next"

        assert (
            ruleset_from_mapping(annotated).digest
            == ruleset_from_mapping(MINIMAL).digest
        )

    def test_changing_a_code_changes_the_digest(self) -> None:
        edited = json.loads(json.dumps(MINIMAL))
        edited["gates"][0]["code"] = "SOMETHING_ELSE"

        assert (
            ruleset_from_mapping(edited).digest != ruleset_from_mapping(MINIMAL).digest
        )


class TestFailClosed:
    def test_a_gate_the_engine_cannot_evaluate_is_rejected(self) -> None:
        """
        A declared gate with no implementation would silently never fire — the
        rule-set would claim a guarantee the engine does not provide.
        """
        ruleset = ruleset_from_mapping(MINIMAL)

        with pytest.raises(RulesetError, match="G2_B"):
            ruleset.validate_against({"G1_A"}, {"C1"})

    def test_an_implemented_gate_the_ruleset_omits_is_rejected(self) -> None:
        """
        The other direction matters just as much: a predicate that runs without
        being declared is a rule no receipt can account for.
        """
        ruleset = ruleset_from_mapping(MINIMAL)

        with pytest.raises(RulesetError, match="G3_C"):
            ruleset.validate_against({"G1_A", "G2_B", "G3_C"}, {"C1"})

    def test_a_matching_set_is_accepted(self) -> None:
        ruleset = ruleset_from_mapping(MINIMAL)
        ruleset.validate_against({"G1_A", "G2_B"}, {"C1"})

    def test_a_duplicate_gate_id_is_rejected(self) -> None:
        """Two gates with one id make the recorded reason ambiguous."""
        dupe = json.loads(json.dumps(MINIMAL))
        dupe["gates"][1]["id"] = "G1_A"

        with pytest.raises(RulesetError, match="G1_A"):
            ruleset_from_mapping(dupe)

    @pytest.mark.parametrize("missing", ["family", "version", "gates"])
    def test_a_missing_top_level_key_is_rejected(self, missing: str) -> None:
        incomplete = json.loads(json.dumps(MINIMAL))
        del incomplete[missing]

        with pytest.raises(RulesetError, match=missing):
            ruleset_from_mapping(incomplete)


class TestMalformedSource:
    def test_unparseable_yaml_is_a_ruleset_error(self, tmp_path: Path) -> None:
        """
        Every other way of failing to get rules raises RulesetError; a syntax
        error should not be the one case that surfaces a yaml exception the
        caller has no reason to catch.
        """
        broken = tmp_path / "ruleset.yaml"
        broken.write_text("gates: [\n  - id: unterminated\n", encoding="utf-8")

        with pytest.raises(RulesetError, match="valid YAML"):
            load_ruleset(broken)

    def test_a_missing_file_is_a_ruleset_error(self, tmp_path: Path) -> None:
        with pytest.raises(RulesetError, match="not found"):
            load_ruleset(tmp_path / "absent.yaml")

    def test_a_gate_that_is_not_a_mapping_is_a_ruleset_error(self) -> None:
        """A malformed entry should read as a bad rule set, not a TypeError."""
        bad = json.loads(json.dumps(MINIMAL))
        bad["gates"][0] = "G1_A"

        with pytest.raises(RulesetError, match="mapping"):
            ruleset_from_mapping(bad)

    def test_a_consumes_that_is_not_a_list_is_a_ruleset_error(self) -> None:
        bad = json.loads(json.dumps(MINIMAL))
        bad["gates"][0]["consumes"] = "price"

        with pytest.raises(RulesetError, match="consumes"):
            ruleset_from_mapping(bad)

    def test_a_file_that_is_not_a_mapping_is_a_ruleset_error(
        self, tmp_path: Path
    ) -> None:
        listed = tmp_path / "ruleset.yaml"
        listed.write_text("- just\n- a\n- list\n", encoding="utf-8")

        with pytest.raises(RulesetError, match="mapping"):
            load_ruleset(listed)


class TestShippedRuleset:
    def test_the_shipped_ruleset_loads(self) -> None:
        ruleset = load_ruleset()

        assert ruleset.family == "guard/negotiation"
        assert [gate.id for gate in ruleset.gates] == [
            "G1_PRICE_POSITIVE",
            "G2_FLOOR_VIOLATION",
            "G3_SETTINGS_PRESENT",
            "G4_MARGIN_VIOLATION",
        ]

    def test_the_shipped_order_is_the_order_the_engine_applied_before(self) -> None:
        """
        This order is not a preference, it is the behaviour that shipped: the
        floor check ran before the fail-closed settings check, so a decision
        below floor on a misconfigured deployment was refused for the floor.
        Moving G3 earlier would change which reason those decisions carry.
        """
        ids = [gate.id for gate in load_ruleset().gates]

        assert ids.index("G2_FLOOR_VIOLATION") < ids.index("G3_SETTINGS_PRESENT")

    def test_the_shipped_version_string_is_the_pinned_one(self) -> None:
        """
        A change detector, deliberately.

        The digest is what a receipt cites to say which rules judged a decision,
        so it must not drift by accident. Editing ruleset.yaml fails here until
        the pin is updated in the same commit — which is the moment to ask
        whether `version` should be bumped too, since consumers key off the
        semver and only notice the digest afterwards.
        """
        assert (
            load_ruleset().version_string == "guard/negotiation@2.0.0+6b8b5d6db3e6e351"
        )

    def test_every_shipped_gate_declares_what_it_consumes(self) -> None:
        """
        `consumes` names premise keys, never values — it is what the receipt's
        step sequence will record (docs/DECISION_RECEIPT.md §3.4).
        """
        for gate in load_ruleset().gates:
            assert isinstance(gate.consumes, tuple)


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
            "postcondition": {
                "id": "P",
                "clauses": [{"id": "C", "expr": "x", "consumes": []}],
            },
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
            "postcondition": {
                "id": "P",
                "clauses": [{"id": "C", "expr": "x", "consumes": []}],
            },
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
