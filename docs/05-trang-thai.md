# 05 — Máy trạng thái

## 1. Đơn hàng Shopee (`shopee_orders.status`)
Trạng thái do Shopee quyết định; ta chỉ phản ánh. Tên cụ thể cần đối chiếu với dữ liệu thật (hiện đã thấy `COMPLETED`).
```mermaid
stateDiagram-v2
  [*] --> PENDING: đơn xuất hiện trong report
  PENDING --> COMPLETED: Shopee xác nhận hoàn tất
  PENDING --> CANCELLED: hủy
  COMPLETED --> RETURNED: trả hàng/hoàn tiền sau đó
  COMPLETED --> [*]
  CANCELLED --> [*]
  RETURNED --> [*]
```
`status` lạ chưa biết → lưu nguyên văn vào `raw_status`, coi là `PENDING` và gắn cờ cho admin.

## 2. Giao dịch hoàn tiền trong ví (`wallet_entries`)
```mermaid
stateDiagram-v2
  [*] --> pending: đơn khớp user (60% hoa hồng)
  pending --> available: đơn COMPLETED + hold_days, và sync đang healthy
  pending --> cancelled: đơn CANCELLED/RETURNED
  available --> reversed: đơn RETURNED sau khi đã vào available nhưng CHƯA rút
  available --> held: user yêu cầu rút
  held --> paid_out: chi trả xong
  held --> available: từ chối/lỗi chi trả
  paid_out --> [*]
  cancelled --> [*]
  reversed --> [*]
```
Ràng buộc: tổng `available` không bao giờ < 0. Chỉ `available` mới rút được, nên trường hợp trả hàng sau khi rút được giảm thiểu bằng `hold_days`. Nếu vẫn xảy ra, ghi nhận là **lỗ của admin** (`loss_entries`), không trừ âm ví user.

## 3. Yêu cầu rút tiền
```mermaid
stateDiagram-v2
  [*] --> requested
  requested --> approved: admin/staff duyệt
  requested --> rejected: từ chối (hoàn held→available)
  approved --> processing: gửi cổng/chuyển khoản
  processing --> paid: xác nhận thành công
  processing --> failed: lỗi → hoàn tiền về available
  failed --> requested: user gửi lại
  paid --> [*]
  rejected --> [*]
```

## 4. Bài đăng của Muse AI (`posts`, chỉ để thống kê)
```mermaid
stateDiagram-v2
  [*] --> issued: Muse xin link (post_key)
  issued --> reported: nhận được click/đơn đầu tiên
  reported --> scored: đủ dữ liệu (≥ N ngày) để chấm điểm
  issued --> stale: > 30 ngày không có click
  scored --> [*]
  stale --> [*]
```
Không có `draft/approved/published`: việc đăng là của Muse.

## 5. Phiên cookie Shopee (`shopee_sessions`)
```mermaid
stateDiagram-v2
  [*] --> unknown: admin dán cookie
  unknown --> healthy: health-check ok
  healthy --> degraded: 1-2 lần lỗi mạng/5xx
  degraded --> healthy: ok lại
  degraded --> expired: 401/403 liên tiếp
  healthy --> expired: 401/403
  expired --> blocked: 403 kéo dài kể cả cookie mới (IP bị chặn)
  expired --> unknown: admin cập nhật cookie
  blocked --> unknown: đổi IP/proxy + cập nhật
```
Khi `expired/blocked`: cảnh báo, dừng chuyển `pending→available`, vẫn cho nhận click; staff có thể dùng import CSV.
