from pydantic import BaseModel, Field


class SafetySettings(BaseModel):
    """
    Guardrail configurations for Aura's economic decisions.
    Protects against hallucinations and bad deals.
    DNA defining the deterministic boundaries of negotiation.
    """

    min_profit_margin: float = Field(default=0.10, description="Minimum profit margin")
    max_discount_percent: float = Field(default=0.30, description="Max discount percent")
    allowed_addons: list[str] = Field(
        default_factory=lambda: ["Breakfast", "Late checkout", "Room upgrade"],
        description="Allowed add-ons"
    )
