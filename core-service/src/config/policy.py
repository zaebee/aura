from pydantic import BaseModel, Field


class SafetySettings(BaseModel):
    """
    Guardrail configurations for Aura's economic decisions.
    Protects against hallucinations and bad deals.
    """

    min_profit_margin: float = 0.10  # 10% minimum profit margin
    max_discount_percent: float = 0.30  # Max 30% discount from base price
    allowed_addons: list[str] = Field(
        default_factory=lambda: ["Breakfast", "Late checkout", "Room upgrade"]
    )
