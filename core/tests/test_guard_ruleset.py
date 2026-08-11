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
    "gates": [
        {
            "id": "G1_A",
            "code": "A_FAILED",
            "consumes": ["price"],
            "safe_price": "margin",
        },
        {
            "id": "G2_B",
            "code": "B_FAILED",
            "consumes": ["price"],
            "safe_price": "floor_markup",
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
            ruleset.validate_against({"G1_A"})

    def test_an_implemented_gate_the_ruleset_omits_is_rejected(self) -> None:
        """
        The other direction matters just as much: a predicate that runs without
        being declared is a rule no receipt can account for.
        """
        ruleset = ruleset_from_mapping(MINIMAL)

        with pytest.raises(RulesetError, match="G3_C"):
            ruleset.validate_against({"G1_A", "G2_B", "G3_C"})

    def test_a_matching_set_is_accepted(self) -> None:
        ruleset = ruleset_from_mapping(MINIMAL)
        ruleset.validate_against({"G1_A", "G2_B"})

    def test_a_duplicate_gate_id_is_rejected(self) -> None:
        """Two gates with one id make the recorded reason ambiguous."""
        dupe = json.loads(json.dumps(MINIMAL))
        dupe["gates"][1]["id"] = "G1_A"

        with pytest.raises(RulesetError, match="G1_A"):
            ruleset_from_mapping(dupe)

    def test_an_unknown_safe_price_strategy_is_rejected(self) -> None:
        bad = json.loads(json.dumps(MINIMAL))
        bad["gates"][0]["safe_price"] = "guess"

        with pytest.raises(RulesetError, match="guess"):
            ruleset_from_mapping(bad)

    @pytest.mark.parametrize("missing", ["family", "version", "gates"])
    def test_a_missing_top_level_key_is_rejected(self, missing: str) -> None:
        incomplete = json.loads(json.dumps(MINIMAL))
        del incomplete[missing]

        with pytest.raises(RulesetError, match=missing):
            ruleset_from_mapping(incomplete)


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

    def test_the_fail_closed_gate_asks_for_the_conservative_safe_price(self) -> None:
        """
        A deployment that cannot read its own margin setting should not answer
        with the cheaper of the two formulas. `margin` yields floor/(1-m),
        above the floor markup, so misconfiguration errs toward the seller.
        """
        gate = {g.id: g for g in load_ruleset().gates}["G3_SETTINGS_PRESENT"]

        assert gate.safe_price == "margin"

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
            load_ruleset().version_string == "guard/negotiation@1.0.0+46cc0e38ca4f895c"
        )

    def test_every_shipped_gate_declares_what_it_consumes(self) -> None:
        """
        `consumes` names premise keys, never values — it is what the receipt's
        step sequence will record (docs/DECISION_RECEIPT.md §3.4).
        """
        for gate in load_ruleset().gates:
            assert isinstance(gate.consumes, tuple)
