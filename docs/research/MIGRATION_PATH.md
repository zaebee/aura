# Aura -> Verum Migration: Step-by-Step Honesty

This document outlines the phased migration of Aura Core/DNA to the Verum programming language, guided by the Unitary Holonomic Monism (UHM) ontology.

## Phase 1: Ontological Alignment (DNA)
**Goal**: Replace Protobuf-based DNA with Verum's Refined and Dependent Types.

- **Action**: Translate `metabolism.proto` and `dna.proto` into Verum `.vr` types.
- **UHM Integration**: Introduce `CoherenceMatrix`, `Purity`, and `Valence` as first-class types.
- **Honesty**: Use Verum's `Text`, `List`, and `Map` to replace implementation-leaky types.
- **Benefit**: Eliminate "Metabolic Toxicity" (JSON-encoded hacks) via strict type-level invariants.

## Phase 2: Metabolic Alignment (Capabilities)
**Goal**: Port the Metabolic Engine to Verum's Context System.

- **Action**: Implement the `MetabolicLoop` as a Verum function with `using [Aggregator, Transformer, ...]`.
- **Worker Strategy**: Offload GPU-heavy perception/reasoning to dedicated "Kinetic Workers" via Verum's FFI or VBC-native opcodes.
- **UHM Integration**: Inject the `Coherence` context into every metabolic cycle.
- **Benefit**: Explicit effect tracking. No more hidden globals or ambient state in proteins.

## Phase 3: Certified Vitality (Formal Verification)
**Goal**: Prove the No-Zombie Theorem and system-level invariants.

- **Action**: Use Verum's Proof DSL (`theorem`, `lemma`) to verify the regeneration mechanism.
- **Invariant**: `ensures Coherence.purity() >= 2/7`.
- **SMT Routing**: Discharge complex safety proofs (e.g., pricing floor vs. UHM hedonic valence) to the SMT backend.
- **Benefit**: Absolute certainty of the Hive's "Self-Modeling" integrity.

## Phase 4: Full Binary Bloodstream
**Goal**: Execute entirely within the Verum θ+ (Execution Environment).

- **Action**: Compile the entire core to VBC (Verum Bytecode).
- **Execution**: Run under the Verum runtime without a Python or Rust-std dependency.
- **Benefit**: ~15ns CBGR safety checks. Deterministic memory management and zero-FFI syscalls.
