from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from agents.schemas.shop import FULL_SHARE_BPS


class PlatformOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fee_bps: int
    max_fee_bps: int
    fee_account: str
    updated_at: datetime


class FeeUpdate(BaseModel):
    fee_bps: int = Field(ge=0, le=FULL_SHARE_BPS)
