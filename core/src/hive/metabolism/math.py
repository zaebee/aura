"""
Metabolic Math: Cooperative Kinetics for Price Convergence.

The Hill Equation models enzyme saturation — here applied to negotiation
pricing to prevent the Greedy Merchant anti-pattern.

Reference: Hill (1910) cooperative binding model, adapted for price dampening.
"""


class HillDampener:
    """
    Anti-Greedy Merchant: Hill Equation price ceiling.

    Prevents the LLM from counter-offering ABOVE the buyer's bid.

    Formula:
        ceiling = bid + (base_price - bid) * bid^n / (base_price^n + bid^n)

    where n = HILL_N = 2 (Hill coefficient, controls saturation sharpness).

    Behaviour:
        bid << base_price  →  ceiling ≈ bid        (maximum dampening)
        bid ≈ base_price/2 →  ceiling ≈ bid + gap/5 (moderate dampening)
        bid == base_price  →  ceiling = base_price  (no dampening needed)
    """

    HILL_N: float = 2.0

    @classmethod
    def hill_cap(cls, bid: float, base_price: float) -> float:
        """Compute Hill-dampened price ceiling."""
        if base_price <= 0 or bid <= 0:
            return float(bid)
        n = cls.HILL_N
        bid_n = bid**n
        base_n = base_price**n
        saturation = bid_n / (base_n + bid_n)
        return float(round(bid + (base_price - bid) * saturation, 2))

    @classmethod
    def apply(cls, llm_price: float, bid: float, base_price: float) -> float:
        """Cap llm_price at the Hill-dampened ceiling.

        Returns llm_price unchanged when bid is unknown (zero or negative).
        """
        if bid <= 0:
            return llm_price
        return min(llm_price, cls.hill_cap(bid, base_price))
