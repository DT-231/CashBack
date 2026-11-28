# PROMPT AUTOPILOT — Claude Code tự làm liên tục, không dừng hỏi

> Cách dùng: mở Claude Code ở thư mục gốc dự án, bật `/ponytail` (mức `full`), dán toàn bộ nội dung dưới đây.
> Dừng: tạo file `docs/autopilot/STOP` (lệnh: `touch docs/autopilot/STOP`) hoặc nhấn Ctrl+C.
> Tiếp tục sau khi hết hạn mức: dán đúng một câu: `Đọc docs/autopilot/STATE.md và tiếp tục autopilot.`

---

## 0. Chế độ làm việc

Bạn chạy ở chế độ **tự hành (autopilot)**. Làm liên tục, hết task này sang task khác, cho đến khi:
- hết token/hạn mức, hoặc
- tồn tại file `docs/autopilot/STOP`, hoặc tôi ngắt phiên.

Tôi (PO) **không ở bên cạnh để trả lời**. Vì vậy:

1. **Không kết thúc lượt chỉ để hỏi tôi. Không dùng AskUserQuestion.** Không viết "bạn muốn tôi làm gì tiếp?".
2. **Gặp điểm mơ hồ → tự quyết, ghi lại, làm tiếp.** Chọn phương án an toàn nhất: ít thay đổi nhất, ít quyền nhất, fail-closed, đảo ngược được. Ghi vào `docs/autopilot/DECISIONS.md`: ngày, bối cảnh, lựa chọn, phương án thay thế, cách đảo ngược.
3. **Việc chỉ PO làm hoặc quyết được** (dữ liệu Shopee thật, `hold_days`, đơn mua thử, domain, xác nhận với Shopee, nội dung pháp lý, mua dịch vụ, bật rút tiền thật…) → ghi vào `docs/autopilot/PO-INBOX.md` (việc gì, vì sao cần, ảnh hưởng nếu chưa có), rồi **chuyển sang việc khác**. Không chờ.
4. **Bị kẹt** (cùng một lỗi 3 lần, hoặc thử 3 cách khác nhau vẫn chưa tìm ra nguyên nhân) → ghi `docs/autopilot/PARKED.md` (hiện tượng, đã thử gì, giả thuyết), hoàn tác phần dở, sang việc khác. Không chạy lại cùng một lệnh lỗi quá 3 lần mà không đổi gì.
5. Không báo cáo dài giữa chừng. Chỉ cập nhật `LOG.md` và `STATE.md` (mục 4).

---

## 1. Vùng cấm — không có ngoại lệ, dù không ai hỏi

- **Không bật `WITHDRAWALS_ENABLED=1` ở bất kỳ nơi nào.** Không tạo hoặc đổi `.env` thật. Không đọc, in, commit secret, cookie, token, HAR.
- **Không gọi live** tới Shopee, Facebook, Cloudflare, Neon production. Không chạy `revenue.py` hay script nào gọi mạng thật. Mặc định `MOCK=1`. Không tạo click hay đơn giả.
- **Git:** không push lên `main`, không force-push, không `reset --hard` trên nhánh đã push, không xóa nhánh chưa merge.
- **Không đổi** (cần đổi thì ghi `PO-INBOX.md`): quy ước `sub_id` v1, ngữ nghĩa sổ cái (chỉ thêm), tỷ lệ 60%, `hold_days`, các trạng thái đơn, quy tắc làm tròn.
- **Migration:** luôn có `downgrade`, chỉ chạy trên DB dev hoặc DB tạm, không `DROP` dữ liệu thật.
- Không xóa hay sửa `audit_logs`, `wallet_entries`. Không nới quyền role `cashback_app`.
- **Không làm cho test "xanh" bằng cách gian lận:** không `skip`, không giảm assertion, không tắt trigger, contract test hay kiểm tra khởi động.
- **Không sửa:** `.claude/`, `docs/autopilot/STOP`, file prompt autopilot này, phần "Quy tắc an toàn" trong `AGENTS.md`.
- Không làm tính năng ngoài backlog. Muốn thêm gì thì ghi đề xuất vào backlog, không tự làm.
- Thêm dependency chỉ khi thư viện chuẩn hoặc thứ đã có không đủ. Khi thêm, ghi `DECISIONS.md` (lý do, license, kích thước).

---

## 2. Nhánh và merge

- Tạo nhánh tích hợp **`autopilot/main`** từ `main`. Mọi việc xong thì merge vào đây. **Không bao giờ sửa `main`.**
- Được push `autopilot/main` và các nhánh task lên origin.
- Điều kiện để merge vào `autopilot/main` (đủ hết mới merge):
  - `make test` chạy 2 lần liên tiếp đều xanh, không skip, DB sạch sau test;
  - `ruff`, `tsc`, `next build` sạch (khi chạm frontend);
  - mọi logic mới đã qua thử đột biến và đột biến đều bị bắt;
  - diff nằm đúng phạm vi task.
- Task do Codex: squash thành 1 commit. Nhánh chuẩn bị (prep): merge `--no-ff`.
- Cuối cùng tôi tự duyệt và merge `autopilot/main` vào `main`.

---

## 3. Bước 0 — làm một lần ở đầu

1. Đọc `AGENTS.md`, `docs/12-backlog.md`, `backlog/issues.csv`, bảng "Điều kiện mở đăng ký", và (nếu đã có) `docs/autopilot/*`.
2. Tạo `docs/autopilot/{STATE,LOG,DECISIONS,PO-INBOX,PARKED}.md` nếu chưa có.
3. Tạo `autopilot/main`. Merge các nhánh đang chờ theo thứ tự này, chạy test sau mỗi lần, tự xử lý xung đột (giữ cả hai phía với `.env.example` và `12-backlog.md`):
   `task/T-019` → `prep/T-041` → `task/T-041a` (squash) → `task/T-041b` (squash) → `task/startup-db-guard` → `chore/codex-forbidden-paths` → `docs/launch-gates-table`.
4. Ghi vào `PO-INBOX.md`, nếu chưa có: ngày Shopee trả hoa hồng gần nhất và các đơn đi kèm (chốt `hold_days`); kết quả đơn mua thử theo runbook; domain; xác nhận Shopee về cashback; trang điều khoản/quyền riêng tư; tạo `cashback_app` và đổi `DATABASE_URL` khi muốn thử rút tiền.

---

## 4. Vòng lặp cho mỗi task

1. Nếu tồn tại `docs/autopilot/STOP` → viết `REPORT.md` (mục 5) rồi dừng.
2. **Chọn task:** `Must` trước `Should` trước `Could`. Bỏ qua task đang chờ PO. Ưu tiên việc mở khóa việc khác và việc rủi ro cao (bảo mật, tiền). Backlog hết hoặc toàn bị chặn → chọn trong danh sách gợi ý ở mục 6.
3. **Phân việc:**
   - Claude giữ: `core/`, `wallet`, `payouts`, `subid`, `crypto`, auth/MFA, `audit`, migration, mọi thứ về bảo mật.
   - Codex làm: UI, CRUD, test, script, qua `/codex` hoặc `scripts/codex-task.sh`. Tối đa **2 task Codex song song**, khác module và khác thư mục.
   - Task file phải đủ: mục tiêu, phạm vi file, KHÔNG được đụng, acceptance criteria, lệnh test, mục "Test bị bỏ qua".
   - Codex tối đa **2 vòng phản hồi**. Sau đó Claude tự sửa phần còn lại hoặc `PARKED`.
4. **Làm:** có test khóa hành vi trước khi sửa code cũ. Ponytail `full`: thay đổi nhỏ nhất mà đủ.
5. **Kiểm** (bắt buộc, dán số liệu thật vào LOG, không dùng công cụ lọc output):
   - `make test` ×2, `make lint`; `tsc` và `next build` nếu chạm frontend;
   - thử đột biến cho logic mới, khôi phục bằng `git checkout -- <file>`, đã commit trước khi thử;
   - DB sạch sau test;
   - `/ponytail-review` trên diff; thêm `/security-review` nếu chạm auth, ví, payout, crypto, BFF, DB role.
6. **Merge** vào `autopilot/main`. Thêm một dòng vào `LOG.md`: task, commit, `N passed`, số đột biến đã thử và đã bắt.
7. **Cập nhật `STATE.md`:** đang làm gì, tiếp theo là gì, nhánh nào chờ, lệnh để phiên mới tiếp tục. File này phải luôn đủ để phiên mới đọc là làm tiếp được.
8. **Mỗi 5 task:** chạy toàn bộ test, đo thời gian test và endpoint chính, dọn worktree và nhánh đã merge, rà lại `PARKED.md` xem có việc nào giờ làm được.

---

## 5. Khi dừng (STOP, hết token, hết task)

Viết `docs/autopilot/REPORT.md`, ngắn gọn:
- việc đã làm (commit, số test, đột biến);
- các quyết định đã tự đưa ra (trỏ `DECISIONS.md`) — đánh dấu cái nào PO nên xem lại trước;
- việc PO cần làm (trỏ `PO-INBOX.md`);
- việc bị park và lý do;
- lệnh để tôi xem và merge: `git diff main...autopilot/main --stat`, rồi cách merge.

---

## 6. Danh sách gợi ý khi backlog không có việc rõ

(chỉ làm khi không bị chặn bởi PO; đưa vào backlog nếu chưa có)
- T-018: `SUBID_SECRET` hỗ trợ khóa cũ khi đổi khóa (cẩn thận rủi ro khớp nhầm vì chữ ký 3 ký tự).
- `main_worker.py` và `app/jobs`: đồng bộ click/đơn, chốt ví, health-check cookie, chạy bù khi máy bật lại (dùng fixture, không gọi live).
- Ghi `auth.login` vào `audit_logs`.
- Tool API cho Muse AI: kiểm tra đủ, có test hợp đồng.
- Bỏ dần `legacy_api.py` (có test khóa hành vi trước).
- Rà soát hiệu năng: index DB, N+1, thời gian job sync với fixture.
- Rà soát bảo mật toàn repo bằng `/security-review`, sửa lỗi tìm thấy (mỗi lỗi một commit `fix(...)`).
- Runbook còn thiếu (cookie chết, Shopee 403, máy nhà tắt, đối soát lệch), tài liệu `docs/` cập nhật theo code.
- Tăng độ phủ test cho module nào thấp nhất (`make cov`).

---

Bắt đầu từ **Bước 0**, rồi vào vòng lặp. Không hỏi lại.
