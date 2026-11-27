# Runbook: tài khoản DB riêng cho ứng dụng (audit_logs và sổ cái chỉ-thêm)

## Câu hỏi: trigger có chặn TRUNCATE không?
- Trigger **mức dòng** (`BEFORE UPDATE OR DELETE ... FOR EACH ROW`) **không** chạy với `TRUNCATE`. Trước migration `0005`, `TRUNCATE audit_logs` hoặc `TRUNCATE wallet_entries` xóa sạch được dù có trigger.
- Migration `0005` thêm trigger **mức câu lệnh** `BEFORE TRUNCATE` cho `audit_logs` và `wallet_entries` (cùng hàm ném lỗi). Có test: `TRUNCATE` bị chặn cả với chủ sở hữu.
- **Trigger không phải rào chắn tuyệt đối:** chủ sở hữu bảng (hoặc superuser) vẫn chạy được `ALTER TABLE ... DISABLE TRIGGER`, `DROP TRIGGER`, hoặc `TRUNCATE ... ` sau khi tắt trigger. Vì vậy lớp chính là **quyền**: ứng dụng KHÔNG được là chủ sở hữu và không được cấp `UPDATE/DELETE/TRUNCATE` trên hai bảng này.

## Production: hai tài khoản DB
| Tài khoản | Dùng cho | Quyền |
|---|---|---|
| Chủ sở hữu (ví dụ `cashback_owner`) | `alembic upgrade`, bảo trì thủ công | Sở hữu bảng. KHÔNG đặt vào `DATABASE_URL` của ứng dụng |
| `cashback_app` | API và worker | `SELECT/INSERT/UPDATE` thường; `DELETE` chỉ trên `rate_limits, refresh_tokens, orphan_orders, shopee_order_items`; **không** `TRUNCATE`; **không** sửa/xóa `wallet_entries` và `audit_logs`; không sở hữu bảng nên không tắt được trigger |

Tạo role: `infra/db/app-role.sql` (dùng biến `app_role`, `app_password`). Migration `0005` còn thu hồi `UPDATE, DELETE, TRUNCATE` trên hai bảng nếu role tên `cashback_app` đã tồn tại lúc migrate (role tên khác: chạy script trên). Có test (`test_db_roles.py`) dựng role tạm từ chính script này và kiểm: UPDATE/DELETE/TRUNCATE `audit_logs` và `wallet_entries` bị từ chối, không `DISABLE TRIGGER` được, vẫn INSERT/SELECT bình thường.

Khi thêm bảng mới ở migration: chủ sở hữu tạo bảng, rồi `GRANT` quyền tối thiểu cho `cashback_app` trong cùng migration (mặc định ứng dụng không có quyền gì trên bảng mới).

## Dev và test
- Dev dùng tài khoản `cashback` của Docker (superuser/chủ sở hữu): thuận tiện, **không an toàn**; chỉ chạy trên máy dev.
- Test tích hợp cần xóa dòng `audit_logs`/`wallet_entries` để DB sạch. Cách làm (xem `tests/integration/conftest.py` và các fixture `pg`): trong MỘT transaction, chủ sở hữu `ALTER TABLE ... DISABLE TRIGGER`, `DELETE` đúng dòng do test tạo, rồi `ENABLE TRIGGER`. Đây là **đi vòng qua trigger** (không có cách khác để xóa), chỉ chủ sở hữu làm được, và chỉ chạy được trên DB loopback (conftest từ chối chạy dọn nếu `DATABASE_URL` không trỏ localhost). Không bao giờ chạy test tích hợp với `DATABASE_URL` của production.
