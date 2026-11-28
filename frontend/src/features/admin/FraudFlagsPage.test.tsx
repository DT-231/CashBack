// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import FraudFlagsPage from "./FraudFlagsPage";

const { adminFraudFlags, adminResolveFraudFlag, replace, router } = vi.hoisted(() => { const replace = vi.fn(); return { adminFraudFlags: vi.fn(), adminResolveFraudFlag: vi.fn(), replace, router: { replace } }; });
vi.mock("@/lib/api-client", () => ({
  ApiError: class ApiError extends Error {
    constructor(public status: number, public code: string, message: string, public requestId: string | null = null) { super(message); }
    get isAuth() { return this.status === 401 && ["session_expired", "unauthorized"].includes(this.code); }
    get isMfaRequired() { return this.status === 403 && this.code === "mfa_required"; }
  },
  api: { adminFraudFlags, adminResolveFraudFlag },
}));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const flag = (id: number, over: Record<string, unknown> = {}) => ({
  id, user_id: 100 + id, email: `u${id}@x.vn`, rule: "shared_ip", score: 4, status: "open", detail: { distinct_users: 4 },
  created_at: "2026-11-28T02:00:00Z", updated_at: "2026-11-28T02:00:00Z", resolved_by: null, resolved_at: null, resolution_note: null, ...over,
});
const apiError = async (status: number, code: string, message = "lỗi") => { const { ApiError } = await import("@/lib/api-client"); return new ApiError(status, code, message, null); };
const note = (id: number, v = "đã kiểm tra") => fireEvent.change(screen.getByLabelText("Ghi chú (bắt buộc)", { selector: `#flag-note-${id}` }), { target: { value: v } });

describe("FraudFlagsPage", () => {
  beforeEach(() => { adminFraudFlags.mockReset(); adminResolveFraudFlag.mockReset(); replace.mockReset(); adminFraudFlags.mockResolvedValue([flag(1)]); adminResolveFraudFlag.mockResolvedValue(undefined); });
  afterEach(cleanup);

  it("renders known/unknown rules, statuses, details, and hides null resolution fields", async () => {
    adminFraudFlags.mockResolvedValue([
      flag(1), flag(2, { rule: "high_cancel_rate", detail: { orders: 10, cancelled_or_returned: 7 } }), flag(3, { rule: "click_burst", detail: { max_clicks_per_hour: 99 } }),
      flag(4, { rule: "future_rule", status: "future", detail: { weird: 1 } }),
      flag(5, { status: "confirmed", resolved_at: "2026-11-28T03:00:00Z", resolution_note: "ghi chú nguyên văn" }), flag(6, { status: "dismissed" })]);
    render(<FraudFlagsPage />);
    await screen.findByText("#1 · u1@x.vn");
    for (const t of ["Luật: Nhiều tài khoản cùng IP", "Luật: Tỷ lệ hủy/hoàn cao", "Luật: Click dồn dập", "Luật: future_rule", "Trạng thái: Đang mở", "Trạng thái: Đã xác nhận", "Trạng thái: Đã bỏ qua", "Trạng thái: future",
      "Số tài khoản: 4", "Số đơn: 10", "Hủy/hoàn: 7", "Click tối đa/giờ: 99", "weird: 1", "Ghi chú: ghi chú nguyên văn", "Người dùng: 101", "Điểm: 4"]) expect(screen.getAllByText(t).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Xử lý lúc:/)).toHaveLength(1);
    expect(screen.getAllByText(/Ghi chú:/)).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "Bỏ qua" })).toHaveLength(3); // chỉ cờ đang mở (1,2,3) có nút xử lý
  });

  it("filters by status and defaults to open", async () => {
    render(<FraudFlagsPage />);
    await screen.findByText("#1 · u1@x.vn");
    expect(adminFraudFlags).toHaveBeenLastCalledWith({ status: "open", limit: 50, offset: 0 });
    fireEvent.click(screen.getByRole("button", { name: "Đã xác nhận" }));
    await waitFor(() => expect(adminFraudFlags).toHaveBeenLastCalledWith({ status: "confirmed", limit: 50, offset: 0 }));
  });

  it("loads more by row count, appends, and hides button on a short page; empty state", async () => {
    adminFraudFlags.mockResolvedValueOnce(Array.from({ length: 50 }, (_, i) => flag(i + 1))).mockResolvedValueOnce([flag(51)]);
    render(<FraudFlagsPage />);
    await screen.findByText("#1 · u1@x.vn");
    const more = screen.getByRole("button", { name: "Xem thêm" });
    fireEvent.click(more); fireEvent.click(more);
    await screen.findByText("#51 · u51@x.vn");
    expect(adminFraudFlags).toHaveBeenCalledTimes(2);
    expect(adminFraudFlags).toHaveBeenLastCalledWith({ status: "open", limit: 50, offset: 50 });
    expect(screen.getByText("#1 · u1@x.vn")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Xem thêm" })).toBeNull();
    cleanup(); adminFraudFlags.mockResolvedValue([]); render(<FraudFlagsPage />);
    await screen.findByText("Không có cờ gian lận.");
  });

  it("requires a note of 3+ trimmed chars; sends exact decision once; reloads and shows notice", async () => {
    render(<FraudFlagsPage />);
    await screen.findByText("#1 · u1@x.vn");
    const dismiss = screen.getByRole("button", { name: "Bỏ qua" }) as HTMLButtonElement;
    expect(dismiss.disabled).toBe(true);
    note(1, "  ab  "); expect(dismiss.disabled).toBe(true);
    fireEvent.click(dismiss); expect(adminResolveFraudFlag).not.toHaveBeenCalled();
    note(1, "  đã kiểm tra  ");
    adminFraudFlags.mockResolvedValue([]);
    const confirm = screen.getByRole("button", { name: "Xác nhận gian lận" });
    fireEvent.click(confirm); fireEvent.click(confirm);
    await screen.findByText("Đã xử lý cờ #1: Đã xác nhận");
    expect(adminResolveFraudFlag).toHaveBeenCalledTimes(1);
    expect(adminResolveFraudFlag).toHaveBeenCalledWith(1, "confirmed", "đã kiểm tra");
    expect(screen.queryByText("#1 · u1@x.vn")).toBeNull();
  });

  it("sends dismissed for the dismiss button", async () => {
    render(<FraudFlagsPage />);
    await screen.findByText("#1 · u1@x.vn");
    note(1); fireEvent.click(screen.getByRole("button", { name: "Bỏ qua" }));
    await waitFor(() => expect(adminResolveFraudFlag).toHaveBeenCalledWith(1, "dismissed", "đã kiểm tra"));
  });

  it.each([["flag_closed", "Cờ này đã được xử lý ở nơi khác, đã tải lại danh sách"], ["flag_not_found", "Không tìm thấy cờ, đã tải lại danh sách"]])("handles %s by reloading", async (code, msg) => {
    render(<FraudFlagsPage />);
    await screen.findByText("#1 · u1@x.vn");
    adminResolveFraudFlag.mockRejectedValue(await apiError(409, code));
    note(1); fireEvent.click(screen.getByRole("button", { name: "Bỏ qua" }));
    await screen.findByText(msg);
    expect(adminFraudFlags).toHaveBeenCalledTimes(2);
  });

  it("maps forbidden, unknown, network, auth and mfa errors", async () => {
    render(<FraudFlagsPage />);
    await screen.findByText("#1 · u1@x.vn");
    adminResolveFraudFlag.mockRejectedValueOnce(await apiError(403, "forbidden"));
    note(1); fireEvent.click(screen.getByRole("button", { name: "Bỏ qua" }));
    await screen.findByText("Chỉ admin được thực hiện");
    adminResolveFraudFlag.mockRejectedValueOnce(await apiError(500, "boom", "lỗi lạ"));
    fireEvent.click(screen.getByRole("button", { name: "Bỏ qua" }));
    await screen.findByText("lỗi lạ");
    adminResolveFraudFlag.mockRejectedValueOnce(await apiError(0, "network"));
    fireEvent.click(screen.getByRole("button", { name: "Bỏ qua" }));
    await screen.findByText("Không kết nối được máy chủ");
    adminResolveFraudFlag.mockRejectedValueOnce(await apiError(401, "session_expired"));
    fireEvent.click(screen.getByRole("button", { name: "Bỏ qua" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    adminResolveFraudFlag.mockRejectedValueOnce(await apiError(403, "mfa_required"));
    fireEvent.click(screen.getByRole("button", { name: "Bỏ qua" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/admin/mfa"));
  });

  it("redirects on initial-load auth/mfa errors and shows network error", async () => {
    adminFraudFlags.mockRejectedValueOnce(await apiError(401, "unauthorized"));
    render(<FraudFlagsPage />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    cleanup(); adminFraudFlags.mockRejectedValueOnce(await apiError(403, "mfa_required"));
    render(<FraudFlagsPage />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/admin/mfa"));
    cleanup(); adminFraudFlags.mockRejectedValueOnce(await apiError(0, "network"));
    render(<FraudFlagsPage />);
    await screen.findByText("Không kết nối được máy chủ");
  });
});
