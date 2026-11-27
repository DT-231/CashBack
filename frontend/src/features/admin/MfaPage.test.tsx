// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MfaPage from "./MfaPage";
import { ApiError } from "@/lib/api-client";

const mocks = vi.hoisted(() => ({ replace: vi.fn(), router: { replace: vi.fn() }, status: vi.fn(), setup: vi.fn(), enable: vi.fn(), verify: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => mocks.router }));
vi.mock("@/lib/api-client", () => ({ ApiError: class ApiError extends Error { status: number; code: string; constructor(status: number, code: string) { super(code); this.status = status; this.code = code; } get isAuth() { return this.status === 401; } get isMfaRequired() { return this.code === "mfa_required"; } }, api: { mfaStatus: mocks.status, mfaSetup: mocks.setup, mfaEnable: mocks.enable, mfaVerify: mocks.verify } }));

describe("MfaPage", () => {
  beforeEach(() => { vi.clearAllMocks(); mocks.status.mockResolvedValue({ enabled: false, pending: false, verified: false }); });
  afterEach(cleanup);
  it("thiết lập, bật TOTP, yêu cầu xác nhận đủ 8 mã rồi xóa mã khỏi DOM", async () => {
    mocks.setup.mockResolvedValue({ secret: "secret-value", otpauth_uri: "otpauth://totp/example" });
    mocks.enable.mockResolvedValue({ recovery_codes: ["recovery-1", "recovery-2", "recovery-3", "recovery-4", "recovery-5", "recovery-6", "recovery-7", "recovery-8"] });
    mocks.verify.mockResolvedValue({ ok: true });
    render(<MfaPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Thiết lập" }));
    expect(await screen.findByText("secret-value")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Mã xác minh"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Bật" }));
    expect(await screen.findByText("recovery-8")).toBeTruthy();
    const proceed = screen.getByRole("button", { name: "Tiếp tục" }) as HTMLButtonElement;
    expect(proceed.disabled).toBe(true);
    fireEvent.click(screen.getByRole("checkbox")); fireEvent.click(proceed);
    await waitFor(() => expect(screen.queryByText("recovery-1")).toBeNull());
    fireEvent.change(screen.getByLabelText("Mã xác minh"), { target: { value: "654321" } });
    fireEvent.click(screen.getByRole("button", { name: "Xác minh phiên" }));
    await waitFor(() => expect(mocks.verify).toHaveBeenCalledWith({ code: "654321" }));
    expect(mocks.router.replace).toHaveBeenCalledWith("/admin/withdrawals");
  });
  it("gửi riêng recovery_code và xóa mã sau khi gửi", async () => {
    mocks.status.mockResolvedValue({ enabled: true, pending: false, verified: false });
    mocks.verify.mockRejectedValue(new ApiError(400, "mfa_invalid", "invalid", null));
    render(<MfaPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Dùng mã khôi phục" }));
    const input = screen.getByLabelText("Mã khôi phục") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "recover-me" } });
    fireEvent.click(screen.getByRole("button", { name: "Xác minh phiên" }));
    await waitFor(() => expect(mocks.verify).toHaveBeenCalledWith({ recovery_code: "recover-me" }));
    expect(await screen.findByText("Mã không đúng hoặc đã dùng")).toBeTruthy();
    expect(input.value).toBe("");
  });
  it.each([["mfa_invalid", "Mã không đúng hoặc đã dùng"], ["rate_limited", "Bạn thử quá nhiều lần, vui lòng đợi"], ["mfa_state", "Trạng thái TOTP không hợp lệ, vui lòng tải lại"]])("hiện thông báo %s", async (code, text) => {
    mocks.status.mockResolvedValue({ enabled: true, pending: false, verified: false });
    mocks.verify.mockRejectedValue(new ApiError(400, code, code, null));
    render(<MfaPage />);
    fireEvent.change(await screen.findByLabelText("Mã xác minh"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Xác minh phiên" }));
    expect(await screen.findByText(text)).toBeTruthy();
    expect((screen.getByLabelText("Mã xác minh") as HTMLInputElement).value).toBe("");
  });
});
