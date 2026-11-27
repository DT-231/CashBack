// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, replace }) }));
vi.mock("@/lib/api-client", () => ({ ApiError: class ApiError extends Error { constructor(public status: number, public code: string, message: string) { super(message); } get isAuth() { return this.status === 401 && ["session_expired", "unauthorized"].includes(this.code); } }, api: { register: vi.fn(), login: vi.fn(), resendVerification: vi.fn() } }));
import { api } from "@/lib/api-client";
import { AuthForm } from "./AuthForms";

beforeEach(() => { vi.clearAllMocks(); });
afterEach(cleanup);

describe("AuthForm", () => {
  it("đăng ký rồi đăng nhập trước khi chuyển trang", async () => {
    vi.mocked(api.register).mockResolvedValue({ id: 1, email: "a@b.com", role: "member", status: "active" });
    vi.mocked(api.login).mockResolvedValue({ ok: true });
    render(<AuthForm mode="register" />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.com" } });
    fireEvent.change(screen.getByLabelText("Mật khẩu"), { target: { value: "0123456789" } });
    fireEvent.click(screen.getByRole("button", { name: "Đăng ký" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/links"));
    expect(api.register).toHaveBeenCalledWith("a@b.com", "0123456789");
    expect(api.login).toHaveBeenCalledWith("a@b.com", "0123456789");
    expect(vi.mocked(api.register).mock.invocationCallOrder[0]).toBeLessThan(vi.mocked(api.login).mock.invocationCallOrder[0]);
  });

  it("báo mật khẩu ngắn trước khi gọi API", () => {
    render(<AuthForm mode="register" />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.com" } });
    fireEvent.change(screen.getByLabelText("Mật khẩu"), { target: { value: "short" } });
    fireEvent.click(screen.getByRole("button", { name: "Đăng ký" }));
    expect(screen.getByRole("alert").textContent).toContain("ít nhất 10 ký tự");
    expect(api.register).not.toHaveBeenCalled();
  });

  it("dùng thông báo chung khi thông tin đăng nhập sai", async () => {
    vi.mocked(api.login).mockRejectedValue(new (await import("@/lib/api-client")).ApiError(401, "invalid_credentials", "Sai", null));
    render(<AuthForm mode="login" />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.com" } });
    fireEvent.change(screen.getByLabelText("Mật khẩu"), { target: { value: "anything" } });
    fireEvent.click(screen.getByRole("button", { name: "Đăng nhập" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Email hoặc mật khẩu không đúng");
  });

  it("chỉ gửi một lần khi bấm đăng nhập liên tiếp lúc API đang chờ", async () => {
    let resolve!: (value: { ok: true }) => void;
    vi.mocked(api.login).mockReturnValue(new Promise((r) => { resolve = r; }));
    render(<AuthForm mode="login" />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.com" } });
    fireEvent.change(screen.getByLabelText("Mật khẩu"), { target: { value: "password" } });
    const button = screen.getByRole("button", { name: "Đăng nhập" });
    fireEvent.click(button); fireEvent.click(button);
    expect(api.login).toHaveBeenCalledTimes(1);
    expect(button).toHaveProperty("disabled", true);
    resolve({ ok: true });
    await waitFor(() => expect(push).toHaveBeenCalledWith("/links"));
  });

  it("chỉ gửi đăng ký một lần khi bấm liên tiếp lúc API đang chờ", async () => {
    let resolve!: (value: { id: number; email: string; role: "member"; status: string }) => void;
    vi.mocked(api.register).mockReturnValue(new Promise((r) => { resolve = r; }));
    render(<AuthForm mode="register" />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.com" } });
    fireEvent.change(screen.getByLabelText("Mật khẩu"), { target: { value: "0123456789" } });
    const button = screen.getByRole("button", { name: "Đăng ký" });
    fireEvent.click(button); fireEvent.click(button);
    expect(api.register).toHaveBeenCalledTimes(1);
    expect(button).toHaveProperty("disabled", true);
    resolve({ id: 1, email: "a@b.com", role: "member", status: "active" });
    vi.mocked(api.login).mockResolvedValue({ ok: true });
    await waitFor(() => expect(push).toHaveBeenCalledWith("/links"));
  });

  it("chuyển sang đăng nhập nếu tạo tài khoản xong nhưng đăng nhập lỗi", async () => {
    vi.mocked(api.register).mockResolvedValue({ id: 1, email: "a@b.com", role: "member", status: "active" });
    vi.mocked(api.login).mockRejectedValue(new Error("failed"));
    render(<AuthForm mode="register" />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.com" } });
    fireEvent.change(screen.getByLabelText("Mật khẩu"), { target: { value: "0123456789" } });
    fireEvent.click(screen.getByRole("button", { name: "Đăng ký" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Tài khoản đã được tạo, vui lòng đăng nhập");
    expect(replace).toHaveBeenCalledWith("/login");
  });

  it("hiện thông báo giới hạn tốc độ", async () => {
    const { ApiError: MockApiError } = await import("@/lib/api-client");
    vi.mocked(api.login).mockRejectedValue(new MockApiError(429, "rate_limited", "slow down", null));
    render(<AuthForm mode="login" />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.com" } });
    fireEvent.change(screen.getByLabelText("Mật khẩu"), { target: { value: "password" } });
    fireEvent.click(screen.getByRole("button", { name: "Đăng nhập" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Bạn thử quá nhiều lần, vui lòng đợi một lát");
  });

  it("liên kết quên mật khẩu và gửi lại xác minh cho email đăng nhập", async () => {
    vi.mocked(api.login).mockRejectedValue(new (await import("@/lib/api-client")).ApiError(403, "email_unverified", "unverified", null));
    vi.mocked(api.resendVerification).mockResolvedValue({ ok: true });
    render(<AuthForm mode="login" />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.com" } });
    fireEvent.change(screen.getByLabelText("Mật khẩu"), { target: { value: "password" } });
    expect(screen.getByRole("link", { name: "Quên mật khẩu?" }).getAttribute("href")).toBe("/forgot-password");
    fireEvent.click(screen.getByRole("button", { name: "Đăng nhập" }));
    fireEvent.click(await screen.findByRole("button", { name: "Gửi lại email xác minh" }));
    expect(api.resendVerification).toHaveBeenCalledWith("a@b.com");
    expect(await screen.findByText("Nếu tài khoản cần xác minh, chúng tôi đã gửi email mới.")).toBeTruthy();
  });
});
