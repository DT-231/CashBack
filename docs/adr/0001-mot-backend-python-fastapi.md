# ADR 0001 — Một backend Python (FastAPI) dùng chung cho API và worker

- **Trạng thái:** chấp nhận (2026-11-27). Khớp `docs/06` §3.
- **Bối cảnh:** code hiện có là Python (`affiliate`, `revenue`, feed). Cần API, sau này thêm worker đồng bộ cùng dùng một mã.
- **Quyết định:** một codebase `backend/` với nhiều entrypoint (`app/main_api.py`; `main_worker.py` khi làm T-021). Module nghiệp vụ trong `app/modules/`, mã dùng chung trong `app/core/`, bên ngoài trong `app/integrations/`.
- **Hệ quả:** không có `services/link-api` riêng. API thuần `/api/v1` + OpenAPI nên web và app mobile dùng chung.
- **Phương án bỏ:** nhiều service riêng (tốn vận hành cho một người), Node/NestJS (viết lại logic đã verify).
