// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const replace = vi.fn();
const router = { replace };
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/lib/api-client", () => ({ ApiError: class ApiError extends Error { constructor(public status: number, public code: string, message: string) { super(message); } get isAuth() { return this.status === 401; } }, api: { wallet: vi.fn(), walletEntries: vi.fn() } }));
import { api } from "@/lib/api-client";
import WalletPage from "./WalletPage";

const wallet = { pending_vnd: 24225, available_vnd: 70000, held_vnd: 5000, share_pct: 60 };
const entry = (id: number) => ({ id, kind: "accrual", state: "pending", amount_vnd: 24225, order_id: 12, withdrawal_id: null, created_at: "2026-12-01T03:04:00Z" });

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.wallet).mockResolvedValue(wallet);
  vi.mocked(api.walletEntries).mockResolvedValue([entry(1)]);
});
afterEach(cleanup);

describe("WalletPage", () => {
  it("hiển thị ba số dư, tỷ lệ và nhãn lịch sử từ API", async () => {
    render(<WalletPage />);
    expect(await screen.findByText("24.225 ₫")).toBeTruthy();
    expect(screen.getByText("70.000 ₫")).toBeTruthy();
    expect(screen.getByText("5.000 ₫")).toBeTruthy();
    expect(screen.getByText("Tỷ lệ hoàn hiện tại: 60%")).toBeTruthy();
    expect(screen.getByText("Đơn cũ giữ tỷ lệ tại thời điểm phát sinh.")).toBeTruthy();
    expect(screen.getByText("Hoàn tiền")).toBeTruthy();
    expect(screen.getByText("Trạng thái: Chờ xác nhận")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Rút tiền · Sắp có" })).toHaveProperty("disabled", true);
  });

  it("tải lịch sử tiếp theo bằng offset và ẩn nút khi trang sau ngắn hơn 50", async () => {
    vi.mocked(api.walletEntries).mockResolvedValueOnce(Array.from({ length: 50 }, (_, index) => entry(index))).mockResolvedValueOnce([entry(50)]);
    render(<WalletPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Xem thêm" }));
    await waitFor(() => expect(api.walletEntries).toHaveBeenLastCalledWith({ limit: 50, offset: 50 }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Xem thêm" })).toBeNull());
  });

  it("ẩn phân trang khi trang đầu chưa đủ 50 giao dịch", async () => {
    vi.mocked(api.walletEntries).mockResolvedValue([entry(1)]);
    render(<WalletPage />);
    await screen.findByText("Hoàn tiền");
    expect(screen.queryByRole("button", { name: "Xem thêm" })).toBeNull();
  });
});
