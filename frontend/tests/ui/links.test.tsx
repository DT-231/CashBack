// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api-client", () => ({ ApiError: class ApiError extends Error { constructor(public status: number, public code: string, message: string, public requestId: string | null = null) { super(message); } get isAuth() { return this.status === 401 && (this.code === "session_expired" || this.code === "unauthorized"); } }, api: { myLinks: vi.fn(), createLink: vi.fn() } }));
const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));
import { api } from "@/lib/api-client";
import LinksPage from "../../src/app/(member)/links/page";

const link = (code: string) => ({ code, go_url: `https://example.com/${code}`, product: { shop_id: 1, item_id: 2, name: "Bàn" }, created_at: "2026-01-02T03:04:00Z", clicks: 7 });
beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.myLinks).mockResolvedValue([]); Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: vi.fn().mockResolvedValue(undefined) } }); });
afterEach(cleanup);

describe("LinksPage", () => {
  it("phân trang từ offset 50 khi trang đầu đủ 50 link", async () => {
    vi.mocked(api.myLinks).mockResolvedValueOnce(Array.from({ length: 50 }, (_, i) => link(String(i)))).mockResolvedValueOnce(Array.from({ length: 20 }, (_, i) => link(String(50 + i))));
    render(<LinksPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Xem thêm" }));
    await waitFor(() => expect(api.myLinks).toHaveBeenLastCalledWith({ limit: 50, offset: 50 }));
    expect(screen.getAllByText("Số click: 7")).toHaveLength(70);
    await waitFor(() => expect(screen.queryByRole("button", { name: "Xem thêm" })).toBeNull());
  });

  it("hiện link dự phòng khi go_url chưa sẵn sàng", async () => {
    vi.mocked(api.createLink).mockResolvedValue({ code: "x", go_url: null, direct_url: "https://shopee.vn/item", product: { shop_id: 1, item_id: 2, name: null } });
    render(<LinksPage />);
    fireEvent.change(screen.getByLabelText("Link sản phẩm Shopee"), { target: { value: "https://shopee.vn/item" } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo link" }));
    expect(await screen.findByText("Link chuyển hướng chưa sẵn sàng")).toBeTruthy();
    expect(screen.getByText("https://shopee.vn/item")).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: "Sao chép" })[0]);
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith("https://shopee.vn/item"));
    expect(await screen.findByRole("button", { name: "Đã sao chép" })).toBeTruthy();
  });

  it("sao chép cả go_url và direct_url trong kết quả tạo link", async () => {
    vi.mocked(api.createLink).mockResolvedValue({ code: "x", go_url: "https://example.com/go/x", direct_url: "https://shopee.vn/item", product: { shop_id: 1, item_id: 2, name: "Bàn" } });
    render(<LinksPage />);
    fireEvent.change(screen.getByLabelText("Link sản phẩm Shopee"), { target: { value: "https://shopee.vn/item" } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo link" }));
    const copyButtons = await screen.findAllByRole("button", { name: "Sao chép" });
    fireEvent.click(copyButtons[0]);
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith("https://example.com/go/x"));
    fireEvent.click(screen.getByRole("button", { name: "Sao chép" }));
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith("https://shopee.vn/item"));
  });

  it("ẩn xem thêm nếu trang đầu có ít hơn 50 link", async () => {
    vi.mocked(api.myLinks).mockResolvedValue(Array.from({ length: 49 }, (_, i) => link(String(i))));
    render(<LinksPage />);
    await waitFor(() => expect(screen.getAllByText("Số click: 7")).toHaveLength(49));
    expect(screen.queryByRole("button", { name: "Xem thêm" })).toBeNull();
  });

  it("chống gửi lặp, giữ input và danh sách nếu API trả lỗi 400", async () => {
    const { ApiError: MockApiError } = await import("@/lib/api-client");
    let reject!: (error: Error) => void;
    vi.mocked(api.createLink).mockReturnValue(new Promise((_, r) => { reject = r; }));
    render(<LinksPage />);
    const input = screen.getByLabelText("Link sản phẩm Shopee");
    fireEvent.change(input, { target: { value: "https://shopee.vn/short" } });
    const button = screen.getByRole("button", { name: "Tạo link" });
    fireEvent.click(button); fireEvent.click(button);
    expect(api.createLink).toHaveBeenCalledTimes(1);
    expect(button).toHaveProperty("disabled", true);
    reject(new MockApiError(400, "invalid_input", "chưa hỗ trợ link rút gọn", null));
    expect((await screen.findByRole("alert")).textContent).toBe("chưa hỗ trợ link rút gọn");
    expect(input).toHaveProperty("value", "https://shopee.vn/short");
    expect(api.myLinks).toHaveBeenCalledTimes(1);
  });

  it("làm mới danh sách sau khi tạo link", async () => {
    vi.mocked(api.createLink).mockResolvedValue({ code: "new", go_url: "https://example.com/new", direct_url: "https://shopee.vn/new", product: { shop_id: 1, item_id: 2, name: "Mới" } });
    vi.mocked(api.myLinks).mockResolvedValueOnce([]).mockResolvedValueOnce([link("new")]);
    render(<LinksPage />);
    fireEvent.change(screen.getByLabelText("Link sản phẩm Shopee"), { target: { value: "https://shopee.vn/new" } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo link" }));
    expect(await screen.findByText("Số click: 7")).toBeTruthy();
    expect(api.myLinks).toHaveBeenCalledTimes(2);
  });

  it("sao chép go_url của link trong danh sách", async () => {
    vi.mocked(api.myLinks).mockResolvedValue([link("copy-me")]);
    render(<LinksPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Sao chép" }));
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith("https://example.com/copy-me"));
    expect(await screen.findByRole("button", { name: "Đã sao chép" })).toBeTruthy();
  });

  it("hiện trạng thái rỗng và lỗi mạng", async () => {
    render(<LinksPage />);
    expect(await screen.findByText("Bạn chưa tạo link nào")).toBeTruthy();
    vi.mocked(api.createLink).mockRejectedValue(new (await import("@/lib/api-client")).ApiError(0, "network", "offline", null));
    fireEvent.change(screen.getByLabelText("Link sản phẩm Shopee"), { target: { value: "https://shopee.vn/item" } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo link" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Không kết nối được máy chủ");
  });

  it("chuyển đăng nhập khi phiên hết hạn trong trang link", async () => {
    vi.mocked(api.myLinks).mockRejectedValue(new (await import("@/lib/api-client")).ApiError(401, "session_expired", "expired", null));
    render(<LinksPage />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });
});
