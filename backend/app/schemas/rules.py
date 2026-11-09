import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from agents.schemas.shop import FULL_SHARE_BPS, PayeeRoute


class PayeeIn(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    route: PayeeRoute
    # A chain id for a withdraw ("base", "eth", ...); none for a NEAR transfer.
    chain: str | None = Field(default=None, max_length=24)
    address: str = Field(min_length=2, max_length=128)
    memo: str | None = Field(default=None, max_length=128)
    share_bps: int = Field(gt=0, le=FULL_SHARE_BPS)


class PayeesIn(BaseModel):
    payees: list[PayeeIn]


class PayeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    route: PayeeRoute
    chain: str | None
    address: str
    memo: str | None
    share_bps: int


class BudgetIn(BaseModel):
    daily_budget_usd: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class PlatformTermsOut(BaseModel):
    """What owners see before signing: the fee, its ceiling, and where it goes."""
    model_config = ConfigDict(from_attributes=True)

    fee_bps: int
    max_fee_bps: int
    fee_account: str
