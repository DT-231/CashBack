// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import WithdrawalsPage from "./WithdrawalsPage";
import { ApiError } from "@/lib/api-client";
import type { AdminWithdrawalOut } from "@/lib/types";

const mocks = vi.hoisted(() => ({
  replace: vi.fn(), router: { replace: vi.fn() }, withdrawals: vi.fn(), approve: vi.fn(), reject: vi.fn(), fail: vi.fn(), paid: vi.fn(), account: vi.fn(), csv: vi.fn(),
}));
vi.mock("next/navigation", () => ({ useRouter: () => mocks.router }));
vi.mock("@/lib/api-client", () => ({ ApiError: class ApiError extends Error { status: number; code: string; constructor(status: number, code: string) { super(code); this.status = status; this.code = code; } get isAuth() { return this.status === 401; } get isMfaRequired() { return this.code === "mfa_required"; } }, api: { adminWithdrawals: mocks.withdrawals, adminApprove: mocks.approve, adminReject: mocks.reject, adminFail: mocks.fail, adminMarkPaid: mocks.paid, adminPayoutAccount: mocks.account, adminExportCsv: mocks.csv } }));

function row(id: number, status: string, more: Partial<AdminWithdrawalOut> = {}): AdminWithdrawalOut {
  return { id, user_id: 23, amount_vnd: 125000, status: status as AdminWithdrawalOut["status"], bank_account_id: null, bank_code: "VCB", last4: "4321", provider_ref: null, decided_reason: null, created_at: "2026-01-02T03:04:00Z", updated_at: "2026-01-02T03:04:00Z", transfer_note: `CASHBACK W${id}`, approved_by: null, approved_at: null, paid_by: null, paid_at: null, ...more };
}
const fullAccount = { withdrawal_id: 1, amount_vnd: 125000, bank_code: "VCB", account_no: "123456789012", account_name: "Nguyen A" };

describe("WithdrawalsPage", () => {
  beforeEach(() => { vi.clearAllMocks(); mocks.withdrawals.mockResolvedValue([]); mocks.approve.mockResolvedValue({}); mocks.reject.mockResolvedValue({}); mocks.fail.mockResolvedValue({}); mocks.paid.mockResolvedValue({}); mocks.account.mockResolvedValue(fullAccount); mocks.csv.mockResolvedValue(new Blob(["csv"])); });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("truyền bộ lọc và hiển thị đủ nhãn/trạng thái, ẩn trường null và transfer_note nguyên văn", async () => {
    mocks.withdrawals.mockResolvedValueOnce([row(1, "requested", { transfer_note: "CASHBACK W1 / nguyên văn" }), row(2, "approved"), row(3, "rejected", { decided_reason: null }), row(4, "processing"), row(5, "paid", { provider_ref: null }), row(6, "failed")]);
    render(<WithdrawalsPage />);
    expect(await screen.findByText((_content, element) => element?.tagName === "P" && element.textContent?.endsWith("Đang chờ duyệt") === true)).toBeTruthy();
    for (const text of ["Đã duyệt", "Bị từ chối", "Đang xử lý", "Đã chi trả", "Chuyển khoản lỗi"]) expect(screen.getByText((_content, element) => element?.tagName === "P" && element.textContent?.endsWith(text) === true)).toBeTruthy();
    expect(screen.getByText("CASHBACK W1 / nguyên văn")).toBeTruthy();
    expect(document.body.textContent).not.toContain("Mã giao dịch:"); expect(document.body.textContent).not.toContain("Lý do:");
    const requested = screen.getByText("Yêu cầu #1").parentElement!;
    expect(within(requested).getByRole("button", { name: "Duyệt" })).toBeTruthy();
    for (const id of [3, 4, 5, 6]) expect(within(screen.getByText(`Yêu cầu #${id}`).parentElement!).queryByRole("button")).toBeNull();
    fireEvent.change(screen.getByLabelText("Lọc trạng thái"), { target: { value: "approved" } });
    await waitFor(() => expect(mocks.withdrawals).toHaveBeenLastCalledWith({ status: "approved", limit: 50, offset: 0 }));
  });

  it("yêu cầu xem số tài khoản theo thao tác và xóa số khi Ẩn, đổi lọc hoặc hành động", async () => {
    mocks.withdrawals.mockResolvedValue([row(1, "approved")]);
    render(<WithdrawalsPage />);
    await screen.findByText("Yêu cầu #1");
    expect(mocks.account).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Xem số tài khoản" }));
    expect(await screen.findByText("123456789012")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Ẩn" }));
    expect(document.body.textContent).not.toContain("123456789012");
    fireEvent.click(screen.getByRole("button", { name: "Xem số tài khoản" }));
    await screen.findByText("123456789012");
    fireEvent.change(screen.getByLabelText("Lọc trạng thái"), { target: { value: "approved" } });
    await waitFor(() => expect(document.body.textContent).not.toContain("123456789012"));
    fireEvent.click(screen.getByRole("button", { name: "Xem số tài khoản" })); await screen.findByText("123456789012");
    fireEvent.change(screen.getByLabelText("Mã giao dịch ngân hàng"), { target: { value: "ref-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Đánh dấu đã chi trả" }));
    await waitFor(() => expect(document.body.textContent).not.toContain("123456789012"));
  });

  it("không gửi lý do ngắn, gửi đúng id/lý do và chống bấm đúp", async () => {
    mocks.withdrawals.mockResolvedValue([row(7, "requested")]);
    let finish!: (value: unknown) => void;
    mocks.approve.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    render(<WithdrawalsPage />); await screen.findByText("Yêu cầu #7");
    fireEvent.change(screen.getByLabelText("Lý do từ chối"), { target: { value: "ab" } });
    expect((screen.getByRole("button", { name: "Từ chối" }) as HTMLButtonElement).disabled).toBe(true);
    expect(mocks.reject).not.toHaveBeenCalled();
    const approve = screen.getByRole("button", { name: "Duyệt" });
    fireEvent.click(approve); fireEvent.click(approve);
    expect(mocks.approve).toHaveBeenCalledTimes(1); expect(mocks.approve).toHaveBeenCalledWith(7);
    finish({});
    await waitFor(() => expect(mocks.withdrawals).toHaveBeenCalledTimes(2));
  });

  it("gửi đúng lý do, mã giao dịch và hiển thị lỗi duplicate/invalid_transition", async () => {
    mocks.withdrawals.mockResolvedValue([row(8, "approved")]);
    mocks.paid.mockRejectedValueOnce(new ApiError(409, "duplicate_provider_ref", "duplicate", null));
    render(<WithdrawalsPage />); await screen.findByText("Yêu cầu #8");
    fireEvent.change(screen.getByLabelText("Mã giao dịch ngân hàng"), { target: { value: "BANK-77" } });
    fireEvent.click(screen.getByRole("button", { name: "Đánh dấu đã chi trả" }));
    expect(await screen.findByText("Mã giao dịch này đã dùng cho yêu cầu khác")).toBeTruthy();
    expect(mocks.paid).toHaveBeenCalledWith(8, "BANK-77");
    mocks.paid.mockRejectedValueOnce(new ApiError(409, "invalid_transition", "invalid", null));
    fireEvent.change(screen.getByLabelText("Mã giao dịch ngân hàng"), { target: { value: "BANK-77" } });
    fireEvent.click(screen.getByRole("button", { name: "Đánh dấu đã chi trả" }));
    expect(await screen.findByText("Yêu cầu đã được xử lý ở nơi khác, đã tải lại danh sách")).toBeTruthy();
    expect(mocks.withdrawals.mock.calls.length).toBe(2);
  });

  it("gửi đúng id và lý do khi từ chối hoặc báo chuyển khoản lỗi", async () => {
    mocks.withdrawals.mockResolvedValue([row(9, "requested"), row(10, "approved")]);
    render(<WithdrawalsPage />); await screen.findByText("Yêu cầu #10");
    const requested = within(screen.getByText("Yêu cầu #9").parentElement!);
    fireEvent.change(requested.getByLabelText("Lý do từ chối"), { target: { value: "Sai thông tin" } });
    fireEvent.click(requested.getByRole("button", { name: "Từ chối" }));
    await waitFor(() => expect(mocks.reject).toHaveBeenCalledWith(9, "Sai thông tin"));
    const approved = within(screen.getByText("Yêu cầu #10").parentElement!);
    fireEvent.change(approved.getByLabelText("Lý do chuyển khoản lỗi"), { target: { value: "Ngân hàng từ chối" } });
    fireEvent.click(approved.getByRole("button", { name: "Chuyển khoản lỗi" }));
    await waitFor(() => expect(mocks.fail).toHaveBeenCalledWith(10, "Ngân hàng từ chối"));
  });

  it("xuất CSV, tải đúng tên và thu hồi URL; MFA required chuyển tới trang MFA", async () => {
    const createObjectURL = vi.fn(() => "blob:csv"); const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) { expect(this.download).toBe("cashback-payouts.csv"); });
    render(<WithdrawalsPage />); await screen.findByText("Không có yêu cầu rút tiền.");
    fireEvent.click(screen.getByRole("button", { name: "Tải CSV chuyển khoản (các yêu cầu đã duyệt)" }));
    await screen.findByText("Tệp chứa số tài khoản đầy đủ: lưu an toàn và xóa sau khi chuyển khoản");
    expect(mocks.csv).toHaveBeenCalledTimes(1); expect(createObjectURL).toHaveBeenCalledTimes(1); expect(revokeObjectURL).toHaveBeenCalledWith("blob:csv");
    expect(click).toHaveBeenCalled();
    mocks.csv.mockRejectedValueOnce(new ApiError(403, "mfa_required", "mfa required", null));
    fireEvent.click(screen.getByRole("button", { name: "Tải CSV chuyển khoản (các yêu cầu đã duyệt)" }));
    await waitFor(() => expect(mocks.router.replace).toHaveBeenCalledWith("/admin/mfa"));
    vi.unstubAllGlobals(); click.mockRestore();
  });

  it("xem thêm nối trang, dùng offset số dòng và ẩn nút khi trang sau ít hơn 50", async () => {
    const first = Array.from({ length: 50 }, (_, index) => row(index + 1, "paid"));
    mocks.withdrawals.mockResolvedValueOnce(first).mockResolvedValueOnce([row(51, "paid")]);
    render(<WithdrawalsPage />); await screen.findByText("Yêu cầu #50");
    fireEvent.click(screen.getByRole("button", { name: "Xem thêm" }));
    expect(await screen.findByText("Yêu cầu #51")).toBeTruthy();
    expect(mocks.withdrawals).toHaveBeenLastCalledWith({ status: undefined, limit: 50, offset: 50 });
    expect(screen.queryByRole("button", { name: "Xem thêm" })).toBeNull();
  });
});
