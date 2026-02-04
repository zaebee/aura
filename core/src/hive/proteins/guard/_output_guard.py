from config import settings

class SafetyViolation(Exception):
    """Raised when a negotiation decision violates safety guardrails."""
    pass

class OutputGuard:
    """
    Deterministic safety layer for Aura Core.
    Protects against economic hallucinations and floor price breaches.
    """
    def validate_decision(self, decision: dict, context: dict) -> bool:
        action = decision.get("action")
        offered_price = decision.get("price", 0.0)
        floor_price = context.get("floor_price", 0.0)
        internal_cost = context.get("internal_cost", 0.0)

        if offered_price > 0:
            margin = (offered_price - internal_cost) / offered_price
            if margin < settings.safety.min_profit_margin:
                raise SafetyViolation("Minimum profit margin violation")
        elif action in ["accept", "counter"]:
            raise SafetyViolation("Invalid offered price")

        if action in ["accept", "counter"] and offered_price < floor_price:
            raise SafetyViolation("Floor price violation")
        return True
