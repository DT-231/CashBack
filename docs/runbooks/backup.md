# Runbook: sao lưu và khôi phục Postgres (T-060)

Script: `backend/scripts/backup_db.py` (`backup`, `verify`, `restore`). Bản sao lưu là `pg_dump -Fc` được mã hóa AES-256-GCM theo khối 1 MiB (sai khóa, sửa bit, cắt cụt, đảo khối, nối thừa đều bị phát hiện). Bản rõ chỉ nằm trong thư mục tạm và bị xóa ngay; tệp `.dump.enc` quyền 0600; sau khi ghi script giải mã lại để kiểm.

## Khóa (quan trọng nhất)
- `BACKUP_ENC_KEY`: base64 của 32 byte ngẫu nhiên (`python3 -c "import secrets,base64;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"`). **Khác `BANK_ENC_KEY`**, để lộ một khóa không mở được cái kia.
- **Cất khóa NGOÀI máy chạy sao lưu và ngoài chỗ để các tệp `.dump.enc`** (trình quản lý mật khẩu / bản in). Mất khóa = các bản sao lưu vô dụng. Bản sao lưu chứa cả bản mã số tài khoản ngân hàng và bí mật TOTP: muốn dùng được cần cả `BACKUP_ENC_KEY` lẫn `BANK_ENC_KEY`.

## Chạy hằng ngày (máy nhà)
```bash
export BACKUP_ENC_KEY=...            # từ nơi lưu khóa, không ghi vào crontab
python3 backend/scripts/backup_db.py backup --dsn "$DATABASE_URL" --out ~/backups --keep 14
```
Lịch 03:00 mỗi ngày: `crontab -e` → `0 3 * * * cd /đường/dẫn/repo && BACKUP_ENC_KEY=$(cat ~/.config/cashback/backup.key) .venv/bin/python backend/scripts/backup_db.py backup --dsn "$(cat ~/.config/cashback/db.dsn)" --out ~/backups --keep 14 >> ~/backups/backup.log 2>&1` (tệp khóa và DSN quyền 0600, nằm ngoài repo). Cảnh báo khi lỗi: lệnh thoát mã 1 và in lý do (không chứa DSN/mật khẩu/khóa); gắn với Telegram qua `|| curl ...` nếu cần.
- **pg_dump phải cùng phiên bản chính với server** (Postgres 16 ở dev). Máy host có thể có bản khác: đặt `PG_DUMP="docker exec -i <container-db> pg_dump"` và dùng DSN theo mạng trong container (`...@127.0.0.1:5432/...`). Với Neon: dùng `pg_dump` cùng major với dự án Neon.
- Sao chép `~/backups` lên nơi thứ hai (Google Drive bằng `rclone`, ổ ngoài). Tệp đã mã hóa nên an toàn để tải lên, nhưng khóa KHÔNG đi cùng.

## Kiểm tra định kỳ (ít nhất mỗi tháng)
1. `python3 backend/scripts/backup_db.py verify ~/backups/<tệp>.dump.enc` (giải mã hết tệp, in SHA-256; không cần DB).
2. Khôi phục thử vào DB TRỐNG (không bao giờ vào DB đang chạy): tạo DB tạm → `restore <tệp> --dsn <DB-tạm>` → đối chiếu số dòng `users`, `wallet_entries`, `withdrawals`, `audit_logs` và `alembic_version` với bản gốc → xóa DB tạm. (Ghi nhận ngày thử vào sổ vận hành.)
3. Đã thử đầu-cuối trên DB dev 2026-11-28: sao lưu → `verify` → khôi phục vào DB tạm → số dòng và phiên bản migration (`0008`) khớp.

## Khôi phục khi sự cố
`restore` dùng `pg_restore --no-owner --exit-on-error` vào một DB **trống**; sau đó chạy `alembic upgrade head` nếu bản sao lưu cũ hơn mã, trỏ ứng dụng sang DB mới, và kiểm bất biến sổ cái (số dư `wallets` = tổng suy ra từ `wallet_entries`, xem `docs/runbooks/wallet.md`). Role ứng dụng (`cashback_app`) và quyền: chạy lại `infra/db/app-role.sql` (role nằm ngoài bản dump vì `--no-owner`).
