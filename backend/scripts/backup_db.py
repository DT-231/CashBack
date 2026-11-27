#!/usr/bin/env python3
"""Sao lưu Postgres có mã hóa (T-060). pg_dump -Fc → AES-256-GCM theo khối → tệp `.dump.enc`; xoay vòng giữ N bản; khôi phục và kiểm tra.

    python3 backend/scripts/backup_db.py backup  --dsn "$DATABASE_URL" --out ~/backups [--keep 14]
    python3 backend/scripts/backup_db.py verify  FILE            # giải mã hết tệp, kiểm tính toàn vẹn (không cần DB)
    python3 backend/scripts/backup_db.py restore FILE --dsn "$SCRATCH_DATABASE_URL"   # vào DB TRỐNG (không ghi đè)

Khóa: BACKUP_ENC_KEY (base64 32 byte, KHÁC BANK_ENC_KEY; sao lưu khóa NGOÀI máy và ngoài chỗ để bản sao lưu).
pg_dump/pg_restore phải cùng phiên bản chính với server: đặt PG_DUMP / PG_RESTORE (ví dụ "docker exec -i infra-db-1 pg_dump").
Không in/ghi DSN hay mật khẩu; mật khẩu truyền qua PGPASSWORD của tiến trình con.
"""
import _bootstrap  # noqa: F401  (phải import trước app.*)
import argparse
import hashlib
import os
import shlex
import struct
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import ConfigError
from app.core.crypto import parse_key

MAGIC = b"CBK1"
CHUNK = 1024 * 1024
SUFFIX = ".dump.enc"


class BackupError(Exception):
    pass


def encrypt_file(src: Path, dst: Path, key: bytes) -> str:
    """Mã hóa theo khối 1 MiB, mỗi khối một nonce (tiền tố ngẫu nhiên + bộ đếm); AAD gồm header, chỉ số khối và cờ khối cuối
    nên sắp xếp lại/cắt cụt/ghép khối đều bị phát hiện. Trả SHA-256 của bản rõ."""
    prefix, aes, sha = os.urandom(8), AESGCM(key), hashlib.sha256()
    header = MAGIC + prefix
    with src.open("rb") as fi, dst.open("wb") as fo:
        fo.write(header)
        buf, i = fi.read(CHUNK), 0
        while True:
            nxt = fi.read(CHUNK)
            last = not nxt
            sha.update(buf)
            fo.write(struct.pack(">I", len(buf) + 16) + aes.encrypt(prefix + struct.pack(">I", i), buf, header + struct.pack(">IB", i, last)))
            if last:
                break
            buf, i = nxt, i + 1
    return sha.hexdigest()


def decrypt_file(src: Path, dst: Path | None, key: bytes) -> str:
    """Giải mã (dst=None: chỉ kiểm). Ném BackupError nếu sai khóa, bị sửa, cắt cụt hoặc có dữ liệu thừa. Trả SHA-256 bản rõ."""
    aes, sha = AESGCM(key), hashlib.sha256()
    with src.open("rb") as fi:
        header = fi.read(12)
        if len(header) != 12 or header[:4] != MAGIC:
            raise BackupError("không phải tệp sao lưu CBK1")
        out = dst.open("wb") if dst else None
        try:
            i, seen_last = 0, False
            while True:
                raw = fi.read(4)
                if not raw:
                    break
                if seen_last:
                    raise BackupError("có dữ liệu sau khối cuối")
                if len(raw) != 4:
                    raise BackupError("tệp bị cắt cụt")
                (n,) = struct.unpack(">I", raw)
                blob = fi.read(n)
                if len(blob) != n or n < 16 or n > CHUNK + 16:
                    raise BackupError("tệp bị cắt cụt hoặc hỏng")
                last = fi.read(1) == b""              # nhìn trước một byte để biết đây có phải khối cuối
                if not last:
                    fi.seek(-1, 1)
                try:
                    plain = aes.decrypt(header[4:] + struct.pack(">I", i), blob, header + struct.pack(">IB", i, last))
                except InvalidTag:
                    raise BackupError("giải mã thất bại: sai khóa hoặc tệp bị sửa/cắt cụt/đảo khối") from None
                sha.update(plain)
                if out:
                    out.write(plain)
                seen_last, i = last, i + 1
            if not seen_last:
                raise BackupError("tệp bị cắt cụt (thiếu khối cuối)")
        finally:
            if out:
                out.close()
    return sha.hexdigest()


def _conn_args(dsn: str) -> tuple[list[str], dict]:
    u = urlsplit(dsn.replace("postgresql+psycopg://", "postgresql://"))
    args = ["-h", u.hostname or "127.0.0.1", "-p", str(u.port or 5432), "-U", unquote(u.username or ""), "-d", (u.path or "/").lstrip("/")]
    return args, {"PGPASSWORD": unquote(u.password or "")}


def rotate(out: Path, keep: int) -> list[Path]:
    files = sorted(out.glob("backup-*" + SUFFIX))
    gone = files[:-keep] if keep > 0 else []
    for f in gone:
        f.unlink()
    return gone


def backup(dsn: str, out: Path, key: bytes, keep: int, now: datetime | None = None) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%d-%H%M%S")
    target = out / f"backup-{stamp}{SUFFIX}"
    args, env = _conn_args(dsn)
    with tempfile.TemporaryDirectory(dir=out) as tmp:                 # bản rõ chỉ nằm trong thư mục tạm, xóa ngay sau khi mã hóa
        plain = Path(tmp) / "dump"
        _dump_to(plain, args, env)
        digest = encrypt_file(plain, target, key)
        os.chmod(target, 0o600)
        if decrypt_file(target, None, key) != digest:                 # kiểm ngay: bản vừa ghi phải giải mã được
            target.unlink()
            raise BackupError("bản sao lưu vừa ghi không giải mã đúng")
    rotate(out, keep)
    return target


def _dump_to(plain: Path, args: list[str], env: dict) -> None:
    cmd = shlex.split(os.environ.get("PG_DUMP", "pg_dump")) + ["-Fc", "--no-owner"] + args
    with plain.open("wb") as f:
        r = subprocess.run(cmd, env={**os.environ, **env}, stdout=f, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0 or plain.stat().st_size == 0:
        raise BackupError(f"pg_dump lỗi (mã {r.returncode}): {r.stderr.strip()[-300:]}")


def restore(file: Path, dsn: str, key: bytes) -> None:
    args, env = _conn_args(dsn)
    with tempfile.TemporaryDirectory() as tmp:
        plain = Path(tmp) / "dump"
        decrypt_file(file, plain, key)
        cmd = shlex.split(os.environ.get("PG_RESTORE", "pg_restore")) + ["--no-owner", "--exit-on-error"] + args
        with plain.open("rb") as f:
            r = subprocess.run(cmd, env={**os.environ, **env}, stdin=f, stderr=subprocess.PIPE, text=True)
        if r.returncode != 0:
            raise BackupError(f"pg_restore lỗi (mã {r.returncode}): {r.stderr.strip()[-300:]}")


def _key() -> bytes:
    try:
        return parse_key(os.environ.get("BACKUP_ENC_KEY", ""))
    except ConfigError as e:
        raise BackupError(f"BACKUP_ENC_KEY: {e}") from None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="backup_db")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backup"); b.add_argument("--dsn", default=os.environ.get("DATABASE_URL", "")); b.add_argument("--out", required=True)
    b.add_argument("--keep", type=int, default=14)
    v = sub.add_parser("verify"); v.add_argument("file")
    r = sub.add_parser("restore"); r.add_argument("file"); r.add_argument("--dsn", required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "backup":
            if not a.dsn:
                raise BackupError("thiếu --dsn hoặc DATABASE_URL")
            print(f"OK {backup(a.dsn, Path(a.out).expanduser(), _key(), a.keep)}")
        elif a.cmd == "verify":
            print(f"OK sha256={decrypt_file(Path(a.file), None, _key())}")
        else:
            restore(Path(a.file), a.dsn, _key())
            print("OK đã khôi phục (hãy đối chiếu số dòng các bảng chính)")
    except BackupError as e:
        print(f"LỖI: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
