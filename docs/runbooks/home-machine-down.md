# Runbook: máy nhà tắt, mất mạng hoặc khởi động lại

Web, API và `sync-worker` chạy ở máy nhà (`docs/06` mục 0). `/go/{code}` trên Cloudflare Worker + Neon (khi triển khai) vẫn ghi click khi máy tắt.

## Khi máy tắt thì điều gì xảy ra (đã được khóa bằng thiết kế và test)
| Thành phần | Hệ quả | Dữ liệu có mất không |
|---|---|---|
| Web và API | Không truy cập được. Người dùng thấy lỗi kết nối | Không |
| `sync-worker` | Không đồng bộ đơn; **ví không chuyển tiền pending→rút được** (`wallet.settle` yêu cầu lần sync `ok` trong `SYNC_MAX_AGE_HOURS`, mặc định 24 giờ) | Không: Shopee giữ dữ liệu, lần sync sau quét lại cửa sổ `SYNC_DAYS` (60 ngày) |
| Yêu cầu rút tiền đang chờ | Đứng yên (không tự duyệt/chi trả) | Không |
| Click qua `/go` (Worker) | Vẫn ghi nếu Worker + Neon đang chạy; link `direct_url` luôn hoạt động và vẫn ra hoa hồng | Không |
| Sao lưu hằng ngày | Bỏ lỡ lần chạy; `GET /admin/health` báo `backup: warn` khi bản mới nhất quá `BACKUP_MAX_AGE_HOURS` (36) | Mất tối đa thời gian từ bản sao lưu cuối |

## Khi máy bật lại (theo thứ tự)
1. **Mạng và đồng hồ:** `date` đúng múi giờ/NTP (TOTP và token JWT phụ thuộc đồng hồ; lệch quá 30 giây thì TOTP sai).
2. **DB lên trước:** `make db-up` (dev) hoặc dịch vụ Postgres; kiểm `psql ... -c "select 1"`. Nếu dùng Neon: kiểm trạng thái dự án.
3. **API:** chạy theo `docs/runbooks/web-home-run.md` (bind `127.0.0.1`). `GET /health` phải `degraded: false`; admin xem `GET /api/v1/admin/health` (`overall` ok/warn).
4. **Đồng bộ bù:** `python -m app.main_worker sync-once` (quét lại 60 ngày). Kết quả `result: ok` thì mới chốt ví: `python -m app.main_worker settle-once`. Nếu `failed`/`blocked`: cookie hết hạn hoặc IP bị chặn, xem `cookie-chet.md` và `shopee-403.md`.
5. **Kiểm toàn vẹn sổ cái** sau sự cố bất thường (mất điện giữa chừng): `GET /api/v1/admin/ledger-integrity` phải `mismatches: 0` (nếu khác 0: dừng rút tiền, xem `wallet.md`).
6. **Cloudflare Tunnel:** `cloudflared` chạy lại (service/launchd); kiểm domain truy cập được từ ngoài. Domain/hostname không đổi nếu dùng tunnel có tên (tunnel nhanh `trycloudflare` đổi URL và làm mọi người dùng bị đăng xuất: không dùng cho production).
7. **Sao lưu bù:** chạy `backup_db.py backup` ngay một lần (xem `backup.md`).

## Đề phòng
- Bật tự khởi động lại dịch vụ (`restart: unless-stopped` cho Docker, launchd/systemd cho API, web, `cloudflared`).
- Đặt cảnh báo Telegram (`docs/runbooks/cookie-chet.md`): chỉ báo khi worker CHẠY và gặp lỗi; **máy tắt hẳn thì không có ai để báo**: nên dùng dịch vụ giám sát bên ngoài kiểm URL công khai (ví dụ gói miễn phí của một dịch vụ uptime) nếu muốn biết sớm.
- UPS cho máy và modem nếu mất điện thường xuyên (rủi ro R-11).
