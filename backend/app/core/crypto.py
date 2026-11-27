"""Mã hóa có xác thực (AES-256-GCM) cho dữ liệu nhạy cảm lưu DB (số tài khoản ngân hàng).

- Mỗi giá trị lưu kèm `key_id` (phiên bản khóa) để đổi khóa được: khóa mới mã hóa, khóa cũ (BANK_ENC_OLD_KEYS) vẫn giải mã được.
- AAD gắn bản mã với chủ sở hữu (`bank_account:<user_id>`): chép bản mã sang dòng của người khác thì giải mã thất bại.
- Khóa là 32 byte ngẫu nhiên, base64 (tạo: python3 -c "import secrets,base64;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())").
  KHÔNG suy khóa từ mật khẩu/chuỗi tùy ý; khóa yếu (không đủ 32 byte, ít ký tự khác nhau) bị từ chối.
- Mất khóa = không giải mã được = không trả tiền được cho ai: sao lưu NGOÀI `.env` (docs/runbooks/withdrawals.md).
"""
from __future__ import annotations

import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import ConfigError, Settings

_NONCE = 12


class CryptoError(Exception):
    """Không giải mã được (khóa sai, bản mã bị sửa, hoặc bản mã thuộc người khác). Thông điệp không chứa dữ liệu."""


def parse_key(b64: str) -> bytes:
    try:
        raw = base64.urlsafe_b64decode(b64.strip() + "=" * (-len(b64.strip()) % 4))
    except (binascii.Error, ValueError):
        raise ConfigError("khóa mã hóa không phải base64 hợp lệ") from None
    if len(raw) != 32:
        raise ConfigError("khóa mã hóa phải đúng 32 byte (base64 của 32 byte ngẫu nhiên)")
    if len(set(raw)) < 16:
        raise ConfigError("khóa mã hóa quá yếu (không giống 32 byte ngẫu nhiên)")
    return raw


def keyring(settings: Settings) -> tuple[str, dict[str, bytes]]:
    """(key_id hiện hành, {key_id: khóa}). Ném ConfigError nếu thiếu/yếu."""
    cur_id = settings.bank_enc_key_id.strip()
    cur = settings.bank_enc_key.get_secret_value()
    if not cur_id or not all(c.isalnum() or c in "-_" for c in cur_id) or len(cur_id) > 20:
        raise ConfigError("BANK_ENC_KEY_ID phải là chữ/số/-/_ (tối đa 20 ký tự)")
    if not cur.strip():
        raise ConfigError("Thiếu BANK_ENC_KEY")
    ring = {cur_id: parse_key(cur)}
    old = settings.bank_enc_old_keys.get_secret_value().strip()
    for part in filter(None, (x.strip() for x in old.split(","))):
        kid, _, key = part.partition(":")
        if not key or kid in ring:
            raise ConfigError("BANK_ENC_OLD_KEYS phải dạng id:khóa,id:khóa và không trùng key_id")
        ring[kid.strip()] = parse_key(key)
    return cur_id, ring


class BankCipher:
    """Mã hóa theo MỤC ĐÍCH: AAD gồm `purpose` và chủ sở hữu nên bản mã của mục đích này không giải mã được ở mục đích khác
    (số tài khoản ngân hàng vs bí mật TOTP). Dùng chung một bộ khóa BANK_ENC_KEY (một thứ để sao lưu)."""
    purpose = "bank_account"

    def __init__(self, settings: Settings):
        self.key_id, self._ring = keyring(settings)

    def _aad(self, user_id: int) -> bytes:
        return f"{self.purpose}:{user_id}".encode()

    def encrypt(self, plaintext: str, user_id: int) -> tuple[str, str]:
        """(key_id, token). token = base64(nonce || ciphertext || tag)."""
        nonce = os.urandom(_NONCE)
        ct = AESGCM(self._ring[self.key_id]).encrypt(nonce, plaintext.encode(), self._aad(user_id))
        return self.key_id, base64.urlsafe_b64encode(nonce + ct).decode()

    def decrypt(self, key_id: str, token: str, user_id: int) -> str:
        key = self._ring.get(key_id)
        if key is None:
            raise CryptoError("không có khóa cho key_id này")
        try:
            raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
            return AESGCM(key).decrypt(raw[:_NONCE], raw[_NONCE:], self._aad(user_id)).decode()
        except (InvalidTag, binascii.Error, ValueError):
            raise CryptoError("giải mã thất bại") from None


class MfaCipher(BankCipher):
    """Bí mật TOTP của người dùng (cùng khóa, khác AAD)."""
    purpose = "mfa_secret"


class ShopeeCookieCipher(BankCipher):
    """Cookie phiên Shopee Affiliate (cùng khóa, khác AAD). Chủ sở hữu cố định = 1 (một phiên dùng chung)."""
    purpose = "shopee_cookie"
