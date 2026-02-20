from pydantic import BaseModel, Field


class SafetySettings(BaseModel):
    """
    Guardrail configurations for Aura's economic decisions.
    Protects against hallucinations and bad deals.
    """

    min_profit_margin: float = 0.10  # 10% minimum profit margin
    max_discount_percent: float = 0.30  # Max 30% discount from base price
    ui_trigger_price: float = 1000.0  # High-value threshold for UI confirmation
    max_x402_payment: float = 5.0  # Max USDC per autonomous x402 payment
    allowed_addons: list[str] = Field(
        default_factory=lambda: ["Breakfast", "Late checkout", "Room upgrade"]
    )
