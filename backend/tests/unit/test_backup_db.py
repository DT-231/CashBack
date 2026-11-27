"""backup_db.py: mã hóa theo khối chống sửa/cắt/đảo khối, xoay vòng, pg_dump/pg_restore giả (không cần DB)."""
import base64
import importlib.util
import os
import stat
import struct
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("backup_db", SCRIPTS / "backup_db.py")
bk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bk)

KEY_B64 = base64.urlsafe_b64encode(os.urandom(32)).decode()
KEY = base64.urlsafe_b64decode(KEY_B64)
DSN = "postgresql+psycopg://appuser:S3cr3t%21pw@10.0.0.5:5433/mydb"


def enc(tmp_path, data: bytes, key=KEY):
    src, dst = tmp_path / "plain", tmp_path / "x.enc"
    src.write_bytes(data)
    return bk.encrypt_file(src, dst, key), dst


@pytest.mark.parametrize("size", [0, 1, bk.CHUNK - 1, bk.CHUNK, bk.CHUNK + 1, 2 * bk.CHUNK + 5])
def test_roundtrip_sizes_including_chunk_boundaries(tmp_path, size):
    data = os.urandom(size)
    digest, dst = enc(tmp_path, data)
    out = tmp_path / "out"
    assert bk.decrypt_file(dst, out, KEY) == digest and out.read_bytes() == data
    assert bk.decrypt_file(dst, None, KEY) == digest
    if size >= 64:
        assert data[:64] not in dst.read_bytes()


def blob_offsets(path: Path):
    raw, off, out = path.read_bytes(), 12, []
    while off < len(raw):
        (n,) = struct.unpack(">I", raw[off:off + 4])
        out.append((off, 4 + n))
        off += 4 + n
    return raw, out


def test_wrong_key_flip_truncate_append_and_reorder_are_all_detected(tmp_path):
    _, dst = enc(tmp_path, os.urandom(2 * bk.CHUNK + 100))
    raw, chunks = blob_offsets(dst)
    assert len(chunks) == 3
    bad = tmp_path / "bad"

    def fails(content: bytes, key=KEY):
        bad.write_bytes(content)
        with pytest.raises(bk.BackupError):
            bk.decrypt_file(bad, None, key)

    fails(raw, os.urandom(32))                                                         # sai khóa
    fails(raw[:100] + bytes([raw[100] ^ 1]) + raw[101:])                                # sửa một bit giữa khối 1
    fails(raw[:-1] + bytes([raw[-1] ^ 1]))                                              # sửa bit cuối
    fails(raw[: chunks[2][0]])                                                          # cắt đúng ranh giới khối (mất khối cuối)
    fails(raw[:-10])                                                                    # cắt giữa khối
    fails(raw + raw[chunks[2][0]:])                                                     # nối thêm khối thừa sau khối cuối
    swapped = raw[:12] + raw[chunks[1][0]:chunks[1][0] + chunks[1][1]] + raw[chunks[0][0]:chunks[0][0] + chunks[0][1]] + raw[chunks[2][0]:]
    fails(swapped)                                                                      # đảo khối
    fails(b"XXXX" + raw[4:])                                                            # sai magic
    fails(raw[:5])                                                                      # header cụt
    fails(raw[:12])                                                                     # chỉ có header, không có khối nào
    fails(raw[:12] + b"\x00\x00")                                                       # độ dài khối cụt


def test_two_encryptions_of_the_same_data_differ(tmp_path):
    _, a = enc(tmp_path, b"hello world" * 10)
    d2 = tmp_path / "b.enc"
    bk.encrypt_file(tmp_path / "plain", d2, KEY)
    assert a.read_bytes() != d2.read_bytes()                                            # tiền tố nonce ngẫu nhiên mỗi lần


def test_rotate_keeps_the_newest_n(tmp_path):
    for i in range(5):
        (tmp_path / f"backup-2026010{i}-000000{bk.SUFFIX}").write_bytes(b"x")
    (tmp_path / "keepme.txt").write_text("x")
    gone = bk.rotate(tmp_path, 2)
    assert sorted(p.name for p in tmp_path.glob("backup-*")) == [f"backup-2026010{i}-000000{bk.SUFFIX}" for i in (3, 4)]
    assert len(gone) == 3 and (tmp_path / "keepme.txt").exists()
    assert bk.rotate(tmp_path, 0) == []                                                 # keep=0: không xóa gì (tránh xóa sạch do cấu hình sai)


def make_stub(tmp_path, name, body):
    p = tmp_path / name
    p.write_text("#!/bin/bash\n" + body)
    p.chmod(0o755)
    return p


def test_backup_with_a_fake_pg_dump_encrypts_hides_the_password_and_leaves_no_plaintext(tmp_path, monkeypatch):
    marker = b"PLAINTEXT-MARKER-" + os.urandom(8).hex().encode()
    stub = make_stub(tmp_path, "fake_pg_dump", f'echo "$@" > {tmp_path}/argv.txt; echo "$PGPASSWORD" > {tmp_path}/pw.txt; printf "{marker.decode()}"\n')
    monkeypatch.setenv("PG_DUMP", str(stub))
    out = tmp_path / "bk"
    now = datetime(2026, 11, 28, 1, 2, 3, tzinfo=UTC)
    target = bk.backup(DSN, out, KEY, keep=3, now=now)
    assert target.name == "backup-20261128-010203.dump.enc" and stat.S_IMODE(target.stat().st_mode) == 0o600
    assert marker not in target.read_bytes()
    assert bk.decrypt_file(target, tmp_path / "o", KEY) and (tmp_path / "o").read_bytes() == marker
    argv = (tmp_path / "argv.txt").read_text()
    assert "S3cr3t" not in argv and "-h 10.0.0.5" in argv and "-p 5433" in argv and "-U appuser" in argv and "-d mydb" in argv and "-Fc" in argv
    assert (tmp_path / "pw.txt").read_text().strip() == "S3cr3t!pw"                     # mật khẩu qua PGPASSWORD (đã giải mã %21), không qua argv
    assert [p.name for p in out.iterdir()] == [target.name]                             # không còn thư mục tạm chứa bản rõ
    for k in range(1, 5):
        bk.backup(DSN, out, KEY, keep=3, now=now + timedelta(days=k))
    assert len(list(out.glob("backup-*"))) == 3


def test_failed_or_empty_pg_dump_leaves_no_backup_file(tmp_path, monkeypatch):
    out = tmp_path / "bk"
    for body in ('echo "boom: server version mismatch" >&2; exit 1', "exit 0"):          # lỗi, và "thành công" nhưng rỗng
        monkeypatch.setenv("PG_DUMP", str(make_stub(tmp_path, "pgd", body + "\n")))
        with pytest.raises(bk.BackupError):
            bk.backup(DSN, out, KEY, keep=3)
        assert list(out.glob("backup-*")) == [] and [p for p in out.iterdir()] == []


def test_restore_pipes_the_decrypted_dump_to_pg_restore_and_refuses_a_wrong_key(tmp_path, monkeypatch):
    stub = make_stub(tmp_path, "fake_restore", f'cat > {tmp_path}/restored.bin; echo "$@" > {tmp_path}/ra.txt\n')
    monkeypatch.setenv("PG_RESTORE", str(stub))
    _, dst = enc(tmp_path, b"DUMPBYTES" * 1000)
    bk.restore(dst, DSN, KEY)
    assert (tmp_path / "restored.bin").read_bytes() == b"DUMPBYTES" * 1000
    assert "--exit-on-error" in (tmp_path / "ra.txt").read_text() and "S3cr3t" not in (tmp_path / "ra.txt").read_text()
    (tmp_path / "restored.bin").unlink()
    with pytest.raises(bk.BackupError):
        bk.restore(dst, DSN, os.urandom(32))
    assert not (tmp_path / "restored.bin").exists()                                     # sai khóa: không gọi pg_restore


def test_cli_requires_a_strong_key_and_never_echoes_it(tmp_path, monkeypatch, capsys):
    f = tmp_path / "f.enc"
    for bad in ("", "short", base64.urlsafe_b64encode(bytes([7]) * 32).decode()):
        monkeypatch.setenv("BACKUP_ENC_KEY", bad)
        assert bk.main(["verify", str(f)]) == 1
        assert bad not in capsys.readouterr().err or bad == ""
    monkeypatch.setenv("BACKUP_ENC_KEY", KEY_B64)
    _, dst = enc(tmp_path, b"abc")
    assert bk.main(["verify", str(dst)]) == 0 and "sha256=" in capsys.readouterr().out


def test_backup_removes_the_file_when_the_written_copy_does_not_decrypt(tmp_path, monkeypatch):
    monkeypatch.setenv("PG_DUMP", str(make_stub(tmp_path, "pgd", 'printf "data"\n')))
    monkeypatch.setattr(bk, "encrypt_file", lambda src, dst, key: dst.write_bytes(b"garbage") and "0" * 64)   # ghi hỏng
    out = tmp_path / "bk"
    with pytest.raises(bk.BackupError, match="không giải mã đúng"):
        bk.backup(DSN, out, KEY, keep=3)
    assert list(out.glob("backup-*")) == []
