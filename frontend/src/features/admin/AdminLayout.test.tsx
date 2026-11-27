// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AdminLayout from "./AdminLayout";
import { ApiError } from "@/lib/api-client";

const mocks = vi.hoisted(() => ({ replace: vi.fn(), router: { replace: vi.fn() }, me: vi.fn(), logout: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => mocks.router }));
vi.mock("@/lib/api-client", () => ({ ApiError: class ApiError extends Error { status: number; code: string; constructor(status: number, code: string) { super(code); this.status = status; this.code = code; } get isAuth() { return this.status === 401; } }, api: { me: mocks.me, logout: mocks.logout } }));

describe("AdminLayout", () => {
  beforeEach(() => { vi.clearAllMocks(); });
  afterEach(cleanup);
  it("chặn role khác admin và không gọi API admin", async () => {
    mocks.me.mockResolvedValue({ role: "staff" });
    render(<AdminLayout><p>Nội dung admin</p></AdminLayout>);
    expect(await screen.findByText("Bạn không có quyền truy cập")).toBeTruthy();
    expect(screen.queryByText("Nội dung admin")).toBeNull();
  });
  it("chuyển phiên hết hạn tới đăng nhập", async () => {
    mocks.me.mockRejectedValue(new ApiError(401, "session_expired", "expired", null));
    render(<AdminLayout><p>Nội dung admin</p></AdminLayout>);
    await waitFor(() => expect(mocks.router.replace).toHaveBeenCalledWith("/login"));
  });
  it("hiện nav và đăng xuất", async () => {
    mocks.me.mockResolvedValue({ role: "admin" }); mocks.logout.mockResolvedValue(undefined);
    render(<AdminLayout><p>Nội dung admin</p></AdminLayout>);
    expect(await screen.findByText("Nội dung admin")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Rút tiền" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Đăng xuất" }));
    await waitFor(() => expect(mocks.router.replace).toHaveBeenCalledWith("/login"));
  });
});
