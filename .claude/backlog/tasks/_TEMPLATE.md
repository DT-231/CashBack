# T000 — <Tên task ngắn>

## Mục tiêu
<1–3 câu: làm xong thì người dùng/hệ thống có thêm được gì>

## Phạm vi file (chỉ được sửa ở đây)
- backend/app/modules/<module>/...
- backend/tests/...

## KHÔNG được đụng
- backend/app/core/, modules/wallet/, core/subid.py, migrations/ (trừ khi ghi rõ ở trên)

## Bối cảnh cần biết
- <API liên quan, schema, file mẫu nên bắt chước, ví dụ modules/_template/>

## Acceptance criteria
- [ ] Given ... When ... Then ...
- [ ] Given ... When ... Then ...

## Lệnh test phải pass
```
make test-unit MODULE=<module>
make lint
```

## Ghi chú
<tùy chọn>
