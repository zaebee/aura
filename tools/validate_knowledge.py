#!/usr/bin/env python3
"""
Cross-Format Knowledge Validator.

Validates consistency between binary protobuf knowledge distillation and
the markdown architectural anchor. Ensures both representations describe
the same architecture.

Usage:
    python tools/validate_knowledge.py

Checks:
    1. Protocol count matches expected minimum
    2. HiveCortex documented in both formats
    3. ATCG-M completeness assertions
    4. Key architectural patterns present
    5. Protein structure descriptions consistent
"""

import sys
from pathlib import Path

from aura_core.gen.aura.knowledge.v1 import ArchitecturalKnowledge

# Add aura-core to path for imports
repo_root = Path(__file__).parent.parent


def load_binary_knowledge() -> ArchitecturalKnowledge:
    """Load binary protobuf knowledge."""
    binary_path = repo_root / "docs" / "knowledge" / "hive_architecture_v2.bin"
    if not binary_path.exists():
        raise FileNotFoundError(
            f"Binary knowledge not found: {binary_path}\n"
            "Run: uv run tools/distill_knowledge.py"
        )

    binary_bytes = binary_path.read_bytes()
    knowledge = ArchitecturalKnowledge().parse(binary_bytes)
    print(f"✓ Loaded binary knowledge: {len(binary_bytes)} bytes")
    return knowledge


def load_markdown_anchor() -> str:
    """Load markdown architectural anchor."""
    anchor_path = repo_root / "docs" / "ARCHITECTURAL_ANCHOR.md"
    if not anchor_path.exists():
        raise FileNotFoundError(f"Markdown anchor not found: {anchor_path}")

    anchor_content = anchor_path.read_text()
    print(f"✓ Loaded markdown anchor: {len(anchor_content)} characters")
    return anchor_content


def validate_protocol_count(knowledge: ArchitecturalKnowledge, anchor: str) -> bool:
    """Check that protocol count is reasonable and mentioned in anchor."""
    protocol_count = len(knowledge.genome_protocols)

    # Minimum expected protocols
    expected_min = (
        5  # Aggregator, Transformer, SkillProtocol, Connector, Generator, Membrane
    )

    if protocol_count < expected_min:
        print(f"❌ Protocol count too low: {protocol_count} < {expected_min}")
        return False

    # Check that key protocols are mentioned in anchor
    key_protocols = ["Aggregator", "Transformer", "Connector", "Generator", "Membrane"]
    missing = [p for p in key_protocols if p not in anchor]

    if missing:
        print(f"❌ Missing protocols in anchor: {missing}")
        return False

    print(
        f"✓ Protocol count valid: {protocol_count} protocols, all key protocols documented"
    )
    return True


def validate_hive_cortex(knowledge: ArchitecturalKnowledge, anchor: str) -> bool:
    """Check that HiveCortex is present in both formats."""
    # Check binary
    has_cortex = any(s.name == "HiveCortex" for s in knowledge.nucleus_services)

    if not has_cortex:
        print("❌ HiveCortex not found in binary knowledge")
        return False

    # Check markdown
    if "HiveCortex" not in anchor:
        print("❌ HiveCortex not documented in markdown anchor")
        return False

    if "build_organism" not in anchor:
        print("❌ build_organism() pattern not documented in anchor")
        return False

    print("✓ HiveCortex pattern documented in both formats")
    return True


def validate_atcgm_completeness(knowledge: ArchitecturalKnowledge, anchor: str) -> bool:
    """Check ATCG-M completeness assertions."""
    # Check binary patterns
    patterns = knowledge.atcgm_patterns
    complete_patterns = [p for p in patterns if p.is_complete]

    # Core service should have complete ATCG-M
    core_pattern = next((p for p in patterns if p.service_name == "core"), None)

    if not core_pattern:
        print("❌ Core service ATCG-M pattern not found")
        return False

    if not core_pattern.is_complete:
        print(
            f"❌ Core service has incomplete ATCG-M: {len(core_pattern.implemented_phases)}/5 phases"
        )
        return False

    # Check markdown mentions ATCG-M
    if "M→A→T→M→C→G" not in anchor and "M(in)→A→T→M(out)→C→G" not in anchor:
        print("❌ ATCG-M pattern not documented in anchor")
        return False

    print(
        f"✓ ATCG-M completeness validated: {len(complete_patterns)}/{len(patterns)} complete services"
    )
    return True


def validate_protein_structure(knowledge: ArchitecturalKnowledge, anchor: str) -> bool:
    """Check protein structure documentation."""
    protein_count = len(knowledge.organ_proteins)

    if protein_count < 3:
        print(f"❌ Too few proteins extracted: {protein_count}")
        return False

    # Check markdown describes protein structure
    protein_markers = ["skill.py", "manifest.yaml", "Trinity"]

    missing_markers = [m for m in protein_markers if m not in anchor]

    if missing_markers:
        print(f"❌ Protein structure incomplete in anchor, missing: {missing_markers}")
        return False

    # Check for capabilities documentation
    key_proteins = ["persistence", "pulse", "reasoning"]
    for protein_name in key_proteins:
        found = any(protein_name in p.name.lower() for p in knowledge.organ_proteins)
        if not found:
            print(f"⚠ Warning: {protein_name} protein not found in binary knowledge")

    print(f"✓ Protein structure documented: {protein_count} proteins extracted")
    return True


def validate_invariants(knowledge: ArchitecturalKnowledge, anchor: str) -> bool:
    """Check architectural invariants are documented."""
    invariant_count = len(knowledge.invariants)

    if invariant_count < 4:
        print(f"❌ Too few invariants: {invariant_count}")
        return False

    # Check key invariants exist
    key_invariants = {
        "ontological_purity": "Genome NEVER imports",
        "fractal_completeness": "all 5",
        "trinity_pattern": "bind",
        "hidden_knowledge": "floor_price",
    }

    for rule_id, marker in key_invariants.items():
        found = any(inv.rule_id == rule_id for inv in knowledge.invariants)
        if not found:
            print(f"❌ Missing invariant in binary: {rule_id}")
            return False

        if marker not in anchor:
            print(f"❌ Invariant marker not in anchor: {marker} ({rule_id})")
            return False

    print(f"✓ Architectural invariants validated: {invariant_count} rules")
    return True


def validate_version_consistency(
    knowledge: ArchitecturalKnowledge, anchor: str
) -> bool:
    """Check version numbers match."""
    binary_version = knowledge.version

    # Anchor should mention the version
    if binary_version not in anchor:
        print(
            f"⚠ Warning: Version mismatch - binary: {binary_version}, not found in anchor"
        )
        return True  # Warning, not error

    print(f"✓ Version consistent: {binary_version}")
    return True


def validate_binary_distillation_docs(anchor: str) -> bool:
    """Check that anchor documents binary distillation capability."""
    markers = ["binary", "protobuf", "knowledge.proto", "distill_knowledge.py"]

    found_markers = [m for m in markers if m.lower() in anchor.lower()]

    if len(found_markers) < 2:
        print(
            f"⚠ Warning: Binary distillation not well-documented in anchor (found: {found_markers})"
        )
        return True  # Warning, not error

    print("✓ Binary distillation documented in anchor")
    return True


def main() -> int:
    """Run all validation checks."""
    print("╔════════════════════════════════════════════════════════════╗")
    print("║  Aura Hive Cross-Format Knowledge Validator               ║")
    print("╚════════════════════════════════════════════════════════════╝\n")

    try:
        # Load both formats
        knowledge = load_binary_knowledge()
        anchor = load_markdown_anchor()

        print("\n=== Running Validation Checks ===\n")

        # Run all checks
        checks = [
            ("Protocol Count", validate_protocol_count(knowledge, anchor)),
            ("HiveCortex Pattern", validate_hive_cortex(knowledge, anchor)),
            ("ATCG-M Completeness", validate_atcgm_completeness(knowledge, anchor)),
            ("Protein Structure", validate_protein_structure(knowledge, anchor)),
            ("Architectural Invariants", validate_invariants(knowledge, anchor)),
            ("Version Consistency", validate_version_consistency(knowledge, anchor)),
            ("Binary Distillation Docs", validate_binary_distillation_docs(anchor)),
        ]

        passed = sum(1 for _, result in checks if result)
        total = len(checks)

        print("\n" + "=" * 60)
        print(f"Validation Results: {passed}/{total} checks passed")
        print("=" * 60)

        if passed == total:
            print("\n✓ All validation checks passed!")
            print("  Binary and markdown formats are consistent.\n")
            return 0
        else:
            failed_checks = [name for name, result in checks if not result]
            print(f"\n❌ Validation failed. Failed checks: {failed_checks}\n")
            return 1

    except Exception as e:
        print(f"\n❌ Validation error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
