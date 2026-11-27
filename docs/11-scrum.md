# 11 — Quy trình Scrum

## Vai trò (đội nhỏ)
| Vai trò | Ai |
|---|---|
| Product Owner | Bạn (quyết định nghiệp vụ, duyệt DoD) |
| Scrum Master / Tech Lead / Reviewer | Claude Code |
| Developer | Codex (CRUD, UI, test, script) + Claude Code (kiến trúc, ERD, `sub_id`, ví/tiền, bảo mật) |

Giả định: 1 người thật, ~10–15 giờ/tuần. Nếu có thêm người, cập nhật velocity.

## Nhịp sprint
- Sprint **2 tuần**, bắt đầu thứ Hai.
- **Sprint Planning** (thứ Hai, 45 phút): chốt Sprint Goal, kéo story vào.
- **Daily** (bất đồng bộ, 5 phút): ghi vào `STANDUP.md` hoặc issue: hôm qua/hôm nay/vướng.
- **Review** (thứ Sáu tuần 2, 30 phút): demo luồng chạy được.
- **Retro** (sau Review, 20 phút): giữ/bỏ/thử; ghi vào `docs/retro/`.
- **Refinement** (giữa sprint, 30 phút): làm rõ story cho sprint sau.

## Ước lượng
Story point Fibonacci (1, 2, 3, 5, 8, 13). 1 điểm ≈ nửa giờ đến một giờ việc đã rõ cho Codex. Story > 8 phải tách. Velocity khởi đầu giả định **30 điểm/sprint** (hai agent làm song song; nếu thực tế chỉ 15 thì timeline gấp đôi), hiệu chỉnh sau 2 sprint.

## Definition of Ready (story vào sprint được khi)
- Có lời kể *Là… tôi muốn… để…* và acceptance criteria Given/When/Then.
- Biết phụ thuộc và file/phần **không được đụng**.
- Nếu liên quan tiền hoặc `sub_id`: có ví dụ số liệu cụ thể.
- Quyết định PO cần cho story đã có.
- Ước lượng ≤ 8 điểm.

## Definition of Done
- Mọi acceptance criteria đạt, có test tự động tương ứng.
- Lint, format, type check, test đều qua trên CI.
- Test hồi quy `affiliate.make_link` (từ `test_offline.py`) vẫn pass.
- Với code động tới tiền/`sub_id`/auth: Claude review thủ công + có test thuộc tính hoặc biên.
- Không có secret/cookie/PII trong code, log, test fixture.
- Migration có chiều lên và xuống, chạy được trên DB trống.
- Cập nhật tài liệu liên quan (`docs/`, README, `.env.example`).
- Chạy được bằng `docker compose up` với `MOCK=1`.
- Task của Codex: ghi kết quả review (đạt / cần sửa + lý do) vào cuối `backlog/tasks/<id>.md`.

## Quy ước git
- Nhánh: `main` (luôn chạy được), `task/<id>` cho từng task; hai agent không sửa cùng file cùng lúc.
- Commit: `<type>(<scope>): <mô tả>`; type: `feat|fix|docs|test|refactor|chore`; tham chiếu `T-xxx`.
- PR nhỏ (< 400 dòng đổi nếu được), mô tả có checklist acceptance criteria; Claude review rồi squash-merge.
- Cấm commit `.env`, cookie, token, dữ liệu user thật.

## Phối hợp Claude Code ↔ Codex
- `AGENTS.md` (Codex) và `CLAUDE.md` trỏ về cùng nội dung.
- `backlog/tasks/<id>.md` phải tự đủ: mục tiêu, file liên quan, acceptance criteria, lệnh test, **những gì không được đụng**.
- Claude giữ: kiến trúc, ERD, codec `sub_id`, ví/sổ cái, bảo mật, migration. Codex làm: CRUD, UI, test, script.
