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
            value_add_inventory: List[Dict[str, Any]]  # Available perks with cost/value
        }"""
    )
    history = dspy.InputField(
        desc="Previous negotiation turns as JSON list of {bid, response} pairs"
    )
    reasoning = dspy.OutputField(
        desc="""Strategic reasoning about the decision, including:
        - Margin analysis
        - Occupancy considerations
        - Value-add utilization strategy
        - Competitive positioning"""
    )
    response = dspy.OutputField(
        desc="""JSON-formatted action response containing:
        {
            action: str,              # One of: 'accept', 'counter', 'reject'
            price: float,             # Final price (accept) or counter offer (counter)
            message: str              # Professional message to buyer agent
        }"""
    )
