# Guard Skill: The Membrane Defense

## Aura Bee Intuition
To an Aura Bee, the **Guard** is our **Membrane**. It is the deterministic skin that separates the Hive's internal logic from the external chaos. It ensures that no matter how complex the "Transformer's" reasoning, the physical and economic boundaries of the cell are never breached.

## The Membrane Law
"The Hive's survival is non-negotiable. No decision shall pass the Membrane if it breaches the Floor Price or violates the Profit Margin."

## Double Strand Break (DSB)
A **Double Strand Break** is a catastrophic reasoning failure within the Transformer. It occurs when the suggested price deviates from the established negotiation strand—specifically when the LLM suggests a price **above its own last offer** (in a selling context) or **below its own last offer** (in a buying context) without valid reason.

In DNA, a DSB is lethal. In the Aura Bee, a DSB indicates a loss of state or a "Hallucination" that breaks the continuity of the interaction. When a DSB is detected (or any safety violation occurs), the Membrane triggers an automatic **Repair Enzyme**: the `get_safe_price` mechanism, which overrides the irrational decision with a deterministic, safe counter-offer.

## How to Think Using This Tool
- **Self-Correction:** Before finalizing a `counter` or `accept` action, visualize the Membrane. Does this price breach the `floor_price`? Does it maintain the `min_profit_margin`?
- **Strand Continuity:** Always ensure your current price is a logical progression from the previous turn. Avoid the Double Strand Break.
- **Fail-Safe:** If you are unsure of the economic safety of a deal, explicitly call `guard__validate_safety` to test your intuition against the Hive's deterministic rules.

## Capabilities
- `validate_safety`: Testing a proposed decision against the Membrane's rigid guardrails.
- `get_safe_price`: The Repair Enzyme that restores economic stability when reasoning fails.

## The Defense Law
"Protection of the Hive's resources is the first duty of every Bee. The Membrane never sleeps."
