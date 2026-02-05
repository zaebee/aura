#!/usr/bin/env python3
"""
Hive Cartographer: Self-Documenting Map Generator

Generates visual geography documentation from hive-manifest.yaml.
Outputs Mermaid diagrams and chamber mapping tables to docs/visual/hive/geography.md.

Usage:
    python tools/map_hive.py [--manifest PATH] [--output PATH] [--format markdown|mermaid]
"""

import argparse
import sys
from pathlib import Path
from typing import Any, cast

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:
    print("Error: pyyaml is required. Install with: uv add pyyaml", file=sys.stderr)
    sys.exit(1)


def _load_manifest(manifest_path: Path) -> dict[str, Any]:
    """Parse hive-manifest.yaml with error handling."""
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    try:
        with manifest_path.open("r") as f:
            data = yaml.safe_load(f)
        return cast(dict[str, Any], data)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in manifest: {e}") from e


def generate_mermaid_hierarchy(manifest: dict[str, Any]) -> str:
    """
    Generate Mermaid graph TD showing folder hierarchy.

    Creates:
    - Root node → macro folders
    - core → ATCG-M nucleotide subgraph (A, T, C, G, M with metabolism flow)
    - core → Proteins subgraph (reasoning, pulse, guard, etc.)
    """
    lines = ["```mermaid", "graph TD"]
    lines.append('    Root["🏠 Aura Hive Root"]')
    lines.append("")

    # Add macro folders
    macro_folders = manifest.get("macro_atcg_folders", [])
    for folder in macro_folders:
        node_id = folder.replace("-", "_")
        emoji = _get_folder_emoji(folder)
        lines.append(f'    {node_id}["{emoji} {folder}/"]')
        lines.append(f"    Root --> {node_id}")

    lines.append("")

    # Core ATCG-M nucleotide subgraph
    lines.append('    subgraph core_nucleotides["🧬 Core ATCG-M Nucleotides"]')
    lines.append(
        '        A["📡 A (Aggregator)<br/>src/hive/aggregator/<br/>Senses signals"]'
    )
    lines.append(
        '        T["🧠 T (Transformer)<br/>src/hive/transformer/<br/>LLM reasoning"]'
    )
    lines.append(
        '        M_out["🛡️ M (Membrane Out)<br/>src/hive/membrane/<br/>Enforces rules"]'
    )
    lines.append(
        '        C["⚡ C (Connector)<br/>src/hive/connector/<br/>Executes actions"]'
    )
    lines.append(
        '        G["📜 G (Generator)<br/>src/hive/generator/<br/>Emits events"]'
    )
    lines.append("")
    lines.append("        A --> T --> M_out --> C --> G")
    lines.append("    end")
    lines.append("")
    lines.append("    core --> core_nucleotides")
    lines.append("")

    # Core Proteins subgraph
    lines.append('    subgraph core_proteins["⚗️ Core Proteins (SkillProtocol)"]')
    proteins = [
        (
            'ReasoningSkill["🧠 ReasoningSkill<br/>src/hive/proteins/reasoning/<br/>negotiate, analyze"]',
            "#cce5ff",
        ),
        (
            'StorageSkill["💾 StorageSkill<br/>src/hive/proteins/storage/<br/>db_query, cache_get"]',
            "#e6f3ff",
        ),
        (
            'CryptoSkill["💰 CryptoSkill<br/>src/hive/proteins/crypto/<br/>verify_payment, encrypt"]',
            "#fff3cd",
        ),
        (
            'PulseSkill["💓 PulseSkill<br/>src/hive/proteins/pulse/<br/>emit_heartbeat, NATS"]',
            "#ffcccc",
        ),
        (
            'MonitorSkill["📊 MonitorSkill<br/>src/hive/proteins/monitor/<br/>fetch_metrics, health"]',
            "#d4edda",
        ),
        (
            'GuardSkill["🛡️ GuardSkill<br/>src/hive/proteins/guard/<br/>validate_margin, sanitize"]',
            "#ffcccc",
        ),
    ]

    for protein_def, _color in proteins:
        lines.append(f"        {protein_def}")

    lines.append("    end")
    lines.append("")
    lines.append("    core --> core_proteins")
    lines.append("")

    # Add styles
    lines.append(
        "    style core_nucleotides fill:#e6f3ff,stroke:#0066cc,stroke-width:2px"
    )
    lines.append("    style core_proteins fill:#fff9e6,stroke:#856404,stroke-width:2px")
    lines.append("    style M_out fill:#ffcccc,stroke:#cc0000,stroke-width:3px")

    lines.append("```")
    return "\n".join(lines)


def generate_chamber_table(manifest: dict[str, Any]) -> str:
    """Generate Markdown table of path → chamber mappings."""
    chambers = manifest.get("allowed_chambers", {})

    if not chambers:
        return "_No sacred chambers defined._"

    lines = [
        "| Path | Chamber Name | Role |",
        "|------|--------------|------|",
    ]

    for path, chamber_name in sorted(chambers.items()):
        role = _infer_chamber_role(path, chamber_name)
        lines.append(f"| `{path}` | **{chamber_name}** | {role} |")

    return "\n".join(lines)


def generate_full_document(manifest: dict[str, Any]) -> str:
    """Generate complete markdown with diagram, table, and metadata."""
    lines = [
        "# Hive Geography: Sacred Chambers and Nucleotide Map",
        "",
        "**Status:** AUTO-GENERATED by `tools/map_hive.py` — DO NOT EDIT MANUALLY",
        "",
        "**Source of Truth:** `hive-manifest.yaml`",
        "",
        "**Last Generated:** (Timestamp will be added by map_hive.py on each run)",
        "",
        "---",
        "",
        "## Hive Folder Hierarchy",
        "",
        "This diagram shows the complete Hive geography:",
        "",
        generate_mermaid_hierarchy(manifest),
        "",
        "---",
        "",
        "## ATCG-M Nucleotide Locations",
        "",
        "The **five nucleotides** of the ATCG-M metabolism pattern:",
        "",
        "| Nucleotide | Role | Location | Implementation |",
        "|------------|------|----------|----------------|",
        "| **A (Aggregator)** | Senses signals | `core/src/hive/aggregator/` | Calls StorageSkill, MonitorSkill |",
        "| **T (Transformer)** | LLM reasoning | `core/src/hive/transformer/` | Calls ReasoningSkill |",
        "| **C (Connector)** | Executes actions | `core/src/hive/connector/` | Calls CryptoSkill, external APIs |",
        "| **G (Generator)** | Emits events | `core/src/hive/generator/` | Calls PulseSkill for NATS |",
        "| **M (Membrane)** | Immune system | `core/src/hive/membrane/` | Calls GuardSkill for validation |",
        "",
        "**Critical Membrane Position:** M appears **twice** in metabolism flow:",
        "- **M(in)** — Before Aggregator (validates inputs)",
        "- **M(out)** — Between Transformer and Connector (enforces business rules)",
        "",
        "---",
        "",
        "## Protein Locations and Capabilities",
        "",
        "All Proteins implement `SkillProtocol` (from `packages/aura-core/src/aura_core/dna.py`):",
        "",
        "| Protein | Location | Capabilities | Settings Class |",
        "|---------|----------|--------------|----------------|",
        "| **ReasoningSkill** | `core/src/hive/proteins/reasoning/` | negotiate, analyze, generate_embedding | LLMSettings |",
        "| **StorageSkill** | `core/src/hive/proteins/storage/` | db_query, db_write, vector_search, cache_get | DatabaseSettings |",
        "| **CryptoSkill** | `core/src/hive/proteins/crypto/` | verify_payment, create_offer, encrypt_secret | CryptoSettings |",
        "| **PulseSkill** | `core/src/hive/proteins/pulse/` | emit_heartbeat, schedule_deal | HeartbeatSettings |",
        "| **MonitorSkill** | `core/src/hive/proteins/monitor/` | fetch_metrics, health_check, increment_counter | ServerSettings |",
        "| **GuardSkill** | `core/src/hive/proteins/guard/` | validate_margin, validate_floor, sanitize_input | SafetySettings |",
        "",
        "**Protein Principle:** Nucleotides (A, T, C, G, M) are **Pure Orchestrators**. Proteins are **Pure Implementors**.",
        "",
        "---",
        "",
        "## Sacred Chambers Table",
        "",
        generate_chamber_table(manifest),
        "",
        "---",
        "",
        "## Regeneration Instructions",
        "",
        "To regenerate this file after modifying `hive-manifest.yaml`:",
        "",
        "```bash",
        "python tools/map_hive.py",
        "```",
        "",
        "**Options:**",
        "- `--manifest PATH` — Custom manifest path (default: `hive-manifest.yaml`)",
        "- `--output PATH` — Custom output path (default: `docs/visual/hive/geography.md`)",
        "- `--format markdown|mermaid` — Output format (default: markdown)",
        "",
        "---",
        "",
        "*For the glory of the Hive. 🐝*",
    ]

    return "\n".join(lines)


def _get_folder_emoji(folder: str) -> str:
    """Return emoji for macro folder."""
    emoji_map = {
        "core": "🧠",
        "api-gateway": "🚪",
        "frontend": "🖥️",
        "adapters": "🔌",
        "agents": "🐝",
        "proto": "📜",
        "docs": "📚",
        "tools": "🔧",
        "deploy": "🚀",
        "packages": "📦",
    }
    return emoji_map.get(folder, "📁")


def _infer_chamber_role(path: str, chamber_name: str) -> str:
    """Infer role from chamber name and path."""
    role_hints = {
        "EvolutionaryScrolls": "Database schema migrations",
        "ValidationPollen": "Unit and integration tests",
        "WorkerDirectives": "Utility scripts and orchestration",
        "HiveGate": "HTTP/JSON API gateway",
        "SacredCodex": "Configuration and settings",
        "ReasoningNucleus": "LLM reasoning engine",
        "SecurityCitadel": "Cryptographic operations",
        "HiveMembrane": "Input/output validation guards",
        "SensoryNexus": "Signal aggregation",
        "NeuralPulse": "Event emission",
        "MetabolicEngine": "ATCG-M orchestration",
        "HiveArmor": "Kubernetes/Docker deployments",
        "SacredScrolls": "Protobuf definitions",
        "ChroniclersArchive": "Documentation",
        "WorkerCells": "Autonomous agents",
        "KeeperCell": "Bee-keeper agent",
        "AuthorizedEnzyme": "Allowed implementation file",
        "HiveExtensions": "External adapters",
        "HiveWindow": "User interface",
        "ToolShed": "Development utilities",
        "OuterValidationPollen": "Root-level tests",
        "SharedNucleotides": "Shared libraries",
        "SpecializedProteins": "Skill implementations",
    }
    return role_hints.get(chamber_name, "Custom chamber")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Hive geography documentation from hive-manifest.yaml"
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("hive-manifest.yaml"),
        help="Path to hive-manifest.yaml (default: hive-manifest.yaml)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/visual/hive/geography.md"),
        help="Output path (default: docs/visual/hive/geography.md)",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "mermaid"],
        default="markdown",
        help="Output format (default: markdown)",
    )

    args = parser.parse_args()

    try:
        # Load manifest
        manifest = _load_manifest(args.manifest)

        # Generate output based on format
        if args.format == "mermaid":
            output = generate_mermaid_hierarchy(manifest)
        else:
            output = generate_full_document(manifest)

        # Ensure output directory exists
        args.output.parent.mkdir(parents=True, exist_ok=True)

        # Write output
        with args.output.open("w") as f:
            f.write(output)

        print(f"✅ Generated: {args.output}")
        print(
            f"📊 Processed {len(manifest.get('allowed_chambers', {}))} sacred chambers"
        )
        print(f"🧬 Mapped {len(manifest.get('macro_atcg_folders', []))} macro folders")

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
