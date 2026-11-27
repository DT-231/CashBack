# ADR 0005 — Web lưu token bằng cookie HttpOnly qua lớp BFF (Next.js), JS trình duyệt không bao giờ thấy token

- **Trạng thái:** đề xuất (chờ PO duyệt). Ngày 2026-11-27.
- **Bối cảnh:** backend cấp `access token` (JWT, 15 phút) và `refresh token` (ngẫu nhiên, 30 ngày, xoay vòng, phát hiện dùng lại) ở `/api/v1/auth/*`; thiết kế dùng chung cho web và app mobile sau này (`docs/refactor/02-target.md`). Web chạy ở Cloudflare Pages (hoặc Vercel), API ở máy nhà sau Tunnel: **hai origin khác site** (chưa có domain riêng, `docs/06`). Web sẽ hiển thị ví, số dư, link affiliate, nên token bị lộ = mất tiền của user.

## Các phương án
| | Cách | Vì sao loại / chọn |
|---|---|---|
| A | Token trong `localStorage`/`sessionStorage` | Một lỗ XSS lấy được cả access và refresh token. **Loại.** |
| B | Access trong bộ nhớ JS, refresh trong cookie do **backend** đặt | Cookie khác site: cần `SameSite=None` + CORS credentials, Safari/Chrome chặn cookie bên thứ ba ⇒ hỏng không đoán trước được. Chỉ khả thi khi web và API cùng domain đăng ký (cần mua domain). **Hoãn**, xem lại khi có domain |
| C | **BFF**: route handler của Next.js đặt cookie HttpOnly trên origin của **web** và chuyển tiếp mọi lời gọi sang API | Trình duyệt chỉ nói chuyện cùng origin (không CORS), JS không đọc được token. **Chọn.** |

## Quyết định (phương án C)
1. **Cookie** (đặt bởi BFF, không bao giờ bởi JS):
   - `__Host-access`: access token; `HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age` = `expires_in`.
   - `__Secure-refresh`: refresh token; `HttpOnly; Secure; SameSite=Strict; Path=/bff; Max-Age=30 ngày` (chỉ gửi tới các route BFF, không bao giờ tới trang HTML; cần cho cả `/bff/auth/*` lẫn `/bff/api/*` vì proxy tự làm mới).
2. **BFF chỉ là ống dẫn và quản lý token.** Không có nghiệp vụ, không tính tiền, không đổi hình dạng dữ liệu. Các route:
   - `POST /bff/auth/{register,login,logout}`; `POST /bff/auth/refresh` (nội bộ).
   - `/bff/api/<path>` chuyển tiếp tới `API_BASE_URL/api/v1/<path>` theo **danh sách cho phép** (đường dẫn + phương thức), gắn `Authorization: Bearer` từ cookie. Gặp `401` thì tự làm mới token **một lần** rồi thử lại; làm mới lỗi (`invalid_refresh`) thì xóa cookie và trả `401 session_expired` để UI chuyển về đăng nhập.
   - `API_BASE_URL` chỉ là biến môi trường **phía server** (không `NEXT_PUBLIC_`). CORS của backend vẫn tắt.
3. **CSRF:** `SameSite=Strict` cộng với kiểm tra bắt buộc cho mọi phương thức ghi: header `X-CSRF: 1` và `Origin` phải trùng origin của web; chỉ nhận `application/json`.
4. **Đăng xuất:** gọi `/api/v1/auth/logout` (backend thu hồi mọi refresh token của user, nghĩa là đăng xuất mọi thiết bị) rồi xóa cookie.
5. **Không bao giờ** log, trả về trong body, hay đưa vào URL: access/refresh token, `Set-Cookie` của backend. Phản hồi lỗi từ API được chuyển nguyên định dạng `{"error":{code,message,request_id}}`.
6. **App mobile sau này** dùng thẳng `/api/v1/auth/*`, lưu token trong Keychain/Keystore; backend không đổi.

## Luật cho giao diện (bắt buộc, kiểm bằng test)
- **UI không tự tính tiền.** Mọi số tiền (`*_vnd`), tỷ lệ (`share_pct`) và mốc thời gian (ví dụ "dự kiến vào ví lúc …") do API trả về; UI chỉ hiển thị và định dạng qua `lib/format.ts`. Cấm nhân/chia/cộng các giá trị tiền, cấm nhân với tỷ lệ, cấm tự cộng `hold_days` vào ngày. Cần số mới thì thêm vào API, không tính ở UI.
- Mọi lời gọi backend đi qua **một** `lib/api-client.ts`; component không gọi `fetch` trực tiếp.
- Không có logic nghiệp vụ trong Next.js ngoài BFF nói ở trên (không server actions xử lý nghiệp vụ).

## Hệ quả và việc còn mở
- **IP người dùng qua BFF (cần xử lý trước khi bật rate limit thật qua web):** nếu mọi lời gọi `/auth/*` đi qua BFF thì backend chỉ thấy IP của Cloudflare, nên giới hạn theo IP (T-013) sẽ gộp mọi user vào chung một bộ đếm. Hướng xử lý: BFF gửi `X-Visitor-IP` kèm bí mật chung `BFF_SHARED_SECRET`; `core/clientip.client_ip` chỉ tin header này khi bí mật khớp (so sánh hằng thời gian). Cần làm ở một task riêng của Claude (đụng `core/`), **trước khi mở đăng ký cho người ngoài**.
- Hai tab làm mới cùng lúc: backend có khoảng ân hạn 10 giây nên không đăng xuất nhầm, nhưng bên thua có thể nhận `401` một lần; BFF thử đọc lại cookie trước khi kết luận.
- Edge runtime của Cloudflare Pages không giữ trạng thái giữa các lần gọi: BFF **không** được dựa vào bộ nhớ tiến trình để khóa.
- Khi có domain riêng (cùng site với API) có thể chuyển sang phương án B mà không đổi UI, vì UI chỉ biết `lib/api-client.ts`.
