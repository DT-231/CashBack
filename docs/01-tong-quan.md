# 01 — Tổng quan

## Quyết định của Product Owner (từ Checkpoint 1, 2026-11-27)

| # | Quyết định | Hệ quả |
|---|---|---|
| D1 | Chia hoa hồng **60% user / 40% admin** | Tỷ lệ là cấu hình, lưu snapshot theo từng đơn |
| D2 | Rút tiền: **MVP chuyển khoản thủ công trước** (PO xác nhận 2026-11-27), cổng tự động sau | Thiết kế `PayoutProvider`; MVP chỉ cần `manual` (VietQR + CSV). Adapter cổng (T-042) tách khỏi MVP, làm khi có điều kiện (R-07) |
| D7' | Hosting: **máy nhà + Cloudflare Tunnel** cho web, API, sync; Cloudflare Worker cho `/go`; Neon cho DB. **Không Vercel Hobby** (chỉ phi thương mại), không AWS ở MVP (PO, 2026-11-27) | Xem mục "Cập nhật hạ tầng" ở `06-kien-truc.md`; riêng `sync-worker` vẫn phải chạy IP nhà |
| D3 | **Web trước**, app sau | App mobile = ngoài MVP; API thiết kế để app dùng lại |
| D4 | AI fanpage = **Muse AI** (agent bên ngoài, tự mở FB, tạo bài/video, đăng). Nó gọi API của ta để tìm SP + tạo link | **Không** xây module đăng bài/Graph API/hàng chờ duyệt. Ta cung cấp **Tool API** cho agent |
| D5 | Đăng thẳng, không duyệt | Không có luồng duyệt bài |
| D6 | Không cần quản lý fanpage trong hệ thống | Fanpage chỉ là một giá trị trong `sub_id` (nguồn) |
| D7 | Hạ tầng miễn phí | Xem `06-kien-truc.md` |
| D9 | Hoàn tiền = chia 60% hoa hồng Shopee trả về tài khoản của PO | Rủi ro điều khoản Shopee, xem R-02 |
| D11 | **Không cho số dư âm**; tiền vào "chờ xác nhận", hết hạn trả hàng mới sang "rút được" | Ví 2 ngăn: `pending` / `available` |
| D12 | Tài khoản Shopee Affiliate loại **Cá nhân** | Hạn chế cổng chi trả tự động, thuế cá nhân (R-06, R-07) |
| D13 | Xác thực chỉ **email** + rate limit/IP check/bảo mật khác | Không KYC; chống gian lận bằng hành vi |
| D14 | Đơn mồ côi thuộc về admin | Hàng chờ "đơn mồ côi", staff gán tay khi có khiếu nại hợp lệ |
| D16 | Stack chi phí 0đ do tôi đề xuất | FastAPI + Postgres + Next.js, bỏ Redis ở MVP |

**Giả định tôi tự đặt (PO sửa nếu sai):**
- A1: Đội phát triển = **1 người (PO) + Claude Code + Codex**, ~10–15 giờ/tuần (câu 8 chưa rõ).
- A2: Thời gian giữ `pending` = **đơn `COMPLETED` + 7 ngày**, cấu hình được. Cần PO đối chiếu thời điểm Shopee thực sự trả hoa hồng cho PO (thường là kỳ thanh toán hàng tháng), vì nếu ta trả user trước khi Shopee trả ta thì ta ứng vốn.
- A3: Domain: dùng subdomain miễn phí của Cloudflare lúc đầu; mua domain riêng khi có user thật.
- A4: Khi máy nhà tắt, `/go/` không ghi được click; link dự phòng trỏ thẳng affiliate (vẫn ra tiền, mất log click).

## Tầm nhìn
Website hoàn tiền Shopee Việt Nam: user dán link sản phẩm → nhận link affiliate → mua → khi đơn hoàn tất và hết hạn trả hàng, nhận 60% hoa hồng vào ví và rút về. Song song, Muse AI tự đăng bài fanpage bằng link affiliate có `sub_id` riêng để PO biết bài/ngành nào ra tiền.

## Phạm vi

**MVP (Must):** đăng ký/đăng nhập email; dán link → link affiliate; `/go/` ghi click; đồng bộ đơn từ Shopee; ví chờ/khả dụng/hủy; rút tiền; admin xem user/đơn/rút; Tool API cho Muse; đơn mồ côi; cảnh báo cookie chết; rate limit; backup.

**Should:** cổng chi trả tự động; đối soát tổng; vòng học (insights theo bài/ngành/giờ); chống gian lận nâng cao; import CSV dự phòng.

**Could:** hoàn tiền theo ngành/hạng; referral; Telegram bot cho user.

**Won't (ngoài MVP):** app mobile, extension trình duyệt, đăng bài tự động từ hệ thống ta, KYC, TikTok/Zalo, số dư âm.

## KPI

| KPI | Định nghĩa | Mục tiêu 3 tháng đầu (đề xuất) |
|---|---|---|
| Số user đăng ký / kích hoạt | Có ít nhất 1 link tạo | 200 / 80 |
| Click | Click qua `/go/` + click Shopee ghi nhận | 5.000 |
| CVR | đơn / click (Shopee) | ≥ 1,5% |
| Hoa hồng/tháng | Tổng hoa hồng Shopee ghi nhận | PO đặt |
| Tỷ lệ đơn hủy/trả | đơn hủy / tổng đơn | < 15% (theo dõi) |
| Thời gian đối soát | từ đơn xuất hiện trên Shopee đến vào ví `pending` | < 24 giờ sau khi Shopee hiển thị |
| Độ lệch đối soát | |Shopee − (ví + lợi nhuận)| | 0 đồng |
| Thời gian xử lý rút tiền | từ yêu cầu đến chi trả | < 48 giờ |
