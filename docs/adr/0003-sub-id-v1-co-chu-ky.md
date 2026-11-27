# ADR 0003 — sub_id v1 có chữ ký là danh tính nguồn duy nhất

- **Trạng thái:** chấp nhận. Chi tiết `docs/07` §1.
- **Quyết định:** mọi link mới sinh qua `app.core.subid.encode`; link AI: `1p-<post_id>-<page_code>-<chữ ký>-`. Không tự ghép chuỗi, không đưa keyword/dữ liệu cá nhân vào sub_id.
- **Ngoại lệ có chủ đích:** đường dẫn cũ `/api/search`, `/api/link` vẫn nhận nhãn `sub` do caller đặt (dạng `legacy`, đơn về thành "mồ côi"). Sẽ bỏ khi Muse AI chuyển sang `/api/v1/agent/links`.
