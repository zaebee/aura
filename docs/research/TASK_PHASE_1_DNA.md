# Task: Aura-Verum Phase 1 - Ontological Alignment (DNA)

## Objective
Translate Aura's "DNA" from Protobuf definitions into native Verum types, grounding the system in the Unitary Holonomic Monism (UHM) ontology. This move eliminates "metabolic toxicity" and enables formal verification of the system's "vitality."

## Requirements

1. **Native Verum DNA (`aura/core/dna.vr`)**:
    - Translate `metabolism.proto` and `assets.proto` into Verum types.
    - Implement "Semantic Honesty": Use `Text` instead of `string`, `List<T>` instead of `repeated`, and `Map<K, V>` instead of `map`.
    - Map `Signal`, `Context`, `Intent`, `Observation`, and `Event` to Verum records/variants.

2. **UHM Primitive Implementation**:
    - **CoherenceMatrix**: Define as `Tensor<Complex, [7, 7]>` with invariants:
        - `self.is_hermitian()`
        - `self.trace() == 1.0`
    - **Purity**: Define as a refinement type: `type Purity is Float { self >= 2.0/7.0 }`.
    - **Valence**: Define as the time-derivative of purity (dP/dτ).

3. **Metabolic Protocols (Capabilities)**:
    - Define `context protocol` for the core "nucleotides": `Aggregator`, `Transformer`, `Connector`, `Generator`, and `Membrane`.
    - Ensure `Coherence` is a required context for the metabolic loop.

4. **The No-Zombie Guarantee**:
    - Implement the `execute_cycle` function with a formal post-condition:
      ```verum
      @verify(formal)
      fn execute_cycle(signal: &Signal)
          using [Aggregator, Transformer, Connector, Generator, Membrane, Coherence]
          where ensures Coherence.purity() >= 2.0/7.0;
      ```

## References
- See `docs/research/UHM_DNA_ONTOLOGY.vr` for initial type drafts.
- See `docs/research/METABOLISM_MAPPING.vr` for the context mapping.
- See `docs/research/ALIVE_UHM_BRIDGE.md` for the Python PoC logic.

## Goal
A set of `.vr` files that pass `verum check` and provide a mathematical proof that the Hive is "alive" (coherent) according to UHM.
