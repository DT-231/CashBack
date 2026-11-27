"""Kiểu dữ liệu vào/ra của auth."""
import re

from pydantic import BaseModel, Field, field_validator, model_validator

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _norm_email(v: str) -> str:
    v = v.strip().lower()
    if len(v) > 254 or not _EMAIL.match(v):
        raise ValueError("email không hợp lệ")
    return v


class LoginIn(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=128)

    _email = field_validator("email")(_norm_email)


class RegisterIn(LoginIn):
    password: str = Field(min_length=10, max_length=128)


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=10, max_length=200)


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(BaseModel):
    id: int
    email: str
    role: str
    status: str


class MfaSetupOut(BaseModel):
    """Hiện MỘT lần lúc thiết lập: bí mật để nhập vào ứng dụng xác thực. Không có endpoint nào trả lại nó."""
    secret: str
    otpauth_uri: str


class MfaCodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class MfaVerifyIn(BaseModel):
    code: str | None = Field(default=None, min_length=6, max_length=8)
    recovery_code: str | None = Field(default=None, min_length=8, max_length=24)

    @model_validator(mode="after")
    def _exactly_one(self):
        if (self.code is None) == (self.recovery_code is None):
            raise ValueError("gửi đúng một trong hai: code hoặc recovery_code")
        return self


class MfaEnableOut(BaseModel):
    """Mã khôi phục hiện MỘT lần; server chỉ lưu bản băm."""
    recovery_codes: list[str]


class MfaStatusOut(BaseModel):
    enabled: bool          # đã kích hoạt TOTP
    pending: bool          # đã tạo bí mật nhưng chưa kích hoạt
    verified: bool         # phiên hiện tại đã nhập mã gần đây (còn trong mfa_max_age_hours)
