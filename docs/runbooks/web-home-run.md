# Runbook: chạy web (Next.js + BFF) và API ở máy nhà

Mục tiêu: chỉ `cloudflared` cùng máy mới tới được web và API. Không ai trong mạng LAN/Internet gọi thẳng được cổng của chúng (nếu gọi thẳng được, họ giả được `X-Visitor-IP`/`CF-Connecting-IP` để né rate limit).

## Lệnh (đều bind 127.0.0.1)
```bash
# API (FastAPI): HOST mặc định là 127.0.0.1; KHÔNG đặt HOST=0.0.0.0
cd backend && ../.venv/bin/python -m app.main_api

# Web (Next.js, production): script đã có -H 127.0.0.1
cd frontend && npm run build && npm run start      # = next start -H 127.0.0.1 (cổng mặc định 3000)
# tương đương chạy tay: npx next start -H 127.0.0.1 -p 3000
```
- `frontend/package.json` đã đặt `-H 127.0.0.1` cho `dev` và `start`, có test (`tests/ui-rules.test.ts`) giữ điều đó. **Không** chạy `next start -H 0.0.0.0` và không bỏ `-H`: mặc định của Next.js lắng nghe mọi giao diện mạng.
- Test cổng compose (`test_compose_ports.py`) chỉ bắt được cổng **Docker**. Tiến trình chạy trực tiếp như trên chỉ được bảo vệ bởi lệnh ở đây và test của script.
- Nếu đóng gói Docker sau này: map cổng `"127.0.0.1:PORT:PORT"`; trong container tiến trình phải bind `0.0.0.0` (khi đó giữ `TRUST_PROXY_HEADERS=0`, tin cậy dựa vào `BFF_SHARED_SECRET`).

## Cloudflare Tunnel
`cloudflared` trỏ về **web** (`http://127.0.0.1:3000`), không trỏ thẳng về API. API chỉ nhận lời gọi từ BFF qua `127.0.0.1:8080` (`API_BASE_URL=http://127.0.0.1:8080`). Hostname cố định cần domain riêng (`docs/06-kien-truc.md` mục 0).

## Biến môi trường bắt buộc khi mở cho người ngoài
| Biến | Ở đâu | Ghi chú |
|---|---|---|
| `BFF_SHARED_SECRET` | backend **và** frontend, cùng giá trị | >= 16 ký tự; thiếu/ngắn thì mọi khách dùng chung một bộ đếm rate limit |
| `BFF_ENABLED=1` | backend | Khai báo web đi qua BFF để backend cảnh báo khi thiếu secret |
| `API_BASE_URL` | frontend | `http://127.0.0.1:8080`, không `NEXT_PUBLIC_` |
| `TRUST_PROXY_HEADERS` | backend | `0` khi chỉ BFF gọi tới (BFF dùng secret); `1` chỉ nếu `cloudflared` trỏ thẳng vào API, và khi đó phải bind 127.0.0.1 (khởi động từ chối nếu không) |

## Kiểm tra sau khi chạy
- `curl -s http://127.0.0.1:8080/health` → `visitor_ip` phải là `ok` và `degraded` là `false`.
- `curl -s http://127.0.0.1:3000/bff/health` → `visitor_ip: "ok"`, `degraded: false`.
- Log khởi động **không** có dòng `CẢNH BÁO: BFF_SHARED_SECRET ...` (backend: `app.access`; frontend: `[bff] CẢNH BÁO`).
- Từ máy khác trong LAN: `curl http://<ip-may-nha>:3000` và `:8080` phải **không kết nối được**.
