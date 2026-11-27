## Làm gì / vì sao
<!-- 1–3 câu. Một PR = một module hoặc một việc. -->

## Loại thay đổi
- [ ] `refactor` (KHÔNG đổi hành vi, có test khóa trước) · [ ] `fix` · [ ] `feat` · [ ] `docs`/`chore`

## Checklist review
**Tiền / ví**
- [ ] Không float cho tiền; làm tròn xuống phần của user (`core/money.py`)
- [ ] Chỉ `modules/wallet` ghi `wallets` / `wallet_entries`; sổ cái chỉ thêm, có `idem_key`
- [ ] Không chuyển pending→available khi sync không healthy

**Bảo mật**
- [ ] Không đọc/in/commit `.env`, cookie, token; log không chứa dữ liệu nhạy cảm
- [ ] Endpoint mới có xác thực/phân quyền; đầu vào được validate
- [ ] Không gọi Shopee/Facebook ngoài `integrations/`; test dùng `MOCK=1`/fixture

**Migration**
- [ ] Có `downgrade`; đã chạy up → down → up (`make test-db`)
- [ ] Index cho khóa ngoại/cột lọc mới

**Test & kiến trúc**
- [ ] `make test` và `make lint` xanh (gồm `test_architecture.py`)
- [ ] Có test cho hành vi mới / test tái hiện lỗi đã sửa
- [ ] `sub_id` chỉ dùng `app.core.subid`; link chỉ dùng `modules/links/affiliate_link.py`
- [ ] Task giao Codex chỉ đụng 1 module, không sửa `core/`, `wallet`, `subid` nếu chưa được giao rõ
