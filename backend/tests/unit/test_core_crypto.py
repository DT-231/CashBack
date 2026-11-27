"""AES-256-GCM cho số tài khoản: đúng, chống sửa, gắn với chủ sở hữu, đổi khóa được, từ chối khóa yếu."""
import base64
import os

import pytest

from app.core.config import ConfigError, Settings
from app.core.crypto import BankCipher, CryptoError, keyring, parse_key


def key(seed: int | None = None) -> str:
    return base64.urlsafe_b64encode(os.urandom(32) if seed is None else bytes([seed]) * 32).decode()


def settings(**kw):
    return Settings(withdrawals_enabled=True, bank_enc_key=kw.pop("k", key()), **kw)


def test_roundtrip_stores_key_id_and_hides_plaintext():
    c = BankCipher(settings(bank_enc_key_id="k7"))
    kid, token = c.encrypt("0123456789012", 5)
    assert kid == "k7" and "0123456789012" not in token and "0123" not in token
    assert c.decrypt(kid, token, 5) == "0123456789012"
    assert c.encrypt("0123456789012", 5)[1] != token                    # nonce ngẫu nhiên mỗi lần


def test_ciphertext_is_bound_to_the_owner_and_tamper_proof():
    c = BankCipher(settings())
    kid, token = c.encrypt("0123456789", 5)
    with pytest.raises(CryptoError):
        c.decrypt(kid, token, 6)                                        # chép bản mã sang dòng của người khác
    raw = bytearray(base64.urlsafe_b64decode(token))
    raw[-1] ^= 1
    with pytest.raises(CryptoError):
        c.decrypt(kid, base64.urlsafe_b64encode(bytes(raw)).decode(), 5)
    with pytest.raises(CryptoError):
        c.decrypt(kid, "khong-phai-base64!!", 5)
    with pytest.raises(CryptoError):
        c.decrypt("unknown", token, 5)


def test_wrong_key_fails_and_errors_do_not_leak_data():
    kid, token = BankCipher(settings(k=key(), bank_enc_key_id="k1")).encrypt("0123456789", 5)
    other = BankCipher(settings(k=key(), bank_enc_key_id="k1"))
    with pytest.raises(CryptoError) as e:
        other.decrypt(kid, token, 5)
    assert "0123456789" not in str(e.value) and token not in str(e.value)


def test_rotation_new_key_encrypts_old_key_still_decrypts():
    old = key()
    kid, token = BankCipher(settings(k=old, bank_enc_key_id="k1")).encrypt("0123456789", 5)
    rotated = BankCipher(settings(k=key(), bank_enc_key_id="k2", bank_enc_old_keys=f"k1:{old}"))
    assert rotated.decrypt(kid, token, 5) == "0123456789"               # bản mã k1 vẫn đọc được
    assert rotated.encrypt("0123456789", 5)[0] == "k2"                  # bản mới dùng khóa mới
    with pytest.raises(CryptoError):
        BankCipher(settings(k=key(), bank_enc_key_id="k2")).decrypt(kid, token, 5)   # quên khóa cũ => không giải mã được


@pytest.mark.parametrize("bad", ["", "abc", key(1), base64.urlsafe_b64encode(os.urandom(31)).decode(),
                                 base64.urlsafe_b64encode(os.urandom(33)).decode(), "!!!not-base64!!!",
                                 base64.urlsafe_b64encode(bytes(range(8)) * 4).decode()])
def test_weak_or_malformed_keys_are_rejected(bad):
    with pytest.raises(ConfigError):
        keyring(Settings(bank_enc_key=bad))
    if bad:
        with pytest.raises(ConfigError):
            parse_key(bad)


def test_old_keys_format_and_duplicate_ids_rejected():
    for old in ("nocolon", "k1:" + key()):                              # thiếu id; trùng key_id hiện hành k1
        with pytest.raises(ConfigError):
            keyring(settings(bank_enc_old_keys=old))
    with pytest.raises(ConfigError):
        keyring(settings(bank_enc_key_id="bad id!"))


def test_startup_refuses_withdrawals_without_a_strong_key():
    with pytest.raises(ConfigError, match="BANK_ENC_KEY"):
        Settings(withdrawals_enabled=True).validate_for_serving()
    with pytest.raises(ConfigError):
        Settings(withdrawals_enabled=True, bank_enc_key=key(1)).validate_for_serving()
    Settings(withdrawals_enabled=True, bank_enc_key=key()).validate_for_serving()
    Settings().validate_for_serving()                                    # rút tiền tắt: không cần khóa


def test_key_never_appears_in_exception_messages():
    k = key(3)
    try:
        keyring(Settings(bank_enc_key=k))
    except ConfigError as e:
        assert k not in str(e)
