# ADR 0002 — Chỉ dùng Postgres, bỏ SQLite

- **Trạng thái:** chấp nhận (PO, 2026-11-27).
- **Bối cảnh:** service cũ lưu `links/clicks` ở SQLite, lược đồ khác hẳn Postgres (`docs/07`). Hai nguồn sự thật sẽ lệch.
- **Quyết định:** bỏ SQLite. Luồng AI dùng bảng `posts` + `agent_keys`; `links/clicks` chỉ cho luồng thành viên. Dữ liệu click cũ (`data/links.db`) **không migrate**, giữ file làm bản lưu.
- **Hệ quả:** `/go/<sub_id>`, `/api/stats`, `/api/revenue` cũ bị bỏ khỏi backend. `/go/{code}` chạy ở Cloudflare Worker (T-015); doanh thu thật xem bằng `backend/scripts/revenue_report.py`.
