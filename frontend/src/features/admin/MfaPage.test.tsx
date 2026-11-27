// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MfaPage from "./MfaPage";
import { ApiError } from "@/lib/api-client";

const mocks = vi.hoisted(() => ({ replace: vi.fn(), router: { replace: vi.fn() }, status: vi.fn(), setup: vi.fn(), enable: vi.fn(), verify: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => mocks.router }));
vi.mock("@/lib/api-client", () => ({ ApiError: class ApiError extends Error { status: number; code: string; constructor(status: number, code: string) { super(code); this.status = status; this.code = code; } get isAuth() { return this.status === 401; } get isMfaRequired() { return this.code === "mfa_required"; } }, api: { mfaStatus: mocks.status, mfaSetup: mocks.setup, mfaEnable: mocks.enable, mfaVerify: mocks.verify } }));

describe("MfaPage", () => {
  beforeEach(() => { vi.resetAllMocks(); mocks.status.mockResolvedValue({ enabled: false, pending: false, verified: false }); });
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
    expect(document.body.textContent).not.toContain("secret-value");
    expect(document.body.textContent).not.toContain("recovery-1");
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

  it("hiện đúng nút thiết lập theo pending, điều hướng phiên đã xác minh và ẩn secret sau xác minh", async () => {
    mocks.status.mockResolvedValueOnce({ enabled: false, pending: true, verified: false });
    mocks.setup.mockResolvedValue({ secret: "totp-secret", otpauth_uri: "otpauth://private" });
    const { unmount } = render(<MfaPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Thiết lập lại" }));
    expect(await screen.findByText("totp-secret")).toBeTruthy();
    unmount();

    mocks.status.mockResolvedValueOnce({ enabled: true, pending: true, verified: true });
    mocks.verify.mockResolvedValue({ ok: true });
    render(<MfaPage />);
    await waitFor(() => expect(mocks.router.replace).toHaveBeenCalledWith("/admin/withdrawals"));
    expect(await screen.findByText("Phiên này đã xác minh")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Tới danh sách rút tiền" })).toBeTruthy();
  });

  it("chặn gửi đúp setup, enable và verify đồng bộ", async () => {
    let finishSetup!: (value: unknown) => void;
    mocks.setup.mockImplementation(() => new Promise((resolve) => { finishSetup = resolve; }));
    render(<MfaPage />);
    const setupButton = await screen.findByRole("button", { name: "Thiết lập" });
    fireEvent.click(setupButton); fireEvent.click(setupButton);
    expect(mocks.setup).toHaveBeenCalledTimes(1);
    finishSetup({ secret: "s", otpauth_uri: "uri" });
    await screen.findByText("s");
    let finishEnable!: (value: unknown) => void;
    mocks.enable.mockImplementation(() => new Promise((resolve) => { finishEnable = resolve; }));
    fireEvent.change(screen.getByLabelText("Mã xác minh"), { target: { value: "123456" } });
    const enableForm = screen.getByLabelText("Mã xác minh").closest("form")!;
    fireEvent.submit(enableForm); fireEvent.submit(enableForm);
    expect(mocks.enable).toHaveBeenCalledTimes(1);
    finishEnable({ recovery_codes: ["one"] });
    await screen.findByText("one");
    fireEvent.click(screen.getByRole("checkbox")); fireEvent.click(screen.getByRole("button", { name: "Tiếp tục" }));
    fireEvent.change(screen.getByLabelText("Mã xác minh"), { target: { value: "654321" } });
    let finishVerify!: (value: unknown) => void;
    mocks.verify.mockImplementation(() => new Promise((resolve) => { finishVerify = resolve; }));
    const verifyForm = screen.getByLabelText("Mã xác minh").closest("form")!;
    fireEvent.submit(verifyForm); fireEvent.submit(verifyForm);
    expect(mocks.verify).toHaveBeenCalledTimes(1);
    expect(mocks.verify).toHaveBeenCalledWith({ code: "654321" });
    finishVerify({ ok: true });
    await waitFor(() => expect(mocks.router.replace).toHaveBeenCalledWith("/admin/withdrawals"));
    expect(document.body.textContent).not.toContain("secret-value");
    expect(document.body.textContent).not.toContain("recovery-1");
  });

  it("xóa mã enable sau lỗi và xóa dữ liệu cùng lỗi khi đổi kiểu mã", async () => {
    mocks.setup.mockResolvedValue({ secret: "secret", otpauth_uri: "uri" });
    mocks.enable.mockRejectedValueOnce(new ApiError(400, "mfa_invalid", "bad", null));
    mocks.status.mockResolvedValue({ enabled: false, pending: false, verified: false });
    const first = render(<MfaPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Thiết lập" }));
    await screen.findByText("secret");
    const code = screen.getByLabelText("Mã xác minh") as HTMLInputElement;
    fireEvent.change(code, { target: { value: "123456" } });
    fireEvent.submit(code.closest("form")!);
    expect(await screen.findByText("Mã không đúng hoặc đã dùng")).toBeTruthy();
    await waitFor(() => expect(code.value).toBe(""));
    first.unmount();

    mocks.status.mockResolvedValue({ enabled: true, pending: false, verified: false });
    mocks.verify.mockRejectedValueOnce(new ApiError(400, "mfa_invalid", "bad", null));
    const { unmount } = render(<MfaPage />); await screen.findByLabelText("Mã xác minh");
    fireEvent.change(screen.getByLabelText("Mã xác minh"), { target: { value: "123456" } });
    fireEvent.submit(screen.getByLabelText("Mã xác minh").closest("form")!);
    await screen.findByText("Mã không đúng hoặc đã dùng");
    fireEvent.click(screen.getByRole("button", { name: "Dùng mã khôi phục" }));
    expect(screen.queryByText("Mã không đúng hoặc đã dùng")).toBeNull();
    expect((screen.getByLabelText("Mã khôi phục") as HTMLInputElement).value).toBe("");
    unmount();
  });

  it.each(["status", "setup", "enable", "verify"])("điều hướng xác thực cho phiên hết hạn ở %s", async (operation) => {
    if (operation === "status") mocks.status.mockRejectedValueOnce(new ApiError(401, "session_expired", "expired", null));
    else mocks.status.mockResolvedValue({ enabled: operation === "verify", pending: false, verified: false });
    if (operation === "setup") mocks.setup.mockRejectedValueOnce(new ApiError(401, "unauthorized", "expired", null));
    if (operation === "enable") mocks.enable.mockRejectedValueOnce(new ApiError(401, "unauthorized", "expired", null));
    if (operation === "verify") mocks.verify.mockRejectedValueOnce(new ApiError(401, "unauthorized", "expired", null));
    render(<MfaPage />);
    if (operation !== "status") {
      if (operation === "setup") fireEvent.click(await screen.findByRole("button", { name: "Thiết lập" }));
      if (operation === "enable") {
        mocks.setup.mockResolvedValue({ secret: "s", otpauth_uri: "uri" });
        fireEvent.click(await screen.findByRole("button", { name: "Thiết lập" })); await screen.findByText("s");
        fireEvent.change(screen.getByLabelText("Mã xác minh"), { target: { value: "123456" } }); fireEvent.submit(screen.getByLabelText("Mã xác minh").closest("form")!);
      }
      if (operation === "verify") {
        fireEvent.change(await screen.findByLabelText("Mã xác minh"), { target: { value: "123456" } }); fireEvent.submit(screen.getByLabelText("Mã xác minh").closest("form")!);
      }
    }
    await waitFor(() => expect(mocks.router.replace).toHaveBeenCalledWith("/login"));
  });

  it.each(["status", "setup", "enable", "verify"])("điều hướng MFA required về trang MFA ở %s", async (operation) => {
    const required = () => Promise.reject(new ApiError(403, "mfa_required", "MFA required", null));
    if (operation === "status") mocks.status.mockImplementationOnce(required);
    else mocks.status.mockResolvedValue({ enabled: operation === "verify", pending: false, verified: false });
    if (operation === "setup") mocks.setup.mockImplementationOnce(required);
    if (operation === "enable") {
      mocks.setup.mockResolvedValue({ secret: "s", otpauth_uri: "uri" });
      mocks.enable.mockImplementationOnce(required);
    }
    if (operation === "verify") mocks.verify.mockImplementationOnce(required);
    render(<MfaPage />);
    if (operation === "setup") fireEvent.click(await screen.findByRole("button", { name: "Thiết lập" }));
    if (operation === "enable") {
      fireEvent.click(await screen.findByRole("button", { name: "Thiết lập" })); await screen.findByText("s");
      fireEvent.change(screen.getByLabelText("Mã xác minh"), { target: { value: "123456" } }); fireEvent.submit(screen.getByLabelText("Mã xác minh").closest("form")!);
    }
    if (operation === "verify") {
      fireEvent.change(await screen.findByLabelText("Mã xác minh"), { target: { value: "123456" } }); fireEvent.submit(screen.getByLabelText("Mã xác minh").closest("form")!);
    }
    await waitFor(() => expect(mocks.router.replace).toHaveBeenCalledWith("/admin/mfa"));
  });
});
