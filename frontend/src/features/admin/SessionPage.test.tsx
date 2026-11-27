// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import SessionPage from "./SessionPage";

const { adminShopeeSessionStatus, adminSetShopeeCookie, replace, router } = vi.hoisted(() => {
  const replace = vi.fn();
  return { adminShopeeSessionStatus: vi.fn(), adminSetShopeeCookie: vi.fn(), replace, router: { replace } };
});
vi.mock("@/lib/api-client", () => ({
  ApiError: class ApiError extends Error {
    constructor(public status: number, public code: string, message: string, public requestId: string | null = null) { super(message); }
    get isAuth() { return this.status === 401 && ["session_expired", "unauthorized"].includes(this.code); }
    get isMfaRequired() { return this.status === 403 && this.code === "mfa_required"; }
  },
  api: { adminShopeeSessionStatus, adminSetShopeeCookie },
}));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const session = (status = "healthy", has_cookie = true, dates = true) => ({ has_cookie, status, last_ok_at: dates ? "2026-11-27T12:00:00Z" : null, failure_count: 3, updated_at: dates ? "2026-11-28T12:00:00Z" : null });
const apiError = async (status: number, code: string, message = "lỗi") => {
  const { ApiError } = await import("@/lib/api-client");
  return new ApiError(status, code, message, null);
};

describe("SessionPage", () => {
  beforeEach(() => { adminShopeeSessionStatus.mockReset(); adminSetShopeeCookie.mockReset(); replace.mockReset(); adminShopeeSessionStatus.mockResolvedValue(session()); adminSetShopeeCookie.mockResolvedValue(undefined); });
  afterEach(cleanup);

  it("renders cookie presence, all known labels, unknown values, dates, and null dates safely", async () => {
    for (const [key, label] of [["unknown", "Chưa rõ"], ["healthy", "Hoạt động tốt"], ["degraded", "Có vấn đề"], ["expired", "Hết hạn"], ["blocked", "Bị chặn"], ["future", "future"]]) {
      cleanup(); adminShopeeSessionStatus.mockResolvedValueOnce(session(key)); render(<SessionPage />);
      expect(await screen.findByText(`Trạng thái: ${label}`)).toBeTruthy();
    }
    cleanup(); adminShopeeSessionStatus.mockResolvedValueOnce(session("unknown", false, false)); render(<SessionPage />);
    expect(await screen.findByText("Chưa có cookie")).toBeTruthy();
    expect(screen.queryByText(/Lần OK gần nhất:/)).toBeNull(); expect(screen.queryByText(/Cập nhật lúc:/)).toBeNull();
    expect(screen.getByText("Số lần lỗi liên tiếp: 3")).toBeTruthy();
    cleanup(); adminShopeeSessionStatus.mockResolvedValueOnce(session()); render(<SessionPage />);
    expect(await screen.findByText("Đã lưu cookie")).toBeTruthy(); expect(screen.getByText(/Lần OK gần nhất:/)).toBeTruthy(); expect(screen.getByText(/Cập nhật lúc:/)).toBeTruthy();
  });

  it("does not save blank input; saves exact cookie once and clears it and the DOM", async () => {
    render(<SessionPage />); await screen.findByText("Đã lưu cookie");
    const input = screen.getByLabelText("Dán cookie mới");
    expect((input as HTMLTextAreaElement).autocomplete).toBe("off");
    fireEvent.change(input, { target: { value: "  " } }); fireEvent.submit(input.closest("form")!);
    expect(adminSetShopeeCookie).not.toHaveBeenCalled();
    const value = "SPC_EC=secret; session_id=private";
    fireEvent.change(input, { target: { value } }); fireEvent.submit(input.closest("form")!); fireEvent.submit(input.closest("form")!);
    await screen.findByText("Đã lưu cookie (không hiển thị lại)");
    expect(adminSetShopeeCookie).toHaveBeenCalledTimes(1); expect(adminSetShopeeCookie).toHaveBeenCalledWith(value);
    expect((screen.getByLabelText("Dán cookie mới") as HTMLTextAreaElement).value).toBe("");
    expect(document.body.textContent).not.toContain(value);
  });

  it("clears cookie on failure, maps known errors, and displays unknown errors without the cookie", async () => {
    const cases = [
      ["invalid_cookie", "Cookie không hợp lệ (dạng a=b; c=d, tối đa 8KB)", 422],
      ["not_configured", "Máy chủ chưa cấu hình khóa mã hóa (BANK_ENC_KEY)", 503],
      ["forbidden", "Chỉ admin được thực hiện", 403],
      ["other", "Lỗi API chung [đã ẩn]", 500],
    ] as const;
    for (const [code, message, status] of cases) {
      cleanup(); adminSetShopeeCookie.mockRejectedValueOnce(await apiError(status, code, code === "other" ? message : "private backend detail")); render(<SessionPage />); await screen.findByText("Đã lưu cookie");
      const value = `cookie-secret-${code}`; const input = screen.getByLabelText("Dán cookie mới");
      fireEvent.change(input, { target: { value } }); fireEvent.click(screen.getByRole("button", { name: "Lưu cookie" }));
      expect((await screen.findByRole("alert")).textContent).toContain(message);
      expect((input as HTMLTextAreaElement).value).toBe(""); expect(document.body.textContent).not.toContain(value);
    }
  });

  it("redirects auth and MFA failures and reports network errors while loading or saving", async () => {
    adminShopeeSessionStatus.mockRejectedValueOnce(await apiError(401, "session_expired")); render(<SessionPage />); await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    cleanup(); replace.mockClear(); adminShopeeSessionStatus.mockRejectedValueOnce(await apiError(403, "mfa_required")); render(<SessionPage />); await waitFor(() => expect(replace).toHaveBeenCalledWith("/admin/mfa"));
    cleanup(); adminShopeeSessionStatus.mockRejectedValueOnce(await apiError(0, "network")); render(<SessionPage />); expect((await screen.findByRole("alert")).textContent).toContain("Không kết nối được máy chủ");
    for (const [status, code, target] of [[401, "unauthorized", "/login"], [403, "mfa_required", "/admin/mfa"], [0, "network", ""]] as const) {
      cleanup(); replace.mockClear(); adminShopeeSessionStatus.mockResolvedValue(session()); adminSetShopeeCookie.mockRejectedValueOnce(await apiError(status, code)); render(<SessionPage />); await screen.findByText("Đã lưu cookie");
      const input = screen.getByLabelText("Dán cookie mới"); fireEvent.change(input, { target: { value: `secret-${code}` } }); fireEvent.click(screen.getByRole("button", { name: "Lưu cookie" }));
      if (target) await waitFor(() => expect(replace).toHaveBeenCalledWith(target));
      else expect((await screen.findByRole("alert")).textContent).toContain("Không kết nối được máy chủ");
      await waitFor(() => expect((input as HTMLTextAreaElement).value).toBe(""));
      expect(document.body.textContent).not.toContain(`secret-${code}`);
    }
  });

  it("reloads the status after saving so the page shows the new state", async () => {
    adminShopeeSessionStatus.mockResolvedValueOnce(session("blocked", true)).mockResolvedValueOnce(session("healthy", true));
    render(<SessionPage />);
    await screen.findByText("Trạng thái: Bị chặn");
    fireEvent.change(screen.getByLabelText("Dán cookie mới"), { target: { value: "a=b; c=d" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu cookie" }));
    await screen.findByText("Trạng thái: Hoạt động tốt");
    expect(adminShopeeSessionStatus).toHaveBeenCalledTimes(2);
  });

  it("never echoes the pasted cookie back inside an unknown server error message", async () => {
    adminSetShopeeCookie.mockRejectedValueOnce(await apiError(500, "internal_error", "boom SPC_ST=SECRETCOOKIE123 boom"));
    render(<SessionPage />);
    await screen.findByText(/Đã lưu cookie|Chưa có cookie/);
    fireEvent.change(screen.getByLabelText("Dán cookie mới"), { target: { value: "SPC_ST=SECRETCOOKIE123" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu cookie" }));
    await screen.findByRole("alert");
    expect(document.body.textContent).not.toContain("SECRETCOOKIE123");
    expect(screen.getByRole("alert").textContent).toContain("[đã ẩn]");
    expect((screen.getByLabelText("Dán cookie mới") as HTMLTextAreaElement).value).toBe("");
  });
});
