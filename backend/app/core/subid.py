"""Codec sub_id v1 — xem docs/07-du-lieu.md mục 1.

utm_content = s1-s2-s3-s4-s5
  s1 = {version}{type}   version='1'; type: u=click user, l=link user (dự phòng), p=bài Muse AI, x=khác
  s2 = id chủ sở hữu (user_id hoặc post_id), base36, 1-8 ký tự
  s3 = click_id / link_id / mã fanpage, base36, 1-8 ký tự
  s4 = chữ ký 3 ký tự base36 = HMAC-SHA256(secret, "s1-s2-s3")
  s5 = dự trữ, rỗng ở v1
Mỗi slot chỉ [0-9a-z], không chứa '-'. Không chứa dữ liệu cá nhân.
"""
from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass

VERSION = "1"
TYPES = {"u": "user_click", "l": "user_link", "p": "post", "x": "other"}
ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
MAX_SLOT = 8          # độ dài tối đa s2, s3
SIG_LEN = 3
MAX_TOTAL = 32        # giới hạn tự đặt, thấp hơn nhiều so với mức Shopee đã giữ nguyên khi test
MAX_ID = 36 ** MAX_SLOT - 1
_SLOT_RE = re.compile(r"^[0-9a-z]*$")


class SubIdError(ValueError):
    pass


@dataclass(frozen=True)
class Decoded:
    status: str                 # "ok" | "invalid" | "legacy" | "empty"
    type: str | None = None     # u|l|p|x
    kind: str | None = None     # user_click|user_link|post|other
    owner: int | None = None
    ref: int | None = None
    reason: str | None = None


def to_base36(n: int) -> str:
    if not isinstance(n, int) or isinstance(n, bool) or n < 0:
        raise SubIdError("id phải là số nguyên không âm")
    if n > MAX_ID:
        raise SubIdError(f"id vượt giới hạn {MAX_ID}")
    if n == 0:
        return "0"
    out = []
    while n:
        n, r = divmod(n, 36)
        out.append(ALPHABET[r])
    return "".join(reversed(out))


def _secret_bytes(secret) -> bytes:
    b = secret.encode() if isinstance(secret, str) else bytes(secret or b"")
    if len(b) < 16:
        raise SubIdError("SUBID_SECRET phải có ít nhất 16 byte")
    return b


def _sign(secret, payload: str) -> str:
    digest = hmac.new(_secret_bytes(secret), payload.encode(), hashlib.sha256).digest()
    n = int.from_bytes(digest[:4], "big") % (36 ** SIG_LEN)
    return to_base36(n).rjust(SIG_LEN, "0")


def encode(type_: str, owner_id: int, ref_id: int, secret) -> str:
    if type_ not in TYPES:
        raise SubIdError(f"type không hợp lệ: {type_!r}")
    s1 = VERSION + type_
    s2, s3 = to_base36(owner_id), to_base36(ref_id)
    sig = _sign(secret, f"{s1}-{s2}-{s3}")
    out = f"{s1}-{s2}-{s3}-{sig}-"
    assert len(out) <= MAX_TOTAL and "--" not in out[:-1]
    return out


def decode(utm_content: str | None, secret) -> Decoded:
    """Không bao giờ ném lỗi vì dữ liệu từ Shopee; trả status để caller đưa vào đơn mồ côi.
    `secret` là một khóa HOẶC danh sách khóa (khóa hiện hành trước, rồi khóa cũ sau khi đổi khóa, T-018). Chữ ký chỉ 3 ký tự nên
    mỗi khóa thêm làm tăng xác suất khớp nhầm ~1/46656: tối đa MAX_PREVIOUS_KEYS khóa cũ (config) và caller vẫn phải kiểm sở hữu."""
    raw = (utm_content or "").strip()
    if raw.strip("-") == "":
        return Decoded("empty", reason="không có sub_id")
    parts = raw.split("-")
    if len(parts) != 5 or not parts[0] or parts[0][0] != VERSION:
        return Decoded("legacy", reason="không theo quy ước v1")
    s1, s2, s3, s4, s5 = parts
    if len(s1) != 2 or s1[1] not in TYPES:
        return Decoded("invalid", reason="s1 sai")
    if not all(_SLOT_RE.match(p) for p in parts) or s5 != "":
        return Decoded("invalid", reason="ký tự hoặc s5 sai")
    if not (1 <= len(s2) <= MAX_SLOT and 1 <= len(s3) <= MAX_SLOT and len(s4) == SIG_LEN):
        return Decoded("invalid", reason="độ dài slot sai")
    keys = secret if isinstance(secret, (list, tuple)) else (secret,)
    payload = f"{s1}-{s2}-{s3}"
    if not any([hmac.compare_digest(_sign(k, payload), s4) for k in keys]):      # không thoát sớm: thời gian không lộ khóa nào khớp
        return Decoded("invalid", reason="chữ ký sai")
    return Decoded("ok", type=s1[1], kind=TYPES[s1[1]], owner=int(s2, 36), ref=int(s3, 36))
