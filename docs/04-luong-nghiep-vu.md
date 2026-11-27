# 04 — Luồng nghiệp vụ

Quy ước: `API` = backend chính (FastAPI), `LINK` = link-api (`/go/` + tool API), `SYNC` = sync-worker, `DB` = Postgres.
Do Muse AI tự đăng bài ngoài hệ thống, các luồng 8–10 được viết lại theo mô hình "agent gọi Tool API". Luồng 10 ("tự đăng không cần duyệt") không còn là chức năng của ta.

## 1. Đăng ký / đăng nhập / quên mật khẩu
```mermaid
sequenceDiagram
  actor U as Thành viên
  participant W as Web
  participant API
  participant DB
  participant MAIL as Email
  U->>W: Nhập email + mật khẩu
  W->>API: POST /auth/register
  API->>API: Rate limit theo IP + email
  API->>DB: Tạo user (status=unverified), hash argon2
  API->>MAIL: Gửi link xác minh (token 1 lần, hết hạn 24h)
  U->>API: GET /auth/verify?token=
  API->>DB: status=active
  U->>W: Đăng nhập
  W->>API: POST /auth/login
  API-->>W: Set-Cookie phiên (HttpOnly, Secure, SameSite)
  Note over U,API: Quên mật khẩu: POST /auth/forgot → email token → POST /auth/reset, trả lời luôn "đã gửi" để không lộ email tồn tại
```

## 2. Dán link → link affiliate
```mermaid
sequenceDiagram
  actor U as Thành viên
  participant W as Web
  participant API
  participant DB
  U->>W: Dán link Shopee
  W->>API: POST /links {url}
  API->>API: Kiểm tra host thuộc shopee.vn/s.shopee.vn/shope.ee
  API->>API: parse shop_id,item_id (affiliate.parse_product_url)
  API->>DB: upsert product; insert link (user_id, product_id) → link_code
  API-->>W: go_url = https://<host>/go/<link_code>, direct_url = link affiliate dự phòng (sub_id mức link)
  Note over API: Link ngắn s.shopee.vn: theo redirect tối đa 3 lần, chỉ tới host Shopee
```

## 3. Bấm link → redirect → mua
```mermaid
sequenceDiagram
  actor U as Thành viên
  participant LINK as link-api /go
  participant DB
  participant SP as Shopee
  U->>LINK: GET /go/<link_code>
  LINK->>DB: lookup link; insert click (click_id, ip_hash, ua)
  LINK->>LINK: sub_id = encode(v1, source=u, user, click_id)
  LINK-->>U: 302 → universal-link ... utm_content=<sub_id>
  U->>SP: Mở app/web Shopee, mua hàng
  Note over LINK,DB: Nếu DB lỗi: vẫn 302 bằng sub_id mức link (không có click_id) để không mất đơn
```

## 4. Đồng bộ đơn → ví (chờ → khả dụng → hủy)
```mermaid
sequenceDiagram
  participant SYNC
  participant SP as Shopee dashboard
  participant DB
  loop mỗi 30-60 phút
    SYNC->>SP: report/list (cửa sổ 60 ngày, phân trang đủ)
    SP-->>SYNC: đơn + utm_content + status + hoa hồng
    SYNC->>DB: upsert shopee_orders (idempotent theo order_sn+item)
    SYNC->>SYNC: decode sub_id → nguồn (user / post / unknown)
    alt khớp user
      SYNC->>DB: tạo ledger entry "pending" = floor(60% × hoa hồng)
    else không khớp
      SYNC->>DB: đưa vào orphan_orders (thuộc admin)
    end
    SYNC->>DB: đơn đổi trạng thái → cập nhật ledger
  end
  Note over SYNC,DB: Đơn COMPLETED + 7 ngày → pending→available.<br/>Đơn CANCELLED/RETURNED → cancelled (tiền pending bị hủy, không âm).
  Note over SYNC: Nếu sync lỗi (cookie chết/403) → KHÔNG cộng/chuyển tiền, bật cảnh báo
```

## 5. Xem lịch sử
```mermaid
sequenceDiagram
  actor U as Thành viên
  participant W as Web
  participant API
  participant DB
  U->>W: Mở Ví / Click / Đơn
  W->>API: GET /me/wallet, /me/clicks, /me/orders
  API->>DB: truy vấn theo user_id (luôn lọc theo phiên)
  API-->>W: số dư pending/available + lịch sử
```

## 6. Rút tiền
```mermaid
sequenceDiagram
  actor U as Thành viên
  participant API
  participant DB
  actor A as Admin/Staff
  participant PAY as PayoutProvider
  U->>API: POST /me/withdrawals {amount, bank_account}
  API->>DB: kiểm tra ≥ ngưỡng, ≤ available, không có yêu cầu mở
  API->>DB: ledger: available → held (khóa tiền)
  A->>API: POST /admin/withdrawals/{id}/approve
  API->>PAY: payout(amount, account)
  alt thành công
    PAY-->>API: tham chiếu giao dịch
    API->>DB: held → paid_out, lưu tham chiếu
  else thất bại / từ chối
    API->>DB: held → available (hoàn), ghi lý do
  end
  API-->>U: Email thông báo
```

## 7. Khiếu nại "mua rồi chưa thấy đơn"
```mermaid
sequenceDiagram
  actor U as Thành viên
  participant API
  participant DB
  actor S as Staff
  U->>API: POST /me/claims {order_sn hoặc ngày + sản phẩm}
  API->>DB: tra click của user trong khoảng thời gian; kiểm tra đơn Shopee đã về chưa
  alt đơn đã có và khớp
    API-->>U: "Đơn đang ở trạng thái X, dự kiến vào ví lúc Y"
  else đơn mồ côi cùng sản phẩm/giờ
    API->>S: đưa vào hàng chờ
    S->>DB: gán đơn mồ côi → user (có lý do, audit log)
  else chưa có đơn
    API-->>U: "Shopee thường mất 24–48h để hiển thị đơn"
  end
```

## 8. Muse AI lấy sản phẩm + link cho một bài (thay cho luồng "AI fanpage" cũ)
```mermaid
sequenceDiagram
  participant M as Muse AI
  participant LINK as link-api (Tool API)
  participant FEED as feed.csv
  participant DB
  M->>LINK: GET /agent/insights?days=30 (ngành nào ra tiền)
  LINK-->>M: top ngành, giờ, kiểu bài theo hoa hồng thật
  M->>LINK: GET /agent/search?keyword=&min_rate=
  LINK->>FEED: tìm + lọc giá/đã bán
  LINK-->>M: danh sách SP + % hoa hồng
  M->>LINK: POST /agent/links {item, post_key, page_code}
  LINK->>DB: lưu post (post_key↔sub_id, page, category)
  LINK-->>M: aff_link (utm_content=<v1,p,post,...>)
  M->>M: Viết bài/video, đăng lên fanpage (ngoài hệ thống ta)
```

## 9. Vòng học
```mermaid
sequenceDiagram
  participant SYNC
  participant DB
  participant M as Muse AI
  SYNC->>DB: đơn có sub_id nguồn=post → gắn post_key/ngành/giờ đăng
  M->>DB: (qua API) GET /agent/insights?group=category|hour|post
  Note over M: Muse tự điều chỉnh lần chọn SP kế tiếp.<br/>Hoa hồng của bài fanpage 100% thuộc admin, không chia user.
```

## 10. (Bỏ) Tự đăng không duyệt
Do Muse AI đăng ngoài hệ thống, ta không cần cơ chế này. Giới hạn số bài/ngày (nếu muốn) cấu hình ở Muse.

## 11. Cập nhật cookie → health-check → cảnh báo
```mermaid
sequenceDiagram
  actor A as Admin
  participant API
  participant DB
  participant SYNC
  participant SP as Shopee
  participant TG as Telegram/Email
  A->>API: PUT /admin/shopee-session {cookie}
  API->>DB: lưu mã hóa (AES-GCM), status=unknown
  SYNC->>SP: dashboard/detail (nhẹ)
  alt 200 code=0
    SYNC->>DB: status=healthy, last_ok_at
  else 401/403/HTML
    SYNC->>DB: status=expired|blocked, tăng failure_count
    SYNC->>TG: cảnh báo "cookie chết"
    Note over SYNC,DB: Dừng chuyển pending→available cho tới khi sync lại thành công
  end
```

## 12. Đối soát
```mermaid
sequenceDiagram
  actor A as Admin
  participant API
  participant DB
  A->>API: GET /admin/reconciliation?month=
  API->>DB: Σ hoa hồng Shopee (đơn COMPLETED) = X
  API->>DB: Σ chia user (pending+available+paid) = Y; Σ đơn hủy; Σ mồ côi = Z
  API-->>A: X − Y − Z = lợi nhuận giữ lại; cờ nếu lệch ≠ 0
```

## 13. Cấu hình tỷ lệ, ngưỡng
```mermaid
sequenceDiagram
  actor A as Admin
  participant API
  participant DB
  A->>API: PUT /admin/settings {user_share=0.60, min_withdraw, hold_days}
  API->>DB: lưu phiên bản cấu hình (effective_from)
  Note over API,DB: Đơn mới dùng cấu hình mới. Đơn cũ giữ snapshot tỷ lệ tại thời điểm tạo, không đổi hồi tố.
```

## 14. Xử lý gian lận
```mermaid
sequenceDiagram
  participant SYNC
  participant DB
  actor S as Staff
  SYNC->>DB: quy tắc: user mua qua link của chính mình? (khớp device/IP của click với tài khoản)
  SYNC->>DB: nhiều tài khoản cùng ip_hash/device trong 24h; tỷ lệ hủy > ngưỡng
  SYNC->>DB: tạo fraud_flag (rule, điểm)
  S->>DB: xem cờ → giữ pending / khóa tài khoản / bỏ qua (có audit)
```
