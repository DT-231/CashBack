// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const replace = vi.fn();
const router = { replace };
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/lib/api-client", () => ({ ApiError: class ApiError extends Error { constructor(public status: number, public code: string, message: string) { super(message); } get isAuth() { return this.status === 401; } }, api: { myOrders: vi.fn() } }));
import { ApiError, api } from "@/lib/api-client";
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
    await screen.findAllByRole("heading", { name: "Đơn hàng …1234" });
    expect(screen.getAllByRole("heading", { name: "Đơn hàng …1234" })).toHaveLength(51);
    await waitFor(() => expect(screen.queryByRole("button", { name: "Xem thêm" })).toBeNull());
  });

  it("chuyển tới đăng nhập khi phiên hết lúc tải lần đầu hoặc lần trang sau", async () => {
    vi.mocked(api.myOrders).mockRejectedValueOnce(new ApiError(401, "session_expired", "expired", "request-id"));
    render(<OrdersPage />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));

    cleanup();
    vi.clearAllMocks();
    vi.mocked(api.myOrders).mockResolvedValueOnce(Array.from({ length: 50 }, (_, index) => order(index)))
      .mockRejectedValueOnce(new ApiError(401, "session_expired", "expired", "request-id"));
    render(<OrdersPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Xem thêm" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByText("Không thể tải đơn hàng. Vui lòng thử lại.")).toBeNull();
  });

  it("ẩn mốc mở khóa khi null và định dạng đúng giá trị do API trả về", async () => {
    vi.mocked(api.myOrders).mockResolvedValueOnce([
      { ...order(1), expected_release_at: null },
      { ...order(2), expected_release_at: "2027-01-02T12:34:00Z" },
    ]);
    render(<OrdersPage />);
    expect(await screen.findByText(/Dự kiến mở khóa: 19:34 02\/01\/2027/)).toBeTruthy();
    expect(screen.getAllByText(/Dự kiến mở khóa:/)).toHaveLength(1);
  });

  it("dịch đủ trạng thái đơn và hoàn tiền", async () => {
    const statuses = ["PENDING", "COMPLETED", "CANCELLED", "RETURNED"] as const;
    const refunds = ["none", "pending", "available", "cancelled", "reversed"] as const;
    vi.mocked(api.myOrders).mockResolvedValueOnce(refunds.map((refund_state, index) => ({
      ...order(index), status: statuses[index % statuses.length], refund_state,
    })));
    render(<OrdersPage />);
    for (const label of ["Đang chờ", "Hoàn thành", "Đã hủy", "Đã hoàn trả"]) {
      expect((await screen.findAllByText(`Trạng thái đơn: ${label}`)).length).toBeGreaterThan(0);
    }
    const paragraphs = [...document.querySelectorAll("li p")].map((paragraph) => paragraph.textContent ?? "");
    for (const label of ["Chưa có hoàn tiền", "Chờ xác nhận", "Rút được", "Đã hủy", "Đã thu hồi"]) {
      expect(paragraphs.some((paragraph) => paragraph.includes(` · ${label}`))).toBe(true);
    }
    for (const raw of [...statuses, ...refunds]) {
      expect(screen.queryByText(`Trạng thái đơn: ${raw}`)).toBeNull();
      expect(screen.queryByText(new RegExp(` · ${raw}$`))).toBeNull();
    }
  });

  it("hiện danh sách rỗng và bỏ dòng sản phẩm khi product_name null", async () => {
    vi.mocked(api.myOrders).mockResolvedValueOnce([]);
    const { unmount } = render(<OrdersPage />);
    expect(await screen.findByText("Bạn chưa có đơn hàng nào.")).toBeTruthy();
    unmount();

    vi.mocked(api.myOrders).mockResolvedValueOnce([{ ...order(2), product_name: null }]);
    render(<OrdersPage />);
    await screen.findByText("Đơn hàng …1234");
    expect(screen.queryByText(/^Sản phẩm:/)).toBeNull();
  });

  it("ẩn phân trang khi trang đầu chưa đủ 50 đơn", async () => {
    render(<OrdersPage />);
    await screen.findByText("Đơn hàng …1234");
    expect(screen.queryByRole("button", { name: "Xem thêm" })).toBeNull();
  });
});
