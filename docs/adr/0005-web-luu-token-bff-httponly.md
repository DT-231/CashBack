# ADR 0005 — Web lưu token bằng cookie HttpOnly qua lớp BFF (Next.js), JS trình duyệt không bao giờ thấy token

- **Trạng thái:** Accepted (PO chấp nhận 2026-11-27, kèm sửa đổi SameSite ở mục 1).
- **Bối cảnh:** backend cấp `access token` (JWT, 15 phút) và `refresh token` (ngẫu nhiên, 30 ngày, xoay vòng, phát hiện dùng lại) ở `/api/v1/auth/*`; thiết kế dùng chung cho web và app mobile sau này (`docs/refactor/02-target.md`). Web (Next.js, chạy `next start` ở máy nhà, không dùng Vercel Hobby vì chỉ phi thương mại) và API cùng nằm sau một Cloudflare Tunnel; BFF gọi API qua `127.0.0.1`, API chỉ lắng nghe `127.0.0.1` (`docs/06` mục 0). Web sẽ hiển thị ví, số dư, link affiliate, nên token bị lộ = mất tiền của user.

## Các phương án
| | Cách | Vì sao loại / chọn |
|---|---|---|
| A | Token trong `localStorage`/`sessionStorage` | Một lỗ XSS lấy được cả access và refresh token. **Loại.** |
| B | Access trong bộ nhớ JS, refresh trong cookie do **backend** đặt | Backend phải đặt cookie và bật CORS có credentials; access token vẫn nằm trong JS nên XSS vẫn lấy được. **Loại** (có thể xét lại khi UI và API cùng domain đăng ký) |
| C | **BFF**: route handler của Next.js đặt cookie HttpOnly trên origin của **web** và chuyển tiếp mọi lời gọi sang API | Trình duyệt chỉ nói chuyện cùng origin (không CORS), JS không đọc được token. **Chọn.** |

## Quyết định (phương án C)
1. **Cookie** (đặt bởi BFF, không bao giờ bởi JS):
   - `__Host-access`: access token; `HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age` = `expires_in`. **Lax, không phải Strict** (xem "SameSite của cookie truy cập" bên dưới).
   - `__Secure-refresh`: refresh token; `HttpOnly; Secure; SameSite=Strict; Path=/bff; Max-Age=30 ngày` (giữ Strict: chỉ BFF dùng, không cần nhận ra người dùng lúc điều hướng) (chỉ gửi tới `/bff/*`, không tới trang HTML; cần `/bff/api/*` vì BFF tự làm mới khi gặp 401). Môi trường dev (HTTP) dùng tên không tiền tố và không `Secure`.
2. **BFF chỉ là ống dẫn và quản lý token.** Không có nghiệp vụ, không tính tiền, không đổi hình dạng dữ liệu. Các route:
   - `POST /bff/auth/{register,login,logout}`; `POST /bff/auth/refresh` (nội bộ).
   - `/bff/api/<path>` chuyển tiếp tới `API_BASE_URL/api/v1/<path>` theo **danh sách cho phép** (đường dẫn + phương thức), gắn `Authorization: Bearer` từ cookie. Gặp `401` thì tự làm mới token **một lần** rồi thử lại; làm mới lỗi (`invalid_refresh`) thì xóa cookie và trả `401 session_expired` để UI chuyển về đăng nhập.
   - `API_BASE_URL` chỉ là biến môi trường **phía server** (không `NEXT_PUBLIC_`). CORS của backend vẫn tắt.
3. **CSRF** (trả lời câu hỏi cookie HttpOnly có bị CSRF không: có, nên chặn nhiều lớp):
   - `SameSite=Strict` cho cookie refresh và `SameSite=Lax` cho cookie truy cập (lý do ở dưới): trình duyệt không gửi chúng trong request **ghi** xuất phát từ site khác (Lax chỉ gửi cho điều hướng cấp cao dạng GET).
   - Mọi phương thức ghi (`POST/PUT/PATCH/DELETE`) bắt buộc có header `X-CSRF: 1` **và** `Origin` trùng chính xác origin của web (so sánh nguyên chuỗi, thiếu `Origin` thì từ chối); chỉ nhận `Content-Type: application/json`. Trang của site khác không thêm được header tùy biến mà không qua CORS preflight, và BFF không bật CORS, nên request bị chặn.
   - Không dùng CSRF token đồng bộ (synchronizer token): header tùy biến + kiểm tra Origin + SameSite=Strict đã đủ cho API chỉ-JSON, và token trong trang sẽ thêm trạng thái phải giữ. Nếu sau này có form HTML thường hoặc upload `multipart`, phải thêm CSRF token trước.
   - Request `GET` không bao giờ thay đổi dữ liệu (allowlist chỉ cho `GET` đọc). Đây là điều kiện bắt buộc của Lax: **mọi route GET thêm vào allowlist phải chỉ-đọc**; thao tác ghi luôn là `POST/PUT/PATCH/DELETE`.

### SameSite của cookie truy cập: Lax (PO hỏi 2026-11-27)
- **Vấn đề:** cookie `Strict` không được gửi khi người dùng bấm link từ site khác (Facebook, Zalo) vào web, nên request điều hướng đầu tiên trông như chưa đăng nhập. Chuyện này chỉ gây hại nếu quyết định "đã đăng nhập" được đưa ra **ở request điều hướng** (middleware, trang render phía server). Thiết kế hiện tại hỏi `GET /bff/api/auth/me` bằng `fetch` từ trang của chính ta; request đó cùng site nên cookie Strict vẫn được gửi, tức là hôm nay chưa lỗi. Dù vậy ta chọn Lax cho cookie truy cập để không bị cấm làm middleware/SSR cho trang thành viên và tránh nháy "chưa đăng nhập" khi tới từ link ngoài.
- **Lax vẫn an toàn vì:** (1) mọi request ghi bắt buộc `X-CSRF: 1` + `Origin` khớp + JSON (test cho cả POST/PUT/PATCH/DELETE); (2) Lax chỉ gửi cookie cho điều hướng GET cấp cao, và các GET đều chỉ-đọc; (3) trang của kẻ tấn công có thể dẫn người dùng tới `GET /bff/api/me/wallet` nhưng không đọc được phản hồi (không CORS); (4) ngoại lệ "Lax+POST" 2 phút của Chrome chỉ áp dụng cho cookie **không khai báo** SameSite, ta khai báo rõ `Lax`.
- **Rủi ro còn lại khi đổi:** mất một lớp chống CSRF (SameSite không còn chặn GET điều hướng), nên toàn bộ an toàn dựa vào luật "GET chỉ-đọc" và kiểm tra `X-CSRF`/`Origin`. Một GET có tác dụng phụ thêm nhầm vào allowlist sẽ thành lỗ hổng CSRF. Giảm thiểu: test khóa allowlist (chỉ đúng các GET đã biết, mọi phương thức ghi khác bị từ chối) và luật review ở trên. Lax không bảo vệ trước kẻ tấn công **cùng site** (subdomain khác của cùng domain đăng ký), nhưng Strict cũng không; hãy giữ web trên domain riêng không chia sẻ với nội dung người dùng.
- **Cookie refresh giữ Strict** vì chỉ được dùng trong lúc BFF xử lý một lời gọi `fetch` cùng site (không bao giờ cần ở request điều hướng).
4. **Đăng xuất:** gọi `/api/v1/auth/logout` (backend thu hồi mọi refresh token của user, nghĩa là đăng xuất mọi thiết bị) rồi xóa cookie.
5. **Không bao giờ** log, trả về trong body, hay đưa vào URL: access/refresh token, `Set-Cookie` của backend. Phản hồi lỗi từ API được chuyển nguyên định dạng `{"error":{code,message,request_id}}`.
6. **Backend vẫn nhận bearer token** (trả lời câu hỏi app iOS gọi thẳng): backend chỉ đọc `Authorization: Bearer <access>`, **không đọc cookie nào**, nên cookie không phải đường xác thực của backend và CSRF không áp dụng cho backend. App iOS gọi thẳng `/api/v1/auth/*`, lưu token trong Keychain, gửi bearer; không đi qua BFF và không cần đổi backend. Cookie HttpOnly chỉ là cách **BFF** giữ token hộ trình duyệt.
7. **Bí mật chung BFF↔backend** (`BFF_SHARED_SECRET`, dùng ở T-017): chỉ là biến môi trường **phía server** của Next.js và của backend, **không có tiền tố `NEXT_PUBLIC_`** (Next.js nhúng mọi biến `NEXT_PUBLIC_*` vào JS gửi trình duyệt). Chỉ đọc trong code route handler của BFF, không đưa vào bundle client, không log, không đưa vào `.env.example` giá trị thật. Test của frontend (`tests/ui-rules`) có luật cấm `NEXT_PUBLIC_` xuất hiện trong mã nguồn; mất secret thì xoay ở cả hai phía.

## Luật cho giao diện (bắt buộc, kiểm bằng test)
- **UI không tự tính tiền.** Mọi số tiền (`*_vnd`), tỷ lệ (`share_pct`) và mốc thời gian (ví dụ "dự kiến vào ví lúc …") do API trả về; UI chỉ hiển thị và định dạng qua `lib/format.ts`. Cấm nhân/chia/cộng các giá trị tiền, cấm nhân với tỷ lệ, cấm tự cộng `hold_days` vào ngày. Cần số mới thì thêm vào API, không tính ở UI.
- Mọi lời gọi backend đi qua **một** `lib/api-client.ts`; component không gọi `fetch` trực tiếp.
- Không có logic nghiệp vụ trong Next.js ngoài BFF nói ở trên (không server actions xử lý nghiệp vụ).

## Hệ quả và việc còn mở
- **IP người dùng qua BFF (CHẶN việc mở đăng ký cho người ngoài; backlog T-017 và T-016):** nếu mọi lời gọi `/auth/*` đi qua BFF thì backend chỉ thấy IP của Cloudflare, nên giới hạn theo IP (T-013) sẽ gộp mọi user vào chung một bộ đếm. Hướng xử lý: BFF lấy IP thật từ `CF-Connecting-IP` rồi gửi `X-Visitor-IP` kèm `X-BFF-Secret`; `core/clientip.client_ip` chỉ tin `X-Visitor-IP` khi secret khớp (so sánh hằng thời gian), nếu không thì dùng IP kết nối. App iOS gọi thẳng nên không có header này và bị tính theo IP kết nối. API chỉ bind `127.0.0.1`; khởi động bị từ chối nếu `TRUST_PROXY_HEADERS=1` mà bind ngoài localhost (T-016, đã làm).
- Hai tab làm mới cùng lúc: backend có khoảng ân hạn 10 giây nên không đăng xuất nhầm, nhưng bên thua có thể nhận `401` một lần; BFF thử đọc lại cookie trước khi kết luận.
- BFF chạy tiến trình Node ở máy nhà nên có thể khởi động lại bất cứ lúc nào: không giữ trạng thái quan trọng trong bộ nhớ tiến trình (không khóa làm mới token bằng biến toàn cục).
- Nếu sau này chuyển web sang nơi khác (có domain riêng) vẫn giữ BFF; đổi phương án chỉ ảnh hưởng `lib/bff`, không ảnh hưởng UI, vì UI chỉ biết `lib/api-client.ts`.
