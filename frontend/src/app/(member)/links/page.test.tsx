// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api-client", () => ({ ApiError: class ApiError extends Error { constructor(public status: number, public code: string, message: string) { super(message); } }, api: { myLinks: vi.fn(), createLink: vi.fn() } }));
import { api } from "@/lib/api-client";
import LinksPage from "./page";

const link = (code: string) => ({ code, go_url: `https://example.com/${code}`, product: { shop_id: 1, item_id: 2, name: "Bàn" }, created_at: "2026-01-02T03:04:00Z", clicks: 7 });
beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.myLinks).mockResolvedValue([]); });
afterEach(cleanup);

describe("LinksPage", () => {
  it("phân trang từ offset 50 khi trang đầu đủ 50 link", async () => {
    vi.mocked(api.myLinks).mockResolvedValueOnce(Array.from({ length: 50 }, (_, i) => link(String(i)))).mockResolvedValueOnce([link("50")]);
    render(<LinksPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Xem thêm" }));
    await waitFor(() => expect(api.myLinks).toHaveBeenLastCalledWith({ limit: 50, offset: 50 }));
    expect(screen.getAllByText("Số click: 7")).toHaveLength(51);
  });

  it("hiện link dự phòng khi go_url chưa sẵn sàng", async () => {
    vi.mocked(api.createLink).mockResolvedValue({ code: "x", go_url: null, direct_url: "https://shopee.vn/item", product: { shop_id: 1, item_id: 2, name: null } });
    render(<LinksPage />);
    fireEvent.change(screen.getByLabelText("Link sản phẩm Shopee"), { target: { value: "https://shopee.vn/item" } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo link" }));
    expect(await screen.findByText("Link chuyển hướng chưa sẵn sàng")).toBeTruthy();
    expect(screen.getByText("https://shopee.vn/item")).toBeTruthy();
  });
});
