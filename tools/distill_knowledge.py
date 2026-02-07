#!/usr/bin/env python3
"""
Binary Knowledge Distillation for Aura Hive Architecture.

This script extracts architectural knowledge from the codebase and serializes it
to binary Protocol Buffer format. It follows the ATCG-M metabolic pattern itself:

M (Membrane in)  → validate_repo_structure()
A (Aggregator)   → extract_*() functions (dynamic discovery)
T (Transformer)  → build_invariants() (reason about completeness)
C (Connector)    → build_knowledge() (assemble proto)
G (Generator)    → emit artifacts (.bin, .json)
M (Membrane out) → validate_output()

Usage:
    python tools/distill_knowledge.py

Output:
    - docs/knowledge/hive_architecture_v2.bin (binary protobuf)
    - docs/knowledge/hive_architecture_v2.json (debug JSON)
"""

import ast
from datetime import UTC, datetime
from pathlib import Path

import yaml
from aura_core.gen.aura.knowledge.v1 import (
    ArchitecturalKnowledge,
    ATCGMPhase,
    ChamberDefinition,
    ComponentDefinition,
    InvariantRule,
    MetabolicPattern,
    OntologyLevel,
)

# Add aura-core to path for imports
repo_root = Path(__file__).parent.parent


# =============================================================================
# M (Membrane In) - Validation Guards
# =============================================================================


def validate_repo_structure() -> None:
    """Guard: Ensure we're in a valid Hive repository."""
    required_markers = [
        "packages/aura-core",
        "proto/aura",
        "core/src/hive",
    ]
    for marker in required_markers:
        matches = list(repo_root.glob(marker))
        if not matches:
            raise ValueError(f"Not a Hive repo: missing {marker}")
    print("✓ Repository structure validated")


# =============================================================================
# A (Aggregator) - Dynamic Discovery Functions
# =============================================================================


def find_files_by_pattern(pattern: str) -> list[Path]:
    """Dynamically discover files using glob patterns."""
    return list(repo_root.glob(pattern))


def extract_genome_protocols() -> list[ComponentDefinition]:
    """Discover and parse Protocol definitions from aura-core dna.py."""
    protocols = []

    # Find dna.py by convention (packages/*/src/*/dna.py)
    dna_files = find_files_by_pattern("packages/*/src/*/dna.py")

    for dna_file in dna_files:
        tree = ast.parse(dna_file.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Check if it's a Protocol class
                is_protocol = any(
                    (isinstance(b, ast.Name) and b.id == "Protocol")
                    or (
                        isinstance(b, ast.Subscript)
                        and isinstance(b.value, ast.Name)
                        and b.value.id == "Protocol"
                    )
                    for b in node.bases
                )

                if is_protocol:
                    # Extract async methods as capabilities
                    capabilities = [
                        m.name
                        for m in node.body
                        if isinstance(m, ast.AsyncFunctionDef | ast.FunctionDef)
                        and not m.name.startswith("_")
                    ]

                    protocols.append(
                        ComponentDefinition(
                            name=node.name,
                            level=OntologyLevel.ONTOLOGY_LEVEL_GENOME,
                            file_path=str(dna_file.relative_to(repo_root)),
                            description=ast.get_docstring(node) or "",
                            dependencies=[],
                            capabilities=capabilities,
                            metadata={},
                        )
                    )

    print(f"✓ Extracted {len(protocols)} genome protocols")
    return protocols


def extract_nucleus_services() -> list[ComponentDefinition]:
    """Discover nucleotide implementations and HiveCortex."""
    services = []

    # Find HiveCortex by convention (*/src/hive/cortex.py)
    cortex_files = find_files_by_pattern("*/src/hive/cortex.py")
    for cortex_file in cortex_files:
        services.append(
            ComponentDefinition(
                name="HiveCortex",
                level=OntologyLevel.ONTOLOGY_LEVEL_NUCLEUS,
                file_path=str(cortex_file.relative_to(repo_root)),
                description="Cellular assembly unit - orchestrates protein wiring and ATCG-M metabolism",
                dependencies=[],
                capabilities=["build_organism", "wire_proteins", "assemble_metabolism"],
                metadata={},
            )
        )

    # Find nucleotides by ATCG-M naming convention
    for nucleotide in [
        "aggregator",
        "transformer",
        "connector",
        "generator",
        "membrane",
        "metabolism",
    ]:
        # Try: */src/hive/{nucleotide}.py OR */src/hive/{nucleotide}/__init__.py
        nucleotide_files = find_files_by_pattern(
            f"*/src/hive/{nucleotide}.py"
        ) + find_files_by_pattern(f"*/src/hive/{nucleotide}/__init__.py")

        for nuc_file in nucleotide_files:
            # Extract class name from file
            tree = ast.parse(nuc_file.read_text())
            class_names = [
                node.name
                for node in ast.walk(tree)
                if isinstance(node, ast.ClassDef) and not node.name.startswith("_")
            ]

            services.append(
                ComponentDefinition(
                    name=class_names[0]
                    if class_names
                    else f"Hive{nucleotide.capitalize()}",
                    level=OntologyLevel.ONTOLOGY_LEVEL_NUCLEUS,
                    file_path=str(nuc_file.relative_to(repo_root)),
                    description=f"{nucleotide.upper()} nucleotide",
                    dependencies=[],
                    capabilities=[],
                    metadata={
                        "nucleotide_type": nucleotide,
                        "structure": "flattened"
                        if "__init__.py" in str(nuc_file)
                        else "module",
                    },
                )
            )

    print(f"✓ Extracted {len(services)} nucleus services")
    return services


def extract_organ_proteins() -> list[ComponentDefinition]:
    """Discover proteins by manifest.yaml convention."""
    proteins = []

    # Find all manifest.yaml files in proteins directories
    manifest_files = find_files_by_pattern("*/src/hive/proteins/*/manifest.yaml")

    for manifest_path in manifest_files:
        protein_dir = manifest_path.parent
        skill_file = protein_dir / "skill.py"

        manifest = yaml.safe_load(manifest_path.read_text())

        # Extract capabilities from manifest
        capabilities_data = manifest.get("capabilities", [])
        if isinstance(capabilities_data, list):
            # Handle both list of strings and list of dicts
            capabilities: list[str] = []
            for item in capabilities_data:
                if isinstance(item, dict):
                    # List of dicts like: - read_item: "Description"
                    capabilities.extend(item.keys())
                elif isinstance(item, str):
                    # Simple list of strings
                    capabilities.append(item)
        elif isinstance(capabilities_data, dict):
            # Dict format like: {read_item: "Description"}
            capabilities = list(capabilities_data.keys())
        else:
            capabilities = []

        proteins.append(
            ComponentDefinition(
                name=manifest.get("name", protein_dir.name).capitalize() + "Skill",
                level=OntologyLevel.ONTOLOGY_LEVEL_ORGANS,
                file_path=str(skill_file.relative_to(repo_root))
                if skill_file.exists()
                else str(protein_dir.relative_to(repo_root)),
                description=manifest.get("description", f"{protein_dir.name} protein"),
                dependencies=[],
                capabilities=capabilities,
                metadata={
                    "role": manifest.get("role", ""),
                    "manifest_version": str(manifest.get("manifest_version", "1.0")),
                },
            )
        )

    print(f"✓ Extracted {len(proteins)} organ proteins")
    return proteins


def extract_citizen_agents() -> list[ComponentDefinition]:
    """Discover agents (WITH goals)."""
    agents = []

    # Find agents by directory convention (agents/*)
    agent_dirs = [
        d
        for d in (repo_root / "agents").iterdir()
        if d.is_dir() and not d.name.startswith(".")
    ]

    for agent_dir in agent_dirs:
        # Look for hive structure or main.py
        hive_dir = agent_dir / "src" / "hive"

        if hive_dir.exists():
            agents.append(
                ComponentDefinition(
                    name=agent_dir.name.replace("-", "_").capitalize() + "Agent",
                    level=OntologyLevel.ONTOLOGY_LEVEL_CITIZENS,
                    file_path=str(hive_dir.relative_to(repo_root)),
                    description=f"{agent_dir.name} agent with autonomous goals",
                    metadata={
                        "type": "agent",
                        "has_goals": "true",
                        "has_atcgm": "true" if hive_dir.exists() else "false",
                    },
                )
            )

    print(f"✓ Extracted {len(agents)} citizen agents")
    return agents


def extract_citizen_adapters() -> list[ComponentDefinition]:
    """Discover adapters (NO goals, passive translation)."""
    adapters = []
    path = "synapses"

    # Find adapters by directory convention (adapters/*)
    adapter_dirs = [
        d
        for d in (repo_root / path).iterdir()
        if d.is_dir() and not d.name.startswith(".")
    ]

    for adapter_dir in adapter_dirs:
        main_file = adapter_dir / "src" / "main.py"

        if main_file.exists():
            adapters.append(
                ComponentDefinition(
                    name=adapter_dir.name.replace("-", "_").capitalize() + "Adapter",
                    level=OntologyLevel.ONTOLOGY_LEVEL_CITIZENS,
                    file_path=str(main_file.relative_to(repo_root)),
                    description=f"{adapter_dir.name} adapter for protocol translation",
                    metadata={
                        "type": "adapter",
                        "has_goals": "false",
                    },
                )
            )

    print(f"✓ Extracted {len(adapters)} citizen adapters")
    return adapters


def discover_atcgm_services() -> list[Path]:
    """Find all services with hive/ directory structure."""
    # Any directory containing src/hive/ is a potential ATCG-M service
    hive_dirs = find_files_by_pattern("*/src/hive")
    return [d for d in hive_dirs if d.is_dir()]


def extract_atcgm_patterns() -> list[MetabolicPattern]:
    """Scan discovered services for ATCG-M completeness."""
    patterns = []

    for hive_dir in discover_atcgm_services():
        # Extract service name from path (e.g., core/src/hive -> core)
        parts = hive_dir.parts
        service_name = (
            parts[parts.index("src") - 1]
            if "src" in parts
            else hive_dir.parent.parent.name
        )

        # Discover implemented phases
        implemented_phases = []
        phase_implementations = {}

        phase_map = {
            "aggregator": ATCGMPhase.ATCGM_PHASE_A,
            "transformer": ATCGMPhase.ATCGM_PHASE_T,
            "connector": ATCGMPhase.ATCGM_PHASE_C,
            "generator": ATCGMPhase.ATCGM_PHASE_G,
            "membrane": ATCGMPhase.ATCGM_PHASE_M_INBOUND,
            "metabolism": ATCGMPhase.ATCGM_PHASE_M_INBOUND,  # Metabolism orchestrates M
        }

        for nucleotide, phase in phase_map.items():
            # Check: {nucleotide}.py OR {nucleotide}/__init__.py
            module_file = hive_dir / f"{nucleotide}.py"
            package_file = hive_dir / nucleotide / "__init__.py"

            if module_file.exists():
                implemented_phases.append(phase)
                phase_implementations[nucleotide] = str(
                    module_file.relative_to(repo_root)
                )
            elif package_file.exists():
                implemented_phases.append(phase)
                phase_implementations[nucleotide] = str(
                    package_file.relative_to(repo_root)
                )

        # Remove duplicates (membrane counted twice)
        implemented_phases = list(set(implemented_phases))

        patterns.append(
            MetabolicPattern(
                service_name=service_name,
                implemented_phases=implemented_phases,
                phase_implementations=phase_implementations,
                is_complete=len(implemented_phases) >= 5,  # Need at least M, A, T, C, G
                metadata={
                    "nucleotide_count": str(len(phase_implementations)),
                },
            )
        )

    print(f"✓ Extracted {len(patterns)} ATCG-M patterns")
    return patterns


def discover_sacred_chambers() -> list[ChamberDefinition]:
    """Discover chambers from common patterns and conventions."""
    chambers = []

    # Common chamber patterns in Hive architecture
    common_chambers = {
        "migrations/": (
            "HiveEvolutionaryScrolls",
            "Database schema evolution",
            OntologyLevel.ONTOLOGY_LEVEL_NUCLEUS,
        ),
        "src/llm/": (
            "ReasoningNucleus",
            "LLM strategies and engines",
            OntologyLevel.ONTOLOGY_LEVEL_NUCLEUS,
        ),
        "src/guard/": (
            "HiveMembrane",
            "Security guards and validation",
            OntologyLevel.ONTOLOGY_LEVEL_NUCLEUS,
        ),
        "proto/": (
            "SacredScrolls",
            "Protocol Buffer definitions",
            OntologyLevel.ONTOLOGY_LEVEL_GENOME,
        ),
        "src/hive/proteins/": (
            "EnzymaticHelpers",
            "SkillProtocol implementations",
            OntologyLevel.ONTOLOGY_LEVEL_ORGANS,
        ),
        "tests/": (
            "ValidationPollen",
            "Test suites",
            OntologyLevel.ONTOLOGY_LEVEL_NUCLEUS,
        ),
    }

    for path_pattern, (name, purpose, level) in common_chambers.items():
        discovered = find_files_by_pattern(f"*/{path_pattern}")
        if discovered:
            chambers.append(
                ChamberDefinition(
                    filesystem_path=path_pattern,
                    sacred_name=name,
                    purpose=purpose,
                    level=level,
                )
            )

    print(f"✓ Discovered {len(chambers)} sacred chambers")
    return chambers


# =============================================================================
# T (Transformer) - Reasoning About Architecture
# =============================================================================


def build_invariants() -> list[InvariantRule]:
    """Reason about architectural invariants and constraints."""
    invariants = [
        InvariantRule(
            rule_id="ontological_purity",
            description="Genome NEVER imports from Nucleus/Organs/Citizens (one-way dependency)",
            enforcement_mechanism="bee-keeper auditor + import analysis",
            is_hard_constraint=True,
            examples=[
                "✅ from aura_core.dna import Aggregator (in any level)",
                "❌ from core.db import User (in packages/aura-core)",
            ],
        ),
        InvariantRule(
            rule_id="fractal_completeness",
            description="All services MUST implement all 5 ATCG-M nucleotides (M, A, T, C, G)",
            enforcement_mechanism="bee-keeper auditor + distillation validation",
            is_hard_constraint=True,
            examples=[
                "✅ core/ has: aggregator.py, transformer.py, connector.py, generator.py, membrane.py",
                "❌ Missing any nucleotide file breaks the fractal pattern",
            ],
            metadata={},
        ),
        InvariantRule(
            rule_id="trinity_pattern",
            description="All Proteins follow bind() → initialize() → execute() lifecycle",
            enforcement_mechanism="type system (SkillProtocol) + HiveCortex wiring",
            is_hard_constraint=True,
            examples=[
                "✅ class PulseSkill: def bind(), async def initialize(), async def execute()",
                "❌ Direct method calls without Trinity lifecycle",
            ],
            metadata={},
        ),
        InvariantRule(
            rule_id="hidden_knowledge",
            description="Floor prices NEVER exposed to agents (prevents gaming)",
            enforcement_mechanism="Membrane guards (inspect_outbound)",
            is_hard_constraint=True,
            examples=[
                "✅ Agents receive: accepted/countered/rejected/ui_required",
                "❌ Exposing floor_price in API responses",
            ],
            metadata={},
        ),
        InvariantRule(
            rule_id="cellular_metaphor",
            description="All terminology uses biological metaphors (enforced poetically)",
            enforcement_mechanism="bee-keeper auditor flags HERESY",
            is_hard_constraint=False,  # Warning, not build failure
            examples=[
                "✅ Genome, Nucleus, Proteins, Membrane, Bloodstream",
                "❌ Manager, Service, Helper, Utils (non-biological terms)",
            ],
            metadata={},
        ),
        InvariantRule(
            rule_id="contract_first_apis",
            description="Protocol Buffers define ALL service boundaries",
            enforcement_mechanism="buf generate workflow + generated code immutability",
            is_hard_constraint=True,
            examples=[
                "✅ Modify .proto → buf generate → Update implementations",
                "❌ Manually editing */src/proto/ generated code",
            ],
            metadata={},
        ),
    ]

    print(f"✓ Built {len(invariants)} architectural invariants")
    return invariants


# =============================================================================
# C (Connector) - Assembly
# =============================================================================


def build_knowledge() -> ArchitecturalKnowledge:
    """Assemble complete architectural knowledge proto (ATCG-M orchestration)."""
    print("\n=== Building Architectural Knowledge ===\n")

    # A (Aggregator): Collect data from multiple sources
    genome_protocols = extract_genome_protocols()
    nucleus_services = extract_nucleus_services()
    organ_proteins = extract_organ_proteins()
    citizen_agents = extract_citizen_agents()
    citizen_adapters = extract_citizen_adapters()
    atcgm_patterns = extract_atcgm_patterns()
    sacred_chambers = discover_sacred_chambers()

    # T (Transformer): Reason about completeness and consistency
    invariants = build_invariants()

    # C (Connector): Assemble the knowledge proto
    knowledge = ArchitecturalKnowledge(
        knowledge_id=f"hive_arch_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}",
        version="HIVE_GENOME_v2",
        created_at=datetime.now(UTC),
        metadata={
            "source": "automated_extraction",
            "codebase": "aura-hive",
            "extraction_method": "dynamic_discovery",
            "repo_root": str(repo_root),
        },
        genome_protocols=genome_protocols,
        nucleus_services=nucleus_services,
        organ_proteins=organ_proteins,
        citizen_agents=citizen_agents,
        citizen_adapters=citizen_adapters,
        atcgm_patterns=atcgm_patterns,
        sacred_chambers=sacred_chambers,
        invariants=invariants,
    )

    print("\n✓ Knowledge assembly complete")
    return knowledge


# =============================================================================
# G (Generator) - Emit Artifacts
# =============================================================================


def emit_artifacts(knowledge: ArchitecturalKnowledge) -> None:
    """Generate binary and JSON outputs."""
    output_dir = repo_root / "docs" / "knowledge"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Debug: Try serializing parts individually
    print("\nDebug: Testing serialization of each component...")
    try:
        for _, proto in enumerate(knowledge.genome_protocols):
            bytes(proto)
        print(f"  ✓ {len(knowledge.genome_protocols)} genome protocols")
    except Exception as e:
        print(f"  ❌ Genome protocols: {e}")
        raise

    try:
        for _, svc in enumerate(knowledge.nucleus_services):
            bytes(svc)
        print(f"  ✓ {len(knowledge.nucleus_services)} nucleus services")
    except Exception as e:
        print(f"  ❌ Nucleus services: {e}")
        raise

    try:
        for _, protein in enumerate(knowledge.organ_proteins):
            bytes(protein)
        print(f"  ✓ {len(knowledge.organ_proteins)} organ proteins")
    except Exception as e:
        print(f"  ❌ Organ proteins: {e}")
        raise

    try:
        for _, pattern in enumerate(knowledge.atcgm_patterns):
            bytes(pattern)
        print(f"  ✓ {len(knowledge.atcgm_patterns)} ATCG-M patterns")
    except Exception as e:
        print(f"  ❌ ATCGM patterns: {e}")
        raise

    try:
        for _i, inv in enumerate(knowledge.invariants):
            bytes(inv)
        print(f"  ✓ {len(knowledge.invariants)} invariants")
    except Exception as e:
        print(f"  ❌ Invariant #{_i}: {e}")
        raise

    # Binary output (protobuf)
    binary_path = output_dir / "hive_architecture_v2.bin"
    binary_bytes = bytes(knowledge)
    binary_path.write_bytes(binary_bytes)
    print(f"\n✓ Binary distillation: {binary_path} ({len(binary_bytes)} bytes)")

    # JSON for debugging
    json_path = output_dir / "hive_architecture_v2.json"
    json_content = knowledge.to_json(indent=2)
    json_path.write_text(json_content)
    print(f"✓ JSON debug output: {json_path} ({len(json_content)} bytes)")


# =============================================================================
# M (Membrane Out) - Output Validation
# =============================================================================


def validate_output(knowledge: ArchitecturalKnowledge) -> None:
    """Guard: Validate extracted knowledge before finishing."""
    assert len(knowledge.genome_protocols) > 0, "No genome protocols found"
    assert len(knowledge.nucleus_services) > 0, "No nucleus services found"
    assert len(knowledge.organ_proteins) > 0, "No organ proteins found"
    assert len(knowledge.atcgm_patterns) > 0, "No ATCG-M patterns found"
    assert len(knowledge.invariants) > 0, "No invariants defined"

    # Check ATCG-M completeness
    incomplete = [p for p in knowledge.atcgm_patterns if not p.is_complete]
    if incomplete:
        print(f"\n⚠ Warning: {len(incomplete)} services have incomplete ATCG-M:")
        for pattern in incomplete:
            print(
                f"  - {pattern.service_name}: {len(pattern.implemented_phases)}/5 phases"
            )
    else:
        print("\n✓ All services have complete ATCG-M patterns")

    print("\n✓ Output validation passed")


# =============================================================================
# Main Execution (ATCG-M Flow)
# =============================================================================


def main() -> None:
    """Execute the distillation pipeline following ATCG-M pattern."""
    print("╔════════════════════════════════════════════════════════════╗")
    print("║  Aura Hive Binary Knowledge Distillation (ATCG-M)         ║")
    print("╚════════════════════════════════════════════════════════════╝\n")

    try:
        # M (inbound): Validate repository structure
        validate_repo_structure()

        # A-T-C: Build knowledge (aggregation, transformation, assembly)
        knowledge = build_knowledge()

        # G: Emit artifacts
        emit_artifacts(knowledge)

        # M (outbound): Validate output
        validate_output(knowledge)

        print("\n╔════════════════════════════════════════════════════════════╗")
        print("║  ✓ Knowledge Extraction Complete                          ║")
        print("╚════════════════════════════════════════════════════════════╝")

    except Exception as e:
        print(f"\n❌ Error during distillation: {e}")
        raise


if __name__ == "__main__":
    main()
