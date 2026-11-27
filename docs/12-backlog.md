# 12 — Product Backlog

Mẫu: *Là … tôi muốn … để …*; acceptance criteria dạng Given/When/Then; `Owner` = agent làm chính (Claude giữ kiến trúc/ví/bảo mật, Codex làm CRUD/UI/test/script).
Nguồn dữ liệu máy đọc: `backlog/issues.csv` (cùng nội dung).

## Điều kiện mở đăng ký cho người ngoài

**T-061 (đưa web ra Internet cho người ngoài) không được bắt đầu khi chưa có đủ dòng "Xong".** Người duyệt từng mục là PO; Claude cập nhật bảng khi có bằng chứng (commit, ghi chú, ảnh chụp). Cập nhật lần cuối: 2026-11-28.

**Cờ `WITHDRAWALS_ENABLED=0` ở MỌI môi trường (dev, thử nghiệm, production) cho tới khi hết bảng này** (PO, 2026-11-28). Khởi động bật cờ này còn bị từ chối nếu khóa mã hóa yếu, admin chưa bắt buộc TOTP, hoặc user DB là superuser/chủ bảng.

| # | Mục | Trạng thái | Ai làm | Ghi chú / bằng chứng |
|---|---|---|---|---|
| 1 | T-017 xong (X-Visitor-IP + bí mật chung; kèm T-016) | **Xong** | Claude | merge `f6b29c8`, `b437d17` |
| 2 | Có domain riêng trên Cloudflare DNS (Tunnel hostname cố định, cookie `__Host-`, `WEB_ORIGIN`); không dùng tunnel nhanh | Chưa | PO | `docs/06` mục 0 |
| 3 | Domain đã đăng ký làm kênh quảng bá trong hồ sơ Affiliate Shopee, và tên domain không chứa thương hiệu Shopee | Chưa | PO | PO kiểm điều khoản về dùng tên/nhãn hiệu |
| 4 | Đơn mua thử thật khớp sub_id (`utm_content` còn nguyên chữ ký, giải mã `ok`) | Chưa | PO mua và gửi dữ liệu; Claude giải mã | `docs/runbooks/live-attribution-test.md` |
| 5 | PO xác nhận với Shopee (bằng văn bản) về mô hình cashback (R-02) | Chưa | PO | |
| 6 | Trang Điều khoản và Chính sách quyền riêng tư: bản nháp rồi tư vấn pháp lý (R-06, R-17) | Chưa (T-064) | Claude viết nháp; PO đưa luật sư | |
| 7 | `audit_logs` xong (ai, hành động, đối tượng, thời điểm, IP băm; không mật khẩu/token/số tài khoản) | **Xong** | Claude | merge `d8073c0` |
| 8 | Admin bật đăng nhập hai lớp TOTP trước khi bật rút tiền thật (T-019) | Mã xong, đã gộp vào `autopilot/main` (chờ PO merge vào `main`); admin bật thật: **Chưa** | Claude (mã); PO (bật TOTP cho tài khoản admin thật) | `docs/runbooks/admin-mfa.md` |
| 9 | `BANK_ENC_KEY` sao lưu NGOÀI `.env` (hai nơi, tách bản sao lưu DB) | Chưa | PO | `docs/runbooks/withdrawals.md` |
| 10 | Ứng dụng chạy bằng tài khoản DB riêng `cashback_app` (không sở hữu bảng, không TRUNCATE, không sửa/xóa sổ cái và `audit_logs`) | Script, test, kiểm tra lúc khởi động: **xong** (T-040); triển khai thật: **Chưa** | Claude (script/test); PO (tạo role, đổi `DATABASE_URL` của API) | `infra/db/app-role.sql`, `docs/runbooks/db-roles.md` |
| 11 | T-041 giao diện rút tiền (người dùng) và admin chi trả hoạt động (kể cả CSV) | Backend/BFF xong (`prep/T-041`); giao diện: Codex đang làm | Claude (backend/BFF); Codex (UI) | `backlog/tasks/T-041a.md`, `T-041b.md` |

Ghi chú: các mục trên là điều kiện **mở cho người ngoài**. Dùng nội bộ (chỉ PO và người quen, không quảng bá) vẫn có thể thử trên máy mình bằng tunnel nhanh, với `WITHDRAWALS_ENABLED=0`.

## E0 — Nền tảng, hạ tầng, vận hành  (45 điểm)

### T-001: Là dev, tôi muốn monorepo có lint/format/.gitignore/AGENTS.md để hai agent làm cùng luật
- Loại: chore · 3 điểm · Must · Sprint 0 · Owner: claude
- Acceptance criteria:
  - Given repo mới When chạy lint Then pass
  - Given file .env/cookie When git status Then bị ignore
  - Given Codex mở repo When đọc AGENTS.md Then thấy lệnh chạy/test, quy ước sub_id và quy tắc an toàn

### T-002: Là dev, tôi muốn docker compose up chạy đủ dịch vụ để phát triển cục bộ
- Loại: feature · 5 điểm · Must · Sprint 0 · Owner: codex · Phụ thuộc: T-001
- Acceptance criteria:
  - Given máy sạch When docker compose up Then Postgres, api, web, link-api, sync-worker (job rỗng) healthy
  - Given MOCK=1 When gọi /health Then ok và không lộ secret

### T-003: Là dev, tôi muốn CI GitHub Actions chạy lint và test để không merge code hỏng
- Loại: chore · 2 điểm · Must · Sprint 0 · Owner: codex · Phụ thuộc: T-001
- Acceptance criteria:
  - Given PR When push Then CI chạy lint+test
  - Given test hồi quy make_link fail When CI Then PR bị chặn

### T-005: Là dev, tôi muốn migration Postgres đúng ERD cùng dữ liệu seed
- Loại: feature · 5 điểm · Must · Sprint 0 · Owner: claude · Phụ thuộc: T-002
- Acceptance criteria:
  - Given DB trống When alembic upgrade head Then tạo đủ bảng như 07-du-lieu.md
  - Given seed When chạy Then có 1 admin và 2 member mẫu
  - Given alembic downgrade When chạy Then về trạng thái trống
  - Given wallets When ghi available âm Then DB từ chối (CHECK)

### T-007: Là dev, tôi muốn client Shopee giả (MOCK=1) và fixture từ HAR để test không gọi live
- Loại: feature · 3 điểm · Must · Sprint 0 · Owner: codex · Phụ thuộc: T-001
- Acceptance criteria:
  - Given MOCK=1 When sync chạy Then đọc fixture và không gọi mạng
  - Given fixture HAR When parse Then ra đúng 1 đơn 4.037,5đ

### T-060: Là admin, tôi muốn backup tự động mỗi ngày và test khôi phục
- Loại: feature · 3 điểm · Must · Sprint 6 · Owner: codex · Phụ thuộc: T-002
- Acceptance criteria:
  - Given 03:00 When job Then pg_dump nén mã hóa lưu ổ ngoài + Drive
  - Given file backup When restore sang DB trống Then dữ liệu khớp
  - Given backup lỗi When job Then cảnh báo

### T-061: Là PO, tôi muốn chạy web (Next.js) và backend ở máy nhà qua chung một Cloudflare Tunnel
- **Chỉ bắt đầu khi đã tick đủ "Điều kiện mở đăng ký cho người ngoài" ở đầu file này.**
- Loại: feature · 5 điểm · Must · Sprint 6 · Owner: claude · Phụ thuộc: T-002, T-012
- Acceptance criteria:
  - Given tunnel When truy cập từ Internet Then chỉ route cho phép được expose
  - Given DATABASE_URL đổi sang Neon When chạy Then app hoạt động không sửa code
  - Given máy tắt When user dùng web Then hiện báo bảo trì, direct_url vẫn hoạt động

### T-064: Là PO, tôi muốn Điều khoản và Chính sách quyền riêng tư (bản nháp để luật sư xem)
- Loại: docs · 3 điểm · Must · Sprint 6 · Owner: claude
- Acceptance criteria:
  - Given đăng ký When user xem Then có trang và checkbox đồng ý
  - Given bản nháp When gửi PO Then đánh dấu cần tư vấn pháp lý

### T-065: Là admin, tôi muốn log có cấu trúc, che bí mật và trang health
- Loại: feature · 3 điểm · Must · Sprint 6 · Owner: codex · Phụ thuộc: T-002
- Acceptance criteria:
  - Given log When có cookie/token Then bị che
  - Given /admin/health When mở Then thấy DB, sync, cookie, backup

### T-070: Là PO, tôi muốn thử nghiệm với vài user thật và 1 đơn thật (UAT)
- Loại: test · 8 điểm · Must · Sprint 7 · Owner: claude · Phụ thuộc: T-041, T-061
- Acceptance criteria:
  - Given 5 user thân When chạy từ đăng ký tới đơn pending Then không lỗi chặn
  - Given 1 đơn thật COMPLETED When qua hạn Then vào available và rút thủ công thành công
  - Given kết quả When tổng hợp Then có danh sách lỗi và quyết định mở rộng

### T-071: Là PO, tôi muốn rà soát bảo mật trước khi mở rộng
- Loại: test · 5 điểm · Must · Sprint 7 · Owner: claude · Phụ thuộc: T-061
- Acceptance criteria:
  - Given checklist OWASP cơ bản When rà Then không còn lỗi cao
  - Given tunnel When quét Then không lộ route nội bộ
  - Given quét secret When chạy Then sạch

## E1 — Quy ước sub_id và tạo link  (7 điểm)

### T-004: Là hệ thống, tôi muốn codec sub_id v1 có chữ ký để truy ngược đơn về đúng nguồn
- Loại: feature · 5 điểm · Must · Sprint 0 · Owner: claude
- Acceptance criteria:
  - Given (type=u,user=123,click=98765) When encode Then ra 5 slot [0-9a-z] không có '-', độ dài trong giới hạn
  - Given kết quả encode When decode Then ra đúng user và click
  - Given chữ ký bị sửa When decode Then trả invalid và đơn thành mồ côi
  - Given 'fb01----' When decode Then trả legacy
  - Given id = 36^8-1 When encode Then tổng độ dài ≤ 32; id lớn hơn bị từ chối

### T-006: Là PO, tôi muốn test hồi quy make_link để refactor không làm hỏng link đã verify
- Loại: test · 2 điểm · Must · Sprint 0 · Owner: claude
- Acceptance criteria:
  - Given template mặc định When make_link Then URL giống hệt bản v1.2 cho 5 mẫu
  - Given test_offline.py cũ When chạy sau refactor Then 16/16 pass

## E2 — Tài khoản và bảo mật  (18 điểm)

### T-010: Là khách, tôi muốn đăng ký và đăng nhập bằng email để dùng dịch vụ
- Loại: feature · 5 điểm · Must · Sprint 1 · Owner: codex · Phụ thuộc: T-005
- Acceptance criteria:
  - Given email hợp lệ When đăng ký Then tạo user unverified, mật khẩu argon2
  - Given thông tin đúng When đăng nhập Then nhận cookie HttpOnly
  - Given sai mật khẩu 5 lần When thử Then bị khóa tạm theo IP+email

### T-011: Là thành viên, tôi muốn xác minh email và quên mật khẩu để lấy lại tài khoản
- Loại: feature · 5 điểm · Must · Sprint 1 · Owner: codex · Phụ thuộc: T-010
- Acceptance criteria:
  - Given token hợp lệ When xác minh Then user active
  - Given token đã dùng/hết hạn When dùng Then báo lỗi
  - Given email không tồn tại When quên mật khẩu Then vẫn trả 202

### T-012: Là admin, tôi muốn phân quyền member/staff/admin để tách trách nhiệm
- Loại: feature · 3 điểm · Must · Sprint 1 · Owner: claude · Phụ thuộc: T-010
- Acceptance criteria:
  - Given member When gọi /admin/* Then 403
  - Given staff When PUT /admin/shopee-session Then 403
  - Given member A When đọc dữ liệu member B Then 404

### T-013: Là hệ thống, tôi muốn rate limit, chặn IP và audit log để chống lạm dụng
- Loại: feature · 5 điểm · Must · Sprint 1 · Owner: claude · Phụ thuộc: T-010
- Acceptance criteria:
  - Given > N yêu cầu/phút từ 1 IP When gọi đăng ký Then 429
  - Given thao tác admin When thực hiện Then có dòng audit_logs (ai, gì, lúc nào)
  - Given lưu IP When ghi Then chỉ lưu ip_hash HMAC

### T-016: Là hệ thống, tôi muốn từ chối khởi động nếu TRUST_PROXY_HEADERS=1 mà API bind 0.0.0.0
- Loại: chore · 2 điểm · Must · Sprint 1 · Owner: claude · Phụ thuộc: T-013
- Acceptance criteria:
  - Given TRUST_PROXY_HEADERS=1 và HOST=0.0.0.0 When khởi động Then thoát lỗi rõ ràng
  - Given TRUST_PROXY_HEADERS=1 và HOST=127.0.0.1 When khởi động Then chạy
  - Given TRUST_PROXY_HEADERS=0 When khởi động Then chạy bình thường

### T-017: [CHẶN MỞ ĐĂNG KÝ CHO NGƯỜI NGOÀI] BFF chuyển IP thật qua X-Visitor-IP kèm bí mật chung
- Loại: feature · 3 điểm · Must · Sprint 1 · Owner: claude · Phụ thuộc: T-013, T-033
- **Không mở đăng ký cho người ngoài khi T-017 và T-016 chưa xong** (qua BFF backend chỉ thấy một IP, giới hạn theo IP gộp mọi khách).
- Acceptance criteria:
  - Given BFF nhận CF-Connecting-IP hợp lệ When gọi backend Then gửi X-Visitor-IP và X-BFF-Secret
  - Given backend nhận X-Visitor-IP với secret đúng (so sánh hằng thời gian) When tính key Then dùng IP đó
  - Given secret sai hoặc thiếu When có X-Visitor-IP Then bỏ qua header, dùng IP kết nối
  - Given BFF_SHARED_SECRET Then chỉ ở env phía server, không NEXT_PUBLIC_
  - Given hai khách khác IP qua BFF When đăng nhập sai Then bộ đếm tách riêng

### T-018: Là PO, tôi muốn đổi SUBID_SECRET mà đơn từ link đã phát hành vẫn quy được về user
- Loại: feature · 3 điểm · Should · Sprint 1 · Owner: claude · Phụ thuộc: T-010. **Chưa làm** (ghi lại 2026-11-27).
- Bối cảnh: `core/subid` chỉ hỗ trợ MỘT khóa (`SUBID_SECRET`). Đổi hoặc mất khóa thì mọi `utm_content` đã phát hành thành `invalid` (chữ ký sai) và đơn rơi vào hàng đơn mồ côi, không quy được về user.
- Acceptance criteria:
  - Given `SUBID_SECRET_PREVIOUS` (danh sách khóa cũ) When giải mã sub_id ký bằng khóa cũ Then `ok` (thử khóa hiện tại trước, rồi khóa cũ)
  - Given link mới When tạo Then luôn ký bằng khóa hiện tại
  - Given chữ ký chỉ 3 ký tự (không có id khóa) When thử nhiều khóa Then việc khớp nhầm bị chặn bởi kiểm tra sở hữu (click/link thuộc đúng user) của attribution, có test về khả năng khớp nhầm
  - Given khóa cũ quá ngắn hoặc trùng khóa hiện tại When khởi động Then từ chối
  - Given runbook When đọc Then có quy trình xoay khóa và việc sao lưu khóa ngoài `.env`

### T-019: Là admin, tôi muốn đăng nhập hai lớp (TOTP) để tài khoản admin không bị chiếm
- Loại: feature · 5 điểm · Must (trước khi bật rút tiền thật) · Sprint 2 · Owner: claude · Phụ thuộc: T-010, T-040. **Đã làm ở nhánh `task/T-019`, chờ PO duyệt merge** (ghi 2026-11-28).
- Acceptance criteria:
  - Given admin chưa bật TOTP When gọi endpoint admin (duyệt, từ chối, chi trả, xem số tài khoản) Then 403 `mfa_required`
  - Given admin đăng ký TOTP When quét mã và nhập mã đúng Then bật; mã khôi phục hiện đúng một lần, lưu dạng băm
  - Given mã TOTP sai hoặc dùng lại trong cùng cửa sổ When đăng nhập Then từ chối; có rate limit
  - Given bí mật TOTP When lưu Then mã hóa như `BANK_ENC_KEY` (AES-GCM, có key_id), không vào log/audit/response
  - Given bật/tắt/đổi TOTP When thực hiện Then ghi `audit_logs`

## E3 — Link của user và redirect /go  (13 điểm)

### T-014: Là thành viên, tôi muốn dán link Shopee để nhận link của mình
- Loại: feature · 5 điểm · Must · Sprint 1 · Owner: codex · Phụ thuộc: T-004, T-005, T-012
- Acceptance criteria:
  - Given link shopee.vn dạng -i.shop.item When POST /links Then trả go_url và direct_url
  - Given host không thuộc Shopee When POST Then 400
  - Given link ngắn s.shopee.vn When POST Then theo redirect tối đa 3 lần, chỉ tới host Shopee
  - Given cùng user dán lại cùng SP When POST Then tái dùng link, không ghi đè đích

### T-015: Là thành viên, tôi muốn bấm /go/ (chạy trên Cloudflare Worker) để được chuyển sang Shopee và hệ thống ghi click
- Loại: feature · 8 điểm · Must · Sprint 1 · Owner: claude · Phụ thuộc: T-004, T-014
- Acceptance criteria:
  - Given code hợp lệ When GET /go/code Then 302 tới link có utm_content=1u-… đúng user/click
  - Given DB lỗi When GET /go Then vẫn 302 bằng sub_id mức link (1l-…)
  - Given code không tồn tại When GET Then 404
  - Given 100 click/s When thử tải Then p95 < 200ms

## E4 — Đồng bộ Shopee và đơn hàng  (36 điểm)

### T-063: Là admin, tôi muốn dán cookie Shopee được mã hóa at-rest và không đọc lại được
- Loại: feature · 5 điểm · Must · Sprint 2 · Owner: claude · Phụ thuộc: T-012
- Acceptance criteria:
  - Given cookie When lưu Then DB chỉ có bản mã hóa AES-GCM
  - Given log/API When tìm cookie Then không thấy giá trị
  - Given staff When đổi cookie Then 403

### T-020: Là sync-worker, tôi muốn client Shopee báo lỗi có kiểu, phân trang đủ, tiền số nguyên
- Loại: feature · 8 điểm · Must · Sprint 2 · Owner: claude · Phụ thuộc: T-007
- Acceptance criteria:
  - Given 401/403 When gọi Then ném CookieExpired/Blocked (có kiểu)
  - Given 250 trang When phân trang Then lấy đủ hoặc đánh dấu partial, không cắt im lặng
  - Given capped_commission=0 When tính Then dùng 0, không rơi về gross
  - Given giá trị tiền When đọc Then trả bigint micro, không float

### T-021: Là hệ thống, tôi muốn đồng bộ đơn định kỳ, quét lại 60 ngày, chạy bù khi bật lại
- Loại: feature · 8 điểm · Must · Sprint 2 · Owner: claude · Phụ thuộc: T-020, T-005
- Acceptance criteria:
  - Given đơn mới When sync Then upsert idempotent theo order_sn
  - Given đơn đổi PENDING→COMPLETED When sync lại Then cập nhật status
  - Given máy tắt 3 ngày When bật lại Then sync bù đủ
  - Given sync partial When kết thúc Then đánh dấu và không dùng để chuyển tiền

### T-022: Là hệ thống, tôi muốn khớp sub_id với click/user/post và đưa đơn lạ vào hàng mồ côi
- Loại: feature · 5 điểm · Must · Sprint 2 · Owner: claude · Phụ thuộc: T-004, T-021
- Acceptance criteria:
  - Given utm_content hợp lệ loại u When khớp Then gắn user_id và click_id
  - Given loại p When khớp Then gắn post_id
  - Given chữ ký sai hoặc id không tồn tại When khớp Then vào orphan_orders (thuộc admin)

### T-023: Là admin, tôi muốn cảnh báo khi cookie chết hoặc sync lỗi
- Loại: feature · 5 điểm · Must · Sprint 2 · Owner: codex · Phụ thuộc: T-063, T-020
- Acceptance criteria:
  - Given 403 When health-check Then trạng thái expired và gửi Telegram/Email
  - Given expired When quá 6 giờ Then nhắc lại
  - Given cookie mới When health ok Then về healthy

### T-024: Là staff, tôi muốn import CSV báo cáo thủ công khi cookie chết
- Loại: feature · 5 điểm · Should · Sprint 6 · Owner: codex · Phụ thuộc: T-021
- Acceptance criteria:
  - Given CSV báo cáo Shopee When import Then đi qua cùng pipeline khớp sub_id
  - Given dòng trùng When import lại Then không nhân đôi

## E5 — Ví và hoàn tiền  (19 điểm)

### T-030: Là hệ thống, tôi muốn sổ cái ví chỉ thêm, số nguyên, idempotent
- Loại: feature · 8 điểm · Must · Sprint 3 · Owner: claude · Phụ thuộc: T-005
- Acceptance criteria:
  - Given cùng idem_key When ghi 2 lần Then chỉ 1 dòng
  - Given nhiều giao dịch song song When cập nhật ví Then không lệch số dư
  - Given tổng entry When so với wallets Then bằng nhau
  - Given user mới đăng ký chưa có dòng ví When wallet đọc số dư Then trả 0/0/0 và tạo dòng wallets khi ghi lần đầu (auth không được ghi bảng ví)

### T-031: Là thành viên, tôi muốn tiền hoàn vào chờ xác nhận rồi mới thành rút được sau hạn trả hàng
- Loại: feature · 8 điểm · Must · Sprint 3 · Owner: claude · Phụ thuộc: T-030, T-022
- Acceptance criteria:
  - Given đơn khớp user hoa hồng 40.375đ When share 60% Then pending = floor → 24.225đ
  - Given đơn COMPLETED + 7 ngày và sync healthy When job chạy Then pending→available
  - Given đơn CANCELLED/RETURNED When sync Then pending→cancelled, số dư không âm
  - Given sync không healthy When job chạy Then không chuyển tiền

### T-032: Là admin, tôi muốn cấu hình tỷ lệ 60/40, hold_days, snapshot theo đơn
- Loại: feature · 3 điểm · Must · Sprint 3 · Owner: claude · Phụ thuộc: T-030
- Acceptance criteria:
  - Given share đổi 60→50 When có đơn mới Then đơn mới dùng 50%
  - Given đơn cũ When xem Then vẫn 60% (snapshot)

## E6 — Rút tiền  (21 điểm)

### T-040: Là thành viên, tôi muốn gửi yêu cầu rút tiền khi đủ ngưỡng
- Loại: feature · 5 điểm · Must · Sprint 4 · Owner: claude · Phụ thuộc: T-031
- Acceptance criteria:
  - Given available < ngưỡng When rút Then 400
  - Given đang có yêu cầu mở When rút thêm Then 409
  - Given hợp lệ When rút Then available→held trong 1 transaction

### T-041: Là admin, tôi muốn duyệt và chi trả thủ công bằng VietQR/CSV
- **Tiến độ (2026-11-28):** backend duyệt/từ chối/chi trả có từ T-040; `prep/T-041` thêm CSV (chống công thức độc, audit từng dòng), `rules`/`usable_now`/`transfer_note`, BFF allowlist; giao diện: T-041a (người dùng) rồi T-041b (admin + TOTP) cho Codex. **VietQR chưa làm** (cần bảng mã BIN ngân hàng; CSV đủ cho MVP).
- Loại: feature · 8 điểm · Must · Sprint 4 · Owner: claude · Phụ thuộc: T-040, T-012
- Acceptance criteria:
  - Given yêu cầu When duyệt Then sinh mã VietQR/CSV chuyển hàng loạt
  - Given đã chuyển When mark-paid kèm tham chiếu Then held→paid_out và email user
  - Given từ chối When reject Then held→available kèm lý do

### T-042: Là PO, tôi muốn spike và adapter cổng chi trả tự động (sau MVP, MVP dùng chuyển khoản thủ công)
- Loại: spike · 8 điểm · Could · Sprint 7 · Owner: claude · Phụ thuộc: T-041
- Acceptance criteria:
  - Given danh sách cổng When so sánh Then có bảng điều kiện (cá nhân được dùng không, phí, thẻ)
  - Given cổng được chọn When adapter Then cùng interface PayoutProvider, có sandbox test
  - Given thất bại When payout Then hoàn held→available, không mất tiền

## E7 — Tool API cho Muse AI  (13 điểm)

### T-050: Là Muse AI, tôi muốn tool API có key để tìm SP và lấy link theo từng bài
- Loại: feature · 8 điểm · Must · Sprint 5 · Owner: claude · Phụ thuộc: T-004, T-012
- Acceptance criteria:
  - Given key hợp lệ When POST /agent/links post_key mới Then trả aff_link có 1p-…
  - Given post_key trùng When gọi lại Then trả link cũ, không ghi đè
  - Given key sai/thu hồi When gọi Then 401
  - Given min_rate When search Then lọc đúng theo feed

### T-051: Là Muse AI, tôi muốn insights doanh thu theo bài/ngành/giờ để học
- Loại: feature · 5 điểm · Should · Sprint 5 · Owner: codex · Phụ thuộc: T-050, T-022
- Acceptance criteria:
  - Given đơn của bài When group=post Then hiện click/đơn/hoa hồng của từng bài
  - Given group=category|hour|page When gọi Then trả đúng nhóm
  - Given dữ liệu user When gọi Then tuyệt đối không có thông tin user

## E8 — Admin và đối soát  (19 điểm)

### T-043: Là admin, tôi muốn dashboard tổng quan, quản lý user và đơn
- Loại: feature · 8 điểm · Must · Sprint 4 · Owner: codex · Phụ thuộc: T-012, T-021
- Acceptance criteria:
  - Given admin When mở Then thấy click/đơn/hoa hồng/ví/cookie status
  - Given khóa user When thực hiện Then user không đăng nhập được và có audit
  - Given staff When mở Then không thấy trang cookie
  - Given user đã rút trước khi đơn bị thu hồi (bút toán `adjust`) When admin mở dashboard Then thấy tổng và danh sách khoản lỗ (đơn, user, số tiền, thời điểm); không hiện cho staff không có quyền tài chính

### T-044: Là staff, tôi muốn gán tay đơn mồ côi cho user khi có khiếu nại
- Loại: feature · 3 điểm · Must · Sprint 4 · Owner: codex · Phụ thuộc: T-022, T-031
- Acceptance criteria:
  - Given đơn mồ côi When gán user Then sinh entry pending cho user theo share snapshot
  - Given gán When xong Then audit ghi người làm và lý do

### T-052: Là admin, tôi muốn đối soát: hoa hồng Shopee − chia user − lợi nhuận
- Loại: feature · 5 điểm · Should · Sprint 5 · Owner: claude · Phụ thuộc: T-031
- Acceptance criteria:
  - Given tháng M When xem Then X(Shopee) = Y(chia user) + Z(mồ côi + bài) + lợi nhuận
  - Given lệch ≠ 0 When xem Then cảnh báo kèm danh sách đơn lệch

### T-054: Là admin, tôi muốn tỷ lệ hoàn theo ngành/hạng
- Loại: feature · 3 điểm · Could · Sprint 5 · Owner: codex · Phụ thuộc: T-032
- Acceptance criteria:
  - Given ngành A 70% When đơn ngành A Then dùng 70%
  - Given ngành khác When đơn Then dùng tỷ lệ toàn cục

## E9 — Chống gian lận và khiếu nại  (13 điểm)

### T-053: Là staff, tôi muốn phát hiện tự mua, cùng IP/thiết bị, hủy bất thường
- Loại: feature · 8 điểm · Should · Sprint 5 · Owner: codex · Phụ thuộc: T-021
- Acceptance criteria:
  - Given nhiều tài khoản cùng ip_hash/UA trong 24h When quét Then tạo fraud_flag
  - Given user hủy > ngưỡng When quét Then tạo cờ
  - Given cờ When staff xử lý Then giữ pending/khóa/bỏ qua có audit

### T-062: Là thành viên, tôi muốn khiếu nại mua rồi chưa thấy đơn, tra theo click
- Loại: feature · 5 điểm · Should · Sprint 6 · Owner: codex · Phụ thuộc: T-044
- Acceptance criteria:
  - Given user gửi khiếu nại When có click khớp và đơn đã về Then báo trạng thái dự kiến
  - Given khớp đơn mồ côi When staff duyệt Then gán đơn cho user

## E10 — Web cho thành viên  (13 điểm)

### T-033: Là thành viên, tôi muốn giao diện đăng ký/đăng nhập, dán link, xem lịch sử
- Loại: feature · 8 điểm · Must · Sprint 3 · Owner: codex · Phụ thuộc: T-014, T-015
- Acceptance criteria:
  - Given mobile 375px When mở Then không cuộn ngang
  - Given dán link hợp lệ When bấm Then hiện go_url, nút sao chép
  - Given lỗi API When hiển thị Then thông báo tiếng Việt dễ hiểu

### T-034: Là thành viên, tôi muốn xem ví (chờ/rút được) và đơn của tôi
- Loại: feature · 5 điểm · Must · Sprint 3 · Owner: codex · Phụ thuộc: T-031
- Acceptance criteria:
  - Given ví When mở Then thấy pending/available/held và share %
  - Given đơn When mở Then thấy trạng thái và thời điểm dự kiến vào ví

## Tổng
- Must: 178 điểm · Should: 28 · Could: 11 · Tổng: 217

## Ngoài MVP (chưa ước lượng)
App mobile, extension trình duyệt, 2FA admin, referral, KYC, Redis/hàng đợi thật, kênh Zalo/Telegram/TikTok cho user.
