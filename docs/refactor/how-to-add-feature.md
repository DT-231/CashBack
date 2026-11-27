# Thêm chức năng mới (module mới)

Mẫu: `backend/app/modules/_template/`. Một task = một module.

1. **Nhánh:** `task/<id>` từ `main`. Đọc task trong `backlog/tasks/<id>.md` và `AGENTS.md`.
2. **Copy** `_template/` → `modules/<ten>/`, đổi tên `Thing`/`things`.
3. **Migration** (nếu cần bảng): `backend/migrations/versions/NNNN_<ten>.py`, **có `downgrade`**; index cho khóa ngoại và cột lọc. Chạy `make db-up && make test-db` (up → down → up).
4. **Viết test trước:** unit cho `service` (repository giả), integration cho `repository` + `api` (Postgres), contract nếu đụng định dạng (link, sub_id, tiền).
5. **Code theo lớp:** `api.py` (HTTP) → `service.py` (nghiệp vụ, mở transaction) → `repository.py` (SQL). Lỗi kế thừa `AppError` trong `errors.py`. Không import `repository` của module khác; gọi `service` công khai của nó.
6. **Gắn router** trong `app/main_api.py` (`app.include_router(...)`). Đường dẫn dưới `/api/v1/...`.
7. **Cấu hình:** biến mới thêm vào `core/config.py` **và** `.env.example` (có chú thích). Không dùng `os.environ` ở nơi khác.
8. **Tiền:** số nguyên qua `core/money.py`. Chỉ module `wallet` đổi số dư. `sub_id` chỉ qua `core/subid.py`.
9. **Gọi Shopee:** chỉ qua `integrations/shopee`. Test dùng `FakeShopeeClient`/fixture, `MOCK=1`.
10. `make test && make lint` xanh (gồm `test_architecture.py`), mở PR theo template.
