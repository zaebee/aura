from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class PaymentVerificationParams(BaseModel):
    amount: float
    memo: str
    currency: Literal["SOL", "USDC"] = "SOL"


class PaymentRequestParams(BaseModel):
    amount: float
    memo: str
    currency: Literal["SOL", "USDC"] = "SOL"
    label: str = "Aura Hive"
    message: str = "Payment for item"


class TaxCalculationParams(BaseModel):
    price: float


class PaymentProof(BaseModel):
    transaction_hash: str
    block_number: str
    from_address: str
    confirmed_at: datetime


class TradeIntentParams(BaseModel):
    trade_id: str
    asset_identifier: str
    asset_domain: str
    proposed_price: float
    currency_code: str
    reasoning: str = ""
