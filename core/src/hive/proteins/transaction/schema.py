from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class PaymentVerificationParams(BaseModel):
    amount: float
    memo: str
    currency: Literal["SOL", "USDC"] = "SOL"


class PaymentProof(BaseModel):
    transaction_hash: str
    block_number: str
    from_address: str
    confirmed_at: datetime


class EncryptSecretParams(BaseModel):
    secret: str


class DecryptSecretParams(BaseModel):
    encrypted_secret: str


class ConvertPriceParams(BaseModel):
    usd_amount: float
    currency: str | None = None
