# 10 — Ma trận rủi ro

Thang: Xác suất (X) và Tác động (T) từ 1 (thấp) đến 5 (cao); Điểm = X×T. Mục "Cần PO" là việc ta **không tự giả định**.

| ID | Rủi ro | X | T | Điểm | Cách giảm | Cần PO |
|---|---|---|---|---|---|---|
| R-01 | **Phụ thuộc cookie + endpoint nội bộ Shopee**: hết hạn, 403, đổi format | 5 | 5 | 25 | Health-check 15 phút; cảnh báo; dừng cộng tiền khi chưa sync; import CSV thủ công; parser có test với fixture HAR thật; lỗi có kiểu; chạy IP nhà; không cắt dữ liệu im lặng | Cookie lấy thủ công |
| R-02 | **Điều khoản Shopee Affiliate**: mô hình chia lại hoa hồng/cashback cho người dùng có thể bị cấm hoặc cần đăng ký kênh (website, fanpage). Vi phạm có thể bị khóa tài khoản và **mất hoa hồng chưa trả** | 4 | 5 | 20 | **Không tự giả định.** PO đọc điều khoản hiện hành và/hoặc hỏi quản lý tài khoản Shopee bằng văn bản; đăng ký các kênh (web, fanpage) trong tab "Thông tin truyền thông" của tài khoản; gắn chặn "tắt chia tiền" bằng cờ cấu hình nếu bị từ chối; chỉ trả cho user từ tiền Shopee **đã** trả | ✔ trước khi mở cho user ngoài |
| R-03 | **Dòng tiền**: ta trả user trước khi Shopee trả ta (Shopee thanh toán theo kỳ) → ứng vốn, rủi ro nếu bị trừ lại | 3 | 4 | 12 | `hold_days` đủ dài; chỉ chuyển sang rút được khi đơn `COMPLETED` và đối chiếu lịch trả của Shopee; đối soát hằng tháng | ✔ lịch thanh toán thực tế của Shopee |
| R-04 | **Đơn hủy/trả sau khi user đã rút** | 3 | 3 | 9 | Không số dư âm (D11); chỉ rút phần `available`; `hold_days`; ghi `loss_entries` nếu xảy ra | — |
| R-05 | **Sai lệch làm tròn** đơn vị ×1e5 | 4 | 2 | 8 | Số nguyên bigint, làm tròn xuống, test thuộc tính; phần dư thuộc admin; đối soát đến từng đồng | — |
| R-06 | **Thuế & pháp lý**: thu nhập affiliate của cá nhân và khoản chi hoàn tiền cho user có nghĩa vụ thuế/đăng ký kinh doanh; tài khoản Shopee Affiliate là **Cá nhân**. | 3 | 4 | 12 | Ghi nhận đầy đủ sổ sách trong hệ thống để kế toán dùng; **cần tư vấn kế toán/luật**, ta không kết luận | ✔ |
| R-07 | **Cổng chi trả tự động** thường yêu cầu pháp nhân/hợp đồng doanh nghiệp; phí và điều kiện thay đổi; cá nhân có thể không đủ điều kiện | 4 | 3 | 12 | **PO đã chốt (2026-11-27): MVP chuyển khoản thủ công** (`PayoutProvider.manual`, VietQR + CSV); cổng tự động tách khỏi MVP; chọn cổng không cần thẻ/phí cố định; chỉ bật khi PO xác nhận điều kiện | ✔ chọn cổng và điều kiện |
| R-08 | **Gian lận**: tự mua qua link mình để lấy 60%, farm tài khoản (chỉ cần email), đơn ảo, bot tạo click | 4 | 4 | 16 | Rate limit + xác minh email + chặn email dùng một lần; cờ cùng `ip_hash`/UA; tự mua (chủ tài khoản = người mua) khó phát hiện ở phía ta nên dựa vào `hold_days` và tỷ lệ hủy; giới hạn số tài khoản/IP; staff xem `fraud_flags` | — |
| R-09 | **Bảo mật cookie Shopee** (chìa khóa tài khoản kiếm tiền) | 3 | 5 | 15 | Mã hóa at-rest, không log, không commit, không API đọc, chỉ admin; quét secret trong CI; xoay cookie khi nghi lộ | — |
| R-10 | **Lộ API công khai không auth** qua tunnel (S1–S3) | 4 | 5 | 20 | Bắt buộc API key/RBAC trước khi expose; CORS hạn chế; `/go/` chỉ đọc đích từ DB | PO đồng ý bật auth khi lên tunnel |
| R-11 | **Máy nhà tắt/mất mạng**: sync dừng (click vẫn ghi nếu `/go` chạy trên Cloudflare Worker) | 3 | 2 | 6 | `/go` trên Worker; link `direct_url`; sync chạy bù 60 ngày; cảnh báo "không có sync > 24h"; UPS/tự khởi động lại | Câu 17 |
| R-12 | **Giới hạn thật của `sub_id`** chưa kiểm chứng (độ dài, ký tự) | 3 | 4 | 12 | Giới hạn tự đặt thấp (tổng ≤ 32); redirect đã test giữ nguyên tới 89 ký tự; còn cần PO kiểm cột sub_id trong báo cáo (`07-du-lieu.md` mục 5); codec versioned | ✔ kiểm cột sub_id trong báo cáo |
| R-13 | **Chính sách Facebook / Muse AI**: spam, giới hạn tần suất, vi phạm chính sách link affiliate | 3 | 3 | 9 | Ngoài hệ thống ta; Muse chịu trách nhiệm tần suất; ta chỉ cung cấp link. Ghi nhận để PO biết nếu fanpage bị phạt thì ảnh hưởng nguồn hoa hồng | Muse AI là ai/chạy ở đâu |
| R-14 | **Đơn mồ côi chiếm nhiều** (user dùng link Shopee ngoài web, đổi thiết bị, Shopee không giữ `utm_content`) | 3 | 3 | 9 | Giám sát tỷ lệ mồ côi; khiếu nại; cho staff gán tay | — |
| R-15 | **Quá tải một người** (1 dev, 10–15 giờ/tuần) | 4 | 3 | 12 | Backlog ưu tiên Must; giao Codex CRUD/UI/test; MVP cắt bớt (Should/Could đẩy sau) | Câu 8 |
| R-16 | **Mất dữ liệu** (đĩa hỏng, xóa nhầm) | 2 | 5 | 10 | Backup hằng ngày + test khôi phục; sổ cái chỉ thêm | — |
| R-17 | **Dữ liệu cá nhân user bị lộ** | 2 | 4 | 8 | Mã hóa số tài khoản, tối thiểu hóa dữ liệu, TLS, kiểm thử bảo mật | ✔ tư vấn pháp lý |

Ưu tiên xử lý trước khi mở cho user thật: **R-02, R-10, R-01, R-08**.
