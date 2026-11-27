// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));
vi.mock("@/lib/api-client", () => ({
  ApiError: class ApiError extends Error {
    constructor(public status: number, public code: string, message: string) { super(message); }
    get isAuth() { return this.status === 401 && (this.code === "session_expired" || this.code === "unauthorized"); }
  },
  api: { me: vi.fn(), logout: vi.fn() },
}));
import { ApiError, api } from "@/lib/api-client";
import MemberLayout from "../../src/app/(member)/layout";

beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.me).mockResolvedValue({ id: 1, email: "a@b.com", role: "member", status: "active" }); vi.mocked(api.logout).mockResolvedValue(undefined); });
afterEach(cleanup);

describe("MemberLayout", () => {
  it("chuyển về đăng nhập và không hiện nội dung khi phiên hết hạn", async () => {
    vi.mocked(api.me).mockRejectedValue(new ApiError(401, "session_expired", "expired", null));
    render(<MemberLayout><p>Nội dung thành viên</p></MemberLayout>);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByText("Nội dung thành viên")).toBeNull();
  });

  it("gọi đăng xuất rồi chuyển trang kể cả khi API lỗi", async () => {
    vi.mocked(api.logout).mockRejectedValue(new Error("expired"));
    render(<MemberLayout><p>Nội dung thành viên</p></MemberLayout>);
    fireEvent.click(await screen.findByRole("button", { name: "Đăng xuất" }));
    await waitFor(() => expect(api.logout).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });
});
