"""
DSPy signatures for Aura negotiation engine.

Defines the input/output structure for the self-optimizing negotiation module.
"""

import dspy


class Negotiate(dspy.Signature):
    """Negotiation decision signature with economic reasoning.

    This signature defines the structure for the DSPy negotiation module,
    including economic context, negotiation history, and structured output.
    """

    input_bid = dspy.InputField(desc="Buyer's current offer amount in USD")
    context = dspy.InputField(
        desc="""Economic context as JSON string containing:
        {
            base_price: float,        # Standard listing price
            floor_price: float,       # Minimum acceptable price (hidden)
            occupancy: str,           # Current occupancy level (high/medium/low)
            value_add_inventory: List[Dict[str, Any]], # Available perks
            system_constraints: List[str] # Real-time system constraints (e.g. HIGH_LOAD)
        }"""
    )
    history = dspy.InputField(
        desc="Previous negotiation turns as JSON list of {bid, response} pairs"
    )
    thought = dspy.OutputField(
        desc="""Ona's internal strategic analysis (monologue).
        Analyzes margin, occupancy, and system constraints to derive the best strategy.
        This is NOT shown to the user."""
    )
    action = dspy.OutputField(
        desc="""Jules' external action. MUST be a JSON-formatted string:
        {
            "action": str,              # One of: 'accept', 'counter', 'reject', 'ui_required'
            "price": float,             # Final price or counter offer
            "message": str              # Professional message to buyer agent
        }"""
    )
