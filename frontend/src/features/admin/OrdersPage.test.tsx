// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import OrdersPage from "./OrdersPage";

const { adminOrders, replace, router } = vi.hoisted(() => { const replace = vi.fn(); return { adminOrders: vi.fn(), replace, router: { replace } }; });
vi.mock("@/lib/api-client", () => ({ ApiError: class ApiError extends Error { constructor(public status: number, public code: string, message: string, public requestId: string | null = null) { super(message); } get isAuth() { return this.status === 401 && ["session_expired", "unauthorized"].includes(this.code); } get isMfaRequired() { return this.status === 403 && this.code === "mfa_required"; } }, api: { adminOrders } }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
const order = (id: number, status = "PENDING", source_type = "user") => ({ id, order_sn: `order-${id}`, status, source_type, user_id: null, post_id: null, commission_micro: 123456, commission_vnd: 1234, purchase_time: null, completed_at: null });
describe("OrdersPage", () => {
  beforeEach(() => { adminOrders.mockReset(); replace.mockReset(); adminOrders.mockResolvedValue([order(1)]); }); afterEach(cleanup);
  it("passes selected filters to first and next pages and appends results", async () => {
    adminOrders.mockResolvedValueOnce([order(1)]).mockResolvedValueOnce(Array.from({ length: 50 }, (_, i) => order(i + 1))).mockResolvedValueOnce(Array.from({ length: 50 }, (_, i) => order(i + 1))).mockResolvedValueOnce([order(51)]); render(<OrdersPage />); await screen.findByText(/^#1 · order-1$/);
    fireEvent.change(screen.getByLabelText("Lọc trạng thái"), { target: { value: "COMPLETED" } }); await waitFor(() => expect(adminOrders).toHaveBeenLastCalledWith({ status: "COMPLETED", limit: 50, offset: 0 }));
    fireEvent.change(screen.getByLabelText("Lọc nguồn"), { target: { value: "post" } }); await waitFor(() => expect(adminOrders).toHaveBeenLastCalledWith({ status: "COMPLETED", source: "post", limit: 50, offset: 0 }));
    fireEvent.click(await screen.findByRole("button", { name: "Xem thêm" })); await screen.findByText(/^#51 · order-51$/); expect(adminOrders).toHaveBeenLastCalledWith({ status: "COMPLETED", source: "post", limit: 50, offset: 50 }); expect(screen.getByText(/^#1 · order-1$/)).toBeTruthy();
  });
  it("renders known status/source labels, null fields safely, and VND values", async () => {
    adminOrders.mockResolvedValue([order(1), order(2, "COMPLETED", "post"), order(3, "CANCELLED", "legacy"), order(4, "RETURNED", "unknown"), order(5, "FUTURE", "mystery")]); render(<OrdersPage />);
    await screen.findByText(/^#1 · order-1$/); for (const label of ["Đang chờ", "Hoàn thành", "Đã hủy", "Đã hoàn trả", "Người dùng", "Bài đăng", "Cũ", "Không rõ"]) expect(screen.getAllByText(new RegExp(label)).length).toBeGreaterThan(0);
    const rowText = [...document.querySelectorAll("li")].map((item) => item.textContent ?? "");
    for (const expected of ["Trạng thái: Đang chờ", "Trạng thái: Hoàn thành", "Trạng thái: Đã hủy", "Trạng thái: Đã hoàn trả", "Nguồn: Người dùng", "Nguồn: Bài đăng", "Nguồn: Cũ", "Nguồn: Không rõ"]) expect(rowText.some((row) => row.includes(expected))).toBe(true);
    const paragraphs = [...document.querySelectorAll("li p")].map((item) => item.textContent); expect(paragraphs).toContain("Trạng thái: FUTURE"); expect(paragraphs).toContain("Nguồn: mystery"); expect(paragraphs.filter((value) => value === "Người dùng: —")).toHaveLength(5); expect(paragraphs.filter((value) => value === "Hoa hồng: 1.234 ₫")).toHaveLength(5); expect(document.body.textContent).not.toContain("123456"); expect(screen.queryByText(/Ngày mua:/)).toBeNull(); expect(screen.queryByText(/Ngày hoàn tất:/)).toBeNull();
  });
  it("hides pagination when the first page has fewer than 50 orders", async () => {
    adminOrders.mockResolvedValue([order(1), order(2)]);
    render(<OrdersPage />);
    await screen.findByText(/^#1 · order-1$/);
    expect(screen.queryByRole("button", { name: "Xem thêm" })).toBeNull();
  });
  it("shows empty state and redirects auth/MFA while displaying network errors", async () => {
    adminOrders.mockResolvedValueOnce([]); render(<OrdersPage />); expect(await screen.findByText("Không có đơn hàng.")).toBeTruthy();
    const ApiError = (await import("@/lib/api-client")).ApiError; cleanup(); adminOrders.mockRejectedValueOnce(new ApiError(401, "session_expired", "expired", null)); render(<OrdersPage />); await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    cleanup(); replace.mockClear(); adminOrders.mockRejectedValueOnce(new ApiError(403, "mfa_required", "mfa", null)); render(<OrdersPage />); await waitFor(() => expect(replace).toHaveBeenCalledWith("/admin/mfa"));
    cleanup(); adminOrders.mockRejectedValueOnce(new ApiError(0, "network", "network", null)); render(<OrdersPage />); expect((await screen.findByRole("alert")).textContent).toContain("Không kết nối được máy chủ");
  });
});
