// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const replace = vi.fn();
const router = { replace };
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/lib/api-client", () => ({
  ApiError: class ApiError extends Error { constructor(public status: number, public code: string, message: string) { super(message); } get isAuth() { return this.status === 401 && ["session_expired", "unauthorized"].includes(this.code); } },
  api: { withdrawalRules: vi.fn(), bankAccounts: vi.fn(), wallet: vi.fn(), myWithdrawals: vi.fn(), addBankAccount: vi.fn(), requestWithdrawal: vi.fn() },
}));
import { ApiError, api } from "@/lib/api-client";
import type { WithdrawalOut } from "@/lib/types";
import WithdrawPage from "./WithdrawPage";

const rules = { withdrawals_enabled: true, min_withdraw_vnd: 50000, bank_change_cooldown_hours: 48, max_bank_accounts: 3 };
const wallet = { pending_vnd: 0, available_vnd: 123456, held_vnd: 0, share_pct: 60 };
const account = (id: number, usable_now = true) => ({ id, bank_code: "VCB", account_name: "NGUYEN VAN A", last4: "1234", usable_from: "2100-01-02T03:04:00Z", usable_now, created_at: "2026-01-01T00:00:00Z" });
const withdrawal = (id: number, status = "requested", extra: Record<string, unknown> = {}): WithdrawalOut => ({ id, amount_vnd: 50000, status: status as WithdrawalOut["status"], bank_account_id: 1, bank_code: "VCB", last4: "1234", provider_ref: null, decided_reason: null, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", ...extra });
const defaultMocks = () => {
  vi.mocked(api.withdrawalRules).mockResolvedValue(rules);
  vi.mocked(api.bankAccounts).mockResolvedValue([account(1), account(2, false)]);
  vi.mocked(api.wallet).mockResolvedValue(wallet);
  vi.mocked(api.myWithdrawals).mockResolvedValue([withdrawal(1)]);
  vi.mocked(api.addBankAccount).mockResolvedValue(account(3));
  vi.mocked(api.requestWithdrawal).mockResolvedValue(withdrawal(2));
};
const ready = async () => { render(<WithdrawPage />); await screen.findByText("Tối thiểu mỗi lần: 50.000 ₫"); };
const submitWithdrawal = () => {
  fireEvent.change(screen.getByLabelText("Tài khoản nhận"), { target: { value: "1" } });
  fireEvent.change(screen.getByLabelText("Số tiền"), { target: { value: "70000" } });
  fireEvent.click(screen.getByRole("button", { name: "Rút tiền" }));
};

beforeEach(() => {
  vi.clearAllMocks(); defaultMocks();
  let keySequence = 0;
  vi.stubGlobal("crypto", { randomUUID: vi.fn(() => `test-key-${String(++keySequence).padStart(8, "0")}`) });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("WithdrawPage", () => {
  it("tải các nguồn song song và hiển thị quy tắc/số dư do API trả về", async () => {
    await ready();
    expect(api.withdrawalRules).toHaveBeenCalled(); expect(api.bankAccounts).toHaveBeenCalled();
    expect(api.wallet).toHaveBeenCalled(); expect(api.myWithdrawals).toHaveBeenCalledWith({ limit: 50, offset: 0 });
    expect(screen.getByText("Rút được: 123.456 ₫")).toBeTruthy();
    expect(screen.getByText("Tài khoản mới dùng được sau 48 giờ kể từ khi thêm")).toBeTruthy();
  });

  it("tắt cả hai biểu mẫu khi rút tiền chưa mở", async () => {
    vi.mocked(api.withdrawalRules).mockResolvedValue({ ...rules, withdrawals_enabled: false });
    vi.mocked(api.myWithdrawals).mockResolvedValue([withdrawal(1)]);
    render(<WithdrawPage />);
    expect(await screen.findByText("Tính năng rút tiền chưa mở")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Thêm tài khoản" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Rút tiền" })).toBeNull();
    expect(screen.queryByText("Lịch sử yêu cầu rút")).toBeNull();
  });

  it("chỉ hiện thời gian chờ trong dòng tài khoản chưa dùng được; lấy quy tắc từ API", async () => {
    vi.mocked(api.withdrawalRules).mockResolvedValue({ ...rules, min_withdraw_vnd: 76543, bank_change_cooldown_hours: 72 });
    render(<WithdrawPage />); await screen.findByText("Tối thiểu mỗi lần: 76.543 ₫");
    expect(screen.getByText("Tối thiểu mỗi lần: 76.543 ₫")).toBeTruthy();
    expect(screen.getByText("Tài khoản mới dùng được sau 72 giờ kể từ khi thêm")).toBeTruthy();
    const [usable, cooling] = screen.getAllByRole("listitem").filter((item) => item.textContent?.includes("•••• 1234"));
    expect(within(usable).queryByText(/Chưa dùng được để rút/)).toBeNull();
    expect(within(cooling).getByText(/Chưa dùng được để rút\. Dùng được từ 10:04 02\/01\/2100/)).toBeTruthy();
    expect(screen.getByRole("option", { name: "VCB · •••• 1234" })).toBeTruthy();
    expect(screen.getByLabelText("Tài khoản nhận").querySelectorAll("option")).toHaveLength(2);
  });

  it("thêm tài khoản đúng body, xóa số đầy đủ khỏi state/DOM và tải lại danh sách", async () => {
    await ready();
    fireEvent.change(screen.getByLabelText("Mã ngân hàng"), { target: { value: "ACB" } });
    fireEvent.change(screen.getByLabelText("Số tài khoản"), { target: { value: "987654321" } });
    fireEvent.change(screen.getByLabelText("Tên chủ tài khoản"), { target: { value: "TRAN THI B" } });
    fireEvent.click(screen.getByRole("button", { name: "Thêm tài khoản" }));
    await waitFor(() => expect(api.addBankAccount).toHaveBeenCalledWith({ bank_code: "ACB", account_no: "987654321", account_name: "TRAN THI B" }));
    await waitFor(() => expect((screen.getByLabelText("Số tài khoản") as HTMLInputElement).value).toBe(""));
    expect(document.body.textContent).not.toContain("987654321");
    expect(api.bankAccounts).toHaveBeenCalledTimes(2);
  });

  it("gửi số nguyên và idempotency key hợp lệ; thành công làm mới ví/lịch sử", async () => {
    await ready(); submitWithdrawal();
    await waitFor(() => expect(api.requestWithdrawal).toHaveBeenCalledTimes(1));
    const [body, key] = vi.mocked(api.requestWithdrawal).mock.calls[0];
    expect(body).toEqual({ amount_vnd: 70000, bank_account_id: 1 });
    expect(key).toMatch(/^[A-Za-z0-9_-]{8,100}$/);
    await waitFor(() => expect(screen.getByText("Đã gửi yêu cầu rút")).toBeTruthy());
    expect((screen.getByLabelText("Số tiền") as HTMLInputElement).value).toBe("");
    expect(api.wallet).toHaveBeenCalledTimes(2); expect(api.myWithdrawals).toHaveBeenCalledTimes(2);
  });

  it("tạo idempotency key mới cho ý định mới sau khi gửi thành công", async () => {
    await ready(); submitWithdrawal();
    await screen.findByText("Đã gửi yêu cầu rút");
    const firstKey = vi.mocked(api.requestWithdrawal).mock.calls[0][1];
    submitWithdrawal();
    await waitFor(() => expect(api.requestWithdrawal).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.requestWithdrawal).mock.calls[1][1]).not.toBe(firstKey);
  });

  it("dùng lại key sau lỗi mạng và 429, nhưng đổi key sau đổi ý định hoặc thành công", async () => {
    vi.mocked(api.requestWithdrawal).mockRejectedValueOnce(new ApiError(0, "network", "offline", null))
      .mockRejectedValueOnce(new ApiError(429, "rate_limited", "slow", null));
    await ready(); submitWithdrawal(); await screen.findByText("Không kết nối được máy chủ");
    const firstKey = vi.mocked(api.requestWithdrawal).mock.calls[0][1];
    fireEvent.click(screen.getByRole("button", { name: "Rút tiền" }));
    await screen.findByText("Bạn thao tác quá nhanh, vui lòng thử lại sau");
    expect(vi.mocked(api.requestWithdrawal).mock.calls[1][1]).toBe(firstKey);
    fireEvent.change(screen.getByLabelText("Số tiền"), { target: { value: "71000" } });
    fireEvent.click(screen.getByRole("button", { name: "Rút tiền" }));
    await screen.findByText("Đã gửi yêu cầu rút");
    submitWithdrawal(); await waitFor(() => expect(api.requestWithdrawal).toHaveBeenCalledTimes(4));
    expect(vi.mocked(api.requestWithdrawal).mock.calls[2][1]).not.toBe(firstKey);
    expect(vi.mocked(api.requestWithdrawal).mock.calls[3][1]).not.toBe(firstKey);
  });

  it("đổi tài khoản sau lỗi sẽ tạo key mới", async () => {
    vi.mocked(api.requestWithdrawal).mockRejectedValueOnce(new ApiError(500, "error", "oops", null));
    vi.mocked(api.bankAccounts).mockResolvedValue([account(1), { ...account(2), last4: "5678" }]);
    await ready(); submitWithdrawal(); await screen.findByText("oops");
    const oldKey = vi.mocked(api.requestWithdrawal).mock.calls[0][1];
    fireEvent.change(screen.getByLabelText("Tài khoản nhận"), { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: "Rút tiền" }));
    await screen.findByText("Đã gửi yêu cầu rút");
    expect(vi.mocked(api.requestWithdrawal).mock.calls[1][1]).not.toBe(oldKey);
    expect(vi.mocked(api.requestWithdrawal).mock.calls[1][0].bank_account_id).toBe(2);
  });

  it("bấm đúp khi đang gửi chỉ phát một request", async () => {
    let finish!: (row: ReturnType<typeof withdrawal>) => void;
    vi.mocked(api.requestWithdrawal).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    await ready();
    fireEvent.change(screen.getByLabelText("Tài khoản nhận"), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText("Số tiền"), { target: { value: "70000" } });
    const button = screen.getByRole("button", { name: "Rút tiền" });
    fireEvent.click(button); fireEvent.click(button);
    expect(api.requestWithdrawal).toHaveBeenCalledTimes(1);
    finish(withdrawal(2));
  });

  it("chặn gửi hai lần liên tiếp ở tầng submit của biểu mẫu", async () => {
    let finish!: (row: ReturnType<typeof withdrawal>) => void;
    vi.mocked(api.requestWithdrawal).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    await ready();
    fireEvent.change(screen.getByLabelText("Tài khoản nhận"), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText("Số tiền"), { target: { value: "70000" } });
    const form = screen.getByLabelText("Số tiền").closest("form");
    if (!form) throw new Error("Withdrawal form not found");
    fireEvent.submit(form); fireEvent.submit(form);
    expect(api.requestWithdrawal).toHaveBeenCalledTimes(1);
    finish(withdrawal(2));
  });

  it("dịch đủ mã lỗi nghiệp vụ sang thông báo tiếng Việt", async () => {
    const cases = [
      ["below_minimum", "Số tiền thấp hơn mức tối thiểu"], ["insufficient_funds", "Số dư rút được không đủ"],
      ["withdrawal_open_exists", "Bạn đang có một yêu cầu rút chưa xử lý xong"],
      ["idempotency_conflict", "Yêu cầu này đã được gửi với nội dung khác; vui lòng tải lại trang"],
      ["bank_account_cooling_down", "Tài khoản này chưa dùng được để rút"], ["invalid_bank_account", "Tài khoản ngân hàng không hợp lệ"],
      ["too_many_bank_accounts", "Đã đạt số tài khoản tối đa"], ["withdrawals_disabled", "Tính năng rút tiền chưa mở"],
      ["rate_limited", "Bạn thao tác quá nhanh, vui lòng thử lại sau"], ["validation_error", "Thông tin chưa hợp lệ, vui lòng kiểm tra lại"],
    ];
    for (const [code, message] of cases) {
      cleanup(); vi.mocked(api.requestWithdrawal).mockRejectedValueOnce(new ApiError(400, code, "raw api text", null));
      await ready(); submitWithdrawal(); expect(await screen.findByText(message)).toBeTruthy();
    }
  });

  it("dịch đủ trạng thái, giữ giá trị lạ và ẩn trường null", async () => {
    const statuses = ["requested", "approved", "rejected", "processing", "paid", "failed", "other_state"];
    vi.mocked(api.myWithdrawals).mockResolvedValue(statuses.map((status, index) => withdrawal(index, status)));
    await ready();
    for (const label of ["Đang chờ duyệt", "Đã duyệt", "Bị từ chối", "Đang xử lý", "Đã chi trả", "Chuyển khoản lỗi", "other_state"]) {
      expect(screen.getByText(`Trạng thái: ${label}`)).toBeTruthy();
    }
    expect(screen.queryByText("Mã giao dịch:")).toBeNull(); expect(screen.queryByText("Lý do:")).toBeNull();
    expect(screen.queryByText("Trạng thái: requested")).toBeNull();
  });

  it("chuyển về đăng nhập khi hết phiên lúc tải, thêm, rút hoặc xem thêm", async () => {
    vi.mocked(api.withdrawalRules).mockRejectedValueOnce(new ApiError(401, "session_expired", "expired", null));
    render(<WithdrawPage />); await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    cleanup(); vi.clearAllMocks(); defaultMocks(); vi.mocked(api.addBankAccount).mockRejectedValueOnce(new ApiError(401, "unauthorized", "expired", null));
    await ready();
    fireEvent.change(screen.getByLabelText("Mã ngân hàng"), { target: { value: "VCB" } });
    fireEvent.change(screen.getByLabelText("Số tài khoản"), { target: { value: "12345678" } });
    fireEvent.change(screen.getByLabelText("Tên chủ tài khoản"), { target: { value: "A" } });
    fireEvent.click(screen.getByRole("button", { name: "Thêm tài khoản" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    cleanup(); vi.clearAllMocks(); defaultMocks(); vi.mocked(api.requestWithdrawal).mockRejectedValueOnce(new ApiError(401, "unauthorized", "expired", null));
    await ready(); submitWithdrawal(); await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    cleanup(); vi.clearAllMocks(); defaultMocks(); vi.mocked(api.myWithdrawals).mockResolvedValueOnce(Array.from({ length: 50 }, (_, i) => withdrawal(i)))
      .mockRejectedValueOnce(new ApiError(401, "session_expired", "expired", null));
    await ready(); fireEvent.click(await screen.findByRole("button", { name: "Xem thêm" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });

  it("phân trang theo số đã có, nối thêm đủ 50 dòng, ngăn bấm đúp; trang ngắn ẩn nút", async () => {
    vi.mocked(api.myWithdrawals).mockResolvedValueOnce(Array.from({ length: 50 }, (_, i) => withdrawal(i)))
      .mockImplementationOnce(() => new Promise((resolve) => setTimeout(() => resolve(Array.from({ length: 50 }, (_, i) => withdrawal(i + 50))), 15)));
    await ready(); const button = await screen.findByRole("button", { name: "Xem thêm" });
    fireEvent.click(button); fireEvent.click(button);
    await waitFor(() => expect(api.myWithdrawals).toHaveBeenLastCalledWith({ limit: 50, offset: 50 }));
    await waitFor(() => expect(screen.getAllByText("Trạng thái: Đang chờ duyệt")).toHaveLength(100));
    expect(screen.getByRole("button", { name: "Xem thêm" })).toBeTruthy();
    expect(api.myWithdrawals).toHaveBeenCalledTimes(2);
    vi.mocked(api.myWithdrawals).mockResolvedValueOnce([withdrawal(100)]);
    fireEvent.click(screen.getByRole("button", { name: "Xem thêm" }));
    expect(await screen.findAllByText("Trạng thái: Đang chờ duyệt")).toHaveLength(101);   // đợi tải xong rồi mới kiểm nút (trong lúc tải nút đang là "Đang tải…")
    expect(screen.queryByRole("button", { name: "Xem thêm" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Đang tải…" })).toBeNull();
    vi.mocked(api.myWithdrawals).mockResolvedValue([]);
    cleanup(); await ready(); expect(screen.getByText("Chưa có yêu cầu rút tiền nào.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Xem thêm" })).toBeNull();
  });

  it("sau khi gửi thành công chỉ hiện Xem thêm nếu lịch sử tải lại đủ 50 dòng", async () => {
    vi.mocked(api.myWithdrawals).mockResolvedValueOnce(Array.from({ length: 50 }, (_, i) => withdrawal(i)))
      .mockResolvedValueOnce(Array.from({ length: 12 }, (_, i) => withdrawal(i + 50)));
    await ready();
    submitWithdrawal();
    await screen.findByText("Đã gửi yêu cầu rút");
    await waitFor(() => expect(api.myWithdrawals).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole("button", { name: "Xem thêm" })).toBeNull();

    cleanup(); vi.clearAllMocks(); defaultMocks();
    vi.mocked(api.myWithdrawals).mockResolvedValueOnce(Array.from({ length: 50 }, (_, i) => withdrawal(i)))
      .mockResolvedValueOnce(Array.from({ length: 50 }, (_, i) => withdrawal(i + 50)));
    await ready(); submitWithdrawal();
    await screen.findByText("Đã gửi yêu cầu rút");
    await waitFor(() => expect(api.myWithdrawals).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("button", { name: "Xem thêm" })).toBeTruthy();
  });
});
