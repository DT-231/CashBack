from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StrictInt, field_validator

IdemKey = Annotated[str, Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")]


class BankAccountIn(BaseModel):
    bank_code: str = Field(pattern=r"^[A-Za-z0-9]{2,12}$")
    account_no: str = Field(pattern=r"^[0-9]{6,20}$", repr=False)
    account_name: str = Field(min_length=2, max_length=60)

    @field_validator("bank_code")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    @field_validator("account_name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 2 or not all(ch.isalpha() or ch == " " for ch in v):
            raise ValueError("tên chủ tài khoản chỉ gồm chữ và khoảng trắng")
        return v.upper()


class BankAccountOut(BaseModel):
    """Người dùng chỉ thấy 4 số cuối. Số đầy đủ không bao giờ có trong response này."""
    id: int
    bank_code: str
    account_name: str
    last4: str
    usable_from: datetime
    created_at: datetime


class WithdrawalIn(BaseModel):
    amount_vnd: StrictInt = Field(gt=0)
    bank_account_id: StrictInt


class WithdrawalOut(BaseModel):
    id: int
    amount_vnd: int
    status: str
    bank_account_id: int | None
    bank_code: str | None = None
    last4: str | None = None
    provider_ref: str | None = None
    decided_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class AdminWithdrawalOut(WithdrawalOut):
    user_id: int
    approved_by: int | None = None
    approved_at: datetime | None = None
    paid_by: int | None = None
    paid_at: datetime | None = None


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class MarkPaidIn(BaseModel):
    provider_ref: str = Field(min_length=4, max_length=100, pattern=r"^[A-Za-z0-9._\-/]+$")


class PayoutAccountOut(BaseModel):
    """CHỈ trả cho admin ở endpoint chi trả; mỗi lần trả đều ghi audit `payout.view_account`."""
    withdrawal_id: int
    amount_vnd: int
    bank_code: str
    account_no: str
    account_name: str
