# 08 — API (REST, JSON)

Tiền tố `/api/v1`. Lỗi trả dạng `{"error":{"code":"...","message":"..."}}`. Phiên người dùng là cookie HttpOnly; Tool API dùng header `Authorization: Bearer <agent_key>`. Tiền luôn là số nguyên đồng (VND).

Quyền: `public`, `member`, `staff`, `admin`, `agent`.

## Auth
| Method | Path | Quyền | Mô tả |
|---|---|---|---|
| POST | `/auth/register` | public | `{email,password}` → 202, gửi email xác minh |
| GET | `/auth/verify?token=` | public | Kích hoạt |
| POST | `/auth/login` | public | `{email,password}` → set cookie |
| POST | `/auth/logout` | member+ | |
| POST | `/auth/forgot` | public | Luôn 202 |
| POST | `/auth/reset` | public | `{token,password}` |

## Member
| Method | Path | Quyền | Mô tả |
|---|---|---|---|
| POST | `/links` | member | `{url}` → `{code, go_url, direct_url, product:{name,shop_id,item_id}}` |
| GET | `/me/links` | member | Danh sách link + số click |
| GET | `/me/clicks?from=&to=` | member | Lịch sử click |
| GET | `/me/orders` | member | Đơn của tôi + trạng thái |
| GET | `/me/wallet` | member | `{pending_vnd, available_vnd, held_vnd, share_pct}` |
| GET | `/me/wallet/entries` | member | Sổ cái của tôi |
| POST | `/me/bank-accounts` | member | Thêm tài khoản nhận |
| POST | `/me/withdrawals` | member | `{amount_vnd, bank_account_id}` |
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
| GET | `/admin/overview?days=` | staff+ | KPI tổng |
| GET | `/admin/users`, PATCH `/admin/users/{id}` | staff (xem), admin (sửa) | Khóa/mở |
| GET | `/admin/orders?status=&source=` | staff+ | |
| GET | `/admin/orphans`, POST `/admin/orphans/{order_id}/assign` | staff+ | `{user_id, reason}`, ghi audit |
| GET | `/admin/withdrawals?status=` | staff+ | |
| POST | `/admin/withdrawals/{id}/approve` / `/reject` | staff+ (theo cấu hình) | |
| POST | `/admin/withdrawals/{id}/mark-paid` | staff+ | `{provider_ref}` cho chi trả thủ công |
| PUT | `/admin/shopee-session` | admin | `{cookie}`; không có GET trả cookie |
| GET | `/admin/shopee-session/status` | admin | `{status,last_ok_at,failure_count}` |
| POST | `/admin/imports/orders-csv` | staff+ | Import dự phòng |
| GET | `/admin/reconciliation?month=` | admin | |
| GET/PUT | `/admin/settings` | admin | `user_share_bp, min_withdraw_vnd, hold_days, auto_payout` |
| GET | `/admin/fraud-flags` | staff+ | |
| POST/DELETE | `/admin/agent-keys` | admin | Cấp/thu hồi key (hiện key đúng 1 lần) |
| GET | `/admin/audit-logs` | admin | |

## Tool API hiện có (v1.2) — chuyển đổi

Trạng thái sau refactor (2026-11-27, `docs/refactor/`):

| Cũ | Hiện tại |
|---|---|
| `GET /api/search` | **Còn** (lớp tương thích, sắp bỏ) → dùng `GET /api/v1/agent/search` (có auth) |
| `POST /api/link` | **Còn** (lớp tương thích, sắp bỏ) → dùng `POST /api/v1/agent/links` (idempotent theo `post_key`, sub_id v1 có chữ ký) |
| `GET /api/stats`, `GET /api/revenue` | **Đã bỏ**. Doanh thu thật: `backend/scripts/revenue_report.py`; sau này `/agent/insights`, `/admin/overview` |
| `GET /go/<sub_id>` | **Đã bỏ** khỏi backend; `/go/{code}` sẽ chạy ở Cloudflare Worker (T-015) |

`/api/search` và `/api/link` bắt buộc `Authorization: Bearer` khi đã đặt `AGENT_API_KEY` hoặc `HOST` không phải localhost (khi đó server từ chối khởi động nếu thiếu khóa).
