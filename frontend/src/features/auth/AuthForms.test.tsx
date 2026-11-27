// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/lib/api-client", () => ({ ApiError: class ApiError extends Error { constructor(public status: number, public code: string, message: string) { super(message); } }, api: { register: vi.fn(), login: vi.fn() } }));
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
});
