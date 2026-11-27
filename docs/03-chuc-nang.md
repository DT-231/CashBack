# 03 — Chức năng theo module (MoSCoW)

M = Must, S = Should, C = Could, W = Won't (MVP)

## M1. Tài khoản & bảo mật
| Chức năng | Ưu tiên | Người dùng | Ghi chú |
|---|---|---|---|
| Đăng ký email + xác minh email | M | Khách | Chống email rác, giới hạn đăng ký theo IP |
| Đăng nhập/đăng xuất, quên mật khẩu | M | Thành viên | Mật khẩu argon2; phiên cookie HttpOnly |
| Phân quyền member/staff/admin | M | Hệ thống | RBAC |
| Rate limit, chặn IP, audit log | M | Hệ thống | Lưu trong Postgres, không cần Redis |
| 2FA cho admin | S | Admin | TOTP |

## M2. Link & click
| Chức năng | Ưu tiên | Người dùng | Ghi chú |
|---|---|---|---|
| Dán link Shopee → chuẩn hóa `shop_id/item_id` | M | Thành viên | Chấp nhận link ngắn `s.shopee.vn`? Ghi chú: cần theo redirect, chỉ cho phép host Shopee (chống SSRF) |
| Trả link `/go/<code>` (ghi click) + link trực tiếp dự phòng | M | Thành viên | Mỗi click sinh `sub_id` riêng |
| Lịch sử link/click của tôi | M | Thành viên | |
| Cảnh báo sản phẩm không có hoa hồng | S | Thành viên | Chỉ khi có feed/dữ liệu |

## M3. Đồng bộ Shopee & đơn
| Chức năng | Ưu tiên | Người dùng | Ghi chú |
|---|---|---|---|
| Kéo click/đơn định kỳ, quét lại 60 ngày | M | sync-worker | Idempotent, chạy bù |
| Khớp `sub_id` → nguồn (user/bài) | M | sync-worker | Codec versioned |
| Hàng đơn mồ côi + gán tay | M | Staff | Mặc định thuộc admin |
| Health-check cookie + cảnh báo Telegram/Email | M | Admin | Dừng cộng tiền khi chưa đồng bộ được |
| Import CSV báo cáo (dự phòng) | S | Staff | Cùng pipeline với sync |
| Trang cập nhật cookie (mã hóa at-rest) | M | Admin | Không hiển thị lại giá trị |

## M4. Ví & hoàn tiền
| Chức năng | Ưu tiên | Người dùng | Ghi chú |
|---|---|---|---|
| Ví 2 ngăn: chờ xác nhận / rút được | M | Thành viên | Số nguyên, sổ cái bất biến |
| Tự chuyển `pending`→`available` sau hạn | M | Job | COMPLETED + 7 ngày (cấu hình) |
| Hủy/trả hàng → giao dịch `cancelled` | M | Job | Không cho số dư âm |
| Tỷ lệ hoàn toàn cục 60% | M | Admin | Snapshot theo đơn |
| Tỷ lệ theo ngành/hạng | C | Admin | |
| Referral | C | Thành viên | |

## M5. Rút tiền
| Chức năng | Ưu tiên | Người dùng | Ghi chú |
|---|---|---|---|
| Yêu cầu rút (ngưỡng tối thiểu, khóa số dư) | M | Thành viên | |
| Duyệt/từ chối + chi trả thủ công (VietQR/CSV) | M | Admin/Staff | `PayoutProvider.manual` |
| Chi trả qua cổng (tự động) | S | Hệ thống | Phụ thuộc R-07 |
| Lịch sử rút | M | Thành viên | |

## M6. Tool API cho Muse AI
| Chức năng | Ưu tiên | Người dùng | Ghi chú |
|---|---|---|---|
| API key riêng cho agent | M | Admin tạo | Chỉ scope `agent` |
| `search` SP (feed→api→browser) | M | Muse | Giữ code hiện có |
| `link` theo bài: `post_key` → `sub_id` (nguồn `post`) | M | Muse | Bài đăng = 1 `post_key` |
| `insights`: doanh thu theo bài/ngành/giờ | S | Muse | Đọc từ DB của ta, không gọi Shopee trực tiếp |

## M7. Admin
| Chức năng | Ưu tiên | Ghi chú |
|---|---|---|
| Dashboard: user, click, đơn, hoa hồng, ví | M | |
| Quản lý user (khóa/mở) | M | |
| Quản lý đơn, đơn mồ côi | M | |
| Duyệt rút tiền | M | |
| Đối soát tổng | S | Shopee − chia user − lợi nhuận giữ lại |
| Cấu hình tỷ lệ, ngưỡng, thời gian giữ | M | |
| Giám sát sức khỏe: cookie, sync, backup | M | |
| Phát hiện gian lận (tự mua, cùng IP, hủy bất thường) | S | Dạng cờ để staff xem |
| Khiếu nại "mua rồi chưa thấy đơn" | S | Tra theo `click_id` |

## M8. Ngoài MVP
App mobile (W), extension (W), đăng bài tự động từ hệ thống (W, do Muse lo), KYC (W), kênh Zalo/TikTok (W).
