// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const replace = vi.fn();
const router = { replace };
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/lib/api-client", () => ({ ApiError: class ApiError extends Error { constructor(public status: number, public code: string, message: string) { super(message); } get isAuth() { return this.status === 401; } }, api: { myOrders: vi.fn() } }));
import { api } from "@/lib/api-client";
import OrdersPage from "./OrdersPage";

const order = (id: number) => ({ id, order_ref: "1234", status: "PENDING" as const, product_name: "Bàn gỗ", purchased_at: "2026-12-01T03:04:00Z", refund_vnd: 24225, refund_state: "pending" as const, expected_release_at: "2026-12-08T03:04:00Z" });

beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.myOrders).mockResolvedValue([order(1)]); });
afterEach(cleanup);

describe("OrdersPage", () => {
  it("hiển thị đơn theo API, gồm mốc mở khóa do backend trả về", async () => {
    render(<OrdersPage />);
    expect(await screen.findByText("Đơn hàng …1234")).toBeTruthy();
    expect(screen.getByText("Trạng thái đơn: Đang chờ")).toBeTruthy();
    expect(screen.getByText("Sản phẩm: Bàn gỗ")).toBeTruthy();
    expect(screen.getByText("Hoàn tiền: 24.225 ₫ · Chờ xác nhận")).toBeTruthy();
    expect(screen.getByText(/Dự kiến mở khóa: 10:04 08\/12\/2026/)).toBeTruthy();
  });

  it("tải đơn tiếp theo bằng offset và ẩn nút khi trang sau ngắn hơn 50", async () => {
    vi.mocked(api.myOrders).mockResolvedValueOnce(Array.from({ length: 50 }, (_, index) => order(index))).mockResolvedValueOnce([order(50)]);
    render(<OrdersPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Xem thêm" }));
    await waitFor(() => expect(api.myOrders).toHaveBeenLastCalledWith({ limit: 50, offset: 50 }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Xem thêm" })).toBeNull());
  });

  it("ẩn phân trang khi trang đầu chưa đủ 50 đơn", async () => {
    render(<OrdersPage />);
    await screen.findByText("Đơn hàng …1234");
    expect(screen.queryByRole("button", { name: "Xem thêm" })).toBeNull();
  });
});
