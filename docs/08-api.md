# 08 — API (REST, JSON)

Tiền tố `/api/v1`. Lỗi trả dạng `{"error":{"code":"...","message":"..."}}`. Phiên người dùng là cookie HttpOnly; Tool API dùng header `Authorization: Bearer <agent_key>`. Tiền luôn là số nguyên đồng (VND).

Quyền: `public`, `member`, `staff`, `admin`, `agent`.

## Auth
| Method | Path | Quyền | Mô tả |
|---|---|---|---|
| POST | `/auth/register` | public | `{email,password}` → 202, gửi email xác minh |
| POST | `/auth/verify` | public | `{token}` → 204; token một lần, hạn 24 giờ, **POST (không GET) để token không vào URL/nhật ký/Referer** |
| POST | `/auth/verify/resend` | public | `{email}` → luôn 202; chỉ gửi nếu tài khoản chưa xác minh; token cũ vô hiệu; giới hạn theo IP và 3 lần/giờ/email |
| POST | `/auth/login` | public | `{email,password}` → set cookie |
| POST | `/auth/logout` | member+ | |
| GET | `/auth/mfa/status` | member+ | `{enabled, pending, verified}` (phiên này đã nhập mã TOTP gần đây chưa) |
| POST | `/auth/mfa/setup` / `/enable {code}` / `/verify {code | recovery_code}` / `/disable {code}` | member+ | Đăng nhập hai lớp TOTP (T-019). `setup` trả `secret` + `otpauth_uri` một lần; `enable` trả 8 mã khôi phục một lần; `verify` trả cặp token MỚI có `mfa_at` (route admin yêu cầu). Chưa bật/chưa xác minh: route admin trả `403 mfa_required`. Xem `docs/runbooks/admin-mfa.md` |
| POST | `/auth/forgot` | public | `{email}` → luôn 202 (như nhau dù email có tồn tại, bị khóa hay không); gửi nền SAU khi trả lời; giới hạn theo IP và 3 lần/giờ/email |
| POST | `/auth/reset` | public | `{token,password>=10}` → 204; token một lần, hạn 1 giờ; đổi mật khẩu, **đăng xuất mọi thiết bị**, vô hiệu token còn lại; `unverified` thành `active`; tài khoản `locked` KHÔNG được mở |

## Member
| Method | Path | Quyền | Mô tả |
|---|---|---|---|
| POST | `/links` | member | `{url}` → `{code, go_url, direct_url, product:{name,shop_id,item_id}}` |
| GET | `/me/links` | member | Danh sách link + số click |
| GET | `/me/clicks?from=&to=` | member | Lịch sử click |
| GET | `/me/orders?limit=&offset=` | member | Đơn của tôi (mới nhất trước): `{id, order_ref (4 ký tự cuối), status, product_name (null), purchased_at, refund_vnd, refund_state: none\|pending\|available\|cancelled\|reversed, expected_release_at}`. `expected_release_at` chỉ có khi đơn `COMPLETED` và tiền còn chờ = hoàn tất + `hold_days` có hiệu lực lúc hoàn tất; do backend tính, UI không tự tính. Không bao giờ trả đơn của người khác hay đơn mồ côi |
| GET | `/me/wallet` | member | `{pending_vnd, available_vnd, held_vnd, share_pct}` |
| GET | `/me/wallet/entries` | member | Sổ cái của tôi |
| POST/GET | `/me/bank-accounts` | member | Thêm tài khoản nhận `{bank_code, account_no, account_name}` (mã hóa AES-GCM; trả về chỉ `last4`; chờ `bank_change_cooldown_hours`, mặc định 48 giờ, trước khi rút lần đầu về tài khoản mới; tối đa 5) / danh sách (chỉ 4 số cuối) |
| POST | `/me/withdrawals` | member | `{amount_vnd (số nguyên), bank_account_id}` + header **`Idempotency-Key`** bắt buộc. Khóa `rút được → đang khóa` trong một transaction có khóa ví; tối thiểu `min_withdraw_vnd`; một yêu cầu mở mỗi user; rate limit. Lỗi: `below_minimum`, `insufficient_funds`, `withdrawal_open_exists`, `idempotency_conflict`, `bank_account_cooling_down`, `withdrawals_disabled` (503) |
| GET | `/me/withdrawals` | member | Lịch sử rút |
| POST | `/me/claims` | member | `{order_sn?, note, purchased_at}` |

Ví dụ:
```
POST /api/v1/links  {"url":"https://shopee.vn/Ten-i.1020310358.24088489429"}
→ 200 {"code":"q8w2e1","go_url":"https://app.example/go/q8w2e1",
       "direct_url":"https://shopee.vn/universal-link/product/1020310358/24088489429?utm_source=an_17300000000&utm_medium=affiliates&utm_campaign=-&utm_content=1l-3f-9a-k2d-",
       "product":{"shop_id":1020310358,"item_id":24088489429,"name":"..."}}
```

## Redirect (link-api)
| Method | Path | Quyền | Mô tả |
|---|---|---|---|
| GET | `/go/{code}` | public | Ghi click, 302 tới link affiliate có `sub_id` `1u-…`. Không tồn tại → 404. Giới hạn tần suất theo IP. |

## Tool API cho Muse AI (`agent`)
| Method | Path | Mô tả |
|---|---|---|
| GET | `/agent/search?keyword=&limit=&min_rate=&min_sold=` | Tìm SP (feed → api → browser). Không trả link, tránh tạo link thừa |
| POST | `/agent/links` | `{shop_id,item_id,post_key,page_code,category?}` → `{post_id, aff_link}`; `post_key` trùng → trả lại link cũ (idempotent), **không ghi đè đích** |
| GET | `/agent/insights?days=30&group=category\|hour\|post\|page` | Click/đơn/hoa hồng theo nhóm, từ DB của ta |
| GET | `/agent/health` | Trạng thái nguồn tìm kiếm |

Ví dụ:
```
POST /api/v1/agent/links  {"shop_id":1020310358,"item_id":24088489429,"post_key":"fb-p1-20261201-0930-a","page_code":"p1","category":"gia-dung"}
→ {"post_id":412,"sub_id":"1p-bg-1-x4m-","aff_link":"https://shopee.vn/universal-link/product/...&utm_content=1p-bg-1-x4m-"}
```

## Admin / Staff
| Method | Path | Quyền | Mô tả |
|---|---|---|---|
| GET | `/admin/overview?days=` | **admin** (+TOTP) | KPI: người dùng, click, link, đơn theo trạng thái (hoa hồng micro), đơn mồ côi mở, tổng ví (VND nguyên), yêu cầu rút theo trạng thái, lần sync gần nhất |
| GET | `/admin/users?q=&limit=&offset=` | **admin** | Tìm theo email (khớp chữ, không wildcard), kèm số dư ví |
| PATCH | `/admin/users/{id}` | **admin** (+TOTP) | `{status: active\|locked, reason}`; khóa thì xóa mọi refresh token; cấm tự đổi mình và đổi admin khác; audit `users.set_status`. Role không đổi qua API |
| GET | `/admin/orders?status=&source=` | **admin** | Danh sách đơn (lọc theo trạng thái/nguồn) |
| GET | `/admin/orphans`, POST `/admin/orphans/{order_id}/assign` | **admin** (+TOTP; staff không: gán đơn là tạo tiền cho user) | `{user_id, reason}`; gán đúng một lần, cấm tự gán cho mình, user phải đang hoạt động; ví tự ghi nhận ở lần chốt kế tiếp; audit `orders.assign_orphan` |
| GET | `/admin/withdrawals?status=` | **admin** | Chỉ 4 số cuối tài khoản |
| POST | `/admin/withdrawals/{id}/approve` / `/reject` `{reason}` / `/fail` `{reason}` | **admin** (staff không) | Từ chối/lỗi hoàn tiền bằng bút toán `refund_hold` mới; trạng thái đổi có điều kiện (không làm hai lần) |
| GET | `/admin/withdrawals/{id}/payout-account` | **admin** | Giải mã số tài khoản để chuyển khoản (chỉ khi `approved`); ghi audit `payout.view_account` mỗi lần; `Cache-Control: no-store` |
| POST | `/admin/withdrawals/{id}/mark-paid` | **admin** | `{provider_ref}` mã giao dịch ngân hàng, duy nhất, không đánh dấu hai lần |
| PUT | `/admin/shopee-session` | admin | `{cookie}`; không có GET trả cookie |
| GET | `/admin/shopee-session/status` | admin | `{status,last_ok_at,failure_count}` |
| POST | `/admin/imports/orders-csv` | staff+ | Import dự phòng |
| GET | `/admin/reconciliation?month=YYYY-MM` | admin (+TOTP) | Đơn theo trạng thái (hoa hồng micro và VND), bút toán ví theo trạng thái đơn, `completed.{shopee_commission_vnd, user_share_accrued_vnd, platform_margin_vnd}`, chi trả trong tháng, khoản lỗ admin (`adjust`). Tháng nửa mở [đầu, đầu tháng sau) theo UTC |
| GET | `/admin/ledger-integrity` | admin (+TOTP) | So `wallets` với số suy ra từ `wallet_entries`; `mismatches` > 0 là sự cố: dừng rút tiền, xem `docs/runbooks/wallet.md` |
| GET/PUT | `/admin/settings` | admin | `user_share_bp, min_withdraw_vnd, hold_days, auto_payout` |
| GET | `/admin/fraud-flags` | staff+ | |
| POST/DELETE | `/admin/agent-keys` | admin | Cấp/thu hồi key (hiện key đúng 1 lần) |
| GET | `/admin/audit-logs` | admin | |
| GET | `/admin/health` | **admin** (+TOTP) | `{overall, db, sync, shopee_session, backup, warnings}`; mỗi thành phần có `status` ∈ ok/warn/down/unknown/not_configured. `backup` đọc tuổi tệp `backup-*.dump.enc` mới nhất trong `BACKUP_DIR` (thiếu cấu hình thì `overall` ít nhất warn). Không lộ đường dẫn/DSN/bí mật |

## Tool API hiện có (v1.2) — chuyển đổi

Trạng thái sau refactor (2026-11-27, `docs/refactor/`):

| Cũ | Hiện tại |
|---|---|
| `GET /api/search` | **Còn** (lớp tương thích, sắp bỏ) → dùng `GET /api/v1/agent/search` (có auth) |
| `POST /api/link` | **Còn** (lớp tương thích, sắp bỏ) → dùng `POST /api/v1/agent/links` (idempotent theo `post_key`, sub_id v1 có chữ ký) |
| `GET /api/stats`, `GET /api/revenue` | **Đã bỏ**. Doanh thu thật: `backend/scripts/revenue_report.py`; sau này `/agent/insights`, `/admin/overview` |
| `GET /go/<sub_id>` | **Đã bỏ** khỏi backend; `/go/{code}` sẽ chạy ở Cloudflare Worker (T-015) |

`/api/search` và `/api/link` bắt buộc `Authorization: Bearer` khi đã đặt `AGENT_API_KEY` hoặc `HOST` không phải localhost (khi đó server từ chối khởi động nếu thiếu khóa).
