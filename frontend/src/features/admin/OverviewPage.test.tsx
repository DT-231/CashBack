// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import OverviewPage from "./OverviewPage";

const { adminOverview, replace, router } = vi.hoisted(() => { const replace = vi.fn(); return { adminOverview: vi.fn(), replace, router: { replace } }; });
vi.mock("@/lib/api-client", () => ({ ApiError: class ApiError extends Error { constructor(public status: number, public code: string, message: string, public requestId: string | null = null) { super(message); } get isAuth() { return this.status === 401 && ["session_expired", "unauthorized"].includes(this.code); } get isMfaRequired() { return this.status === 403 && this.code === "mfa_required"; } }, api: { adminOverview } }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
const overview = (last_sync: unknown = null) => ({ days: 30, users: { total: 4, new: 2, locked: 1 }, clicks: 8, links: 7, orders: { PENDING: { count: 1, commission_micro: 990000, commission_vnd: 9 }, COMPLETED: { count: 2, commission_micro: 880000, commission_vnd: 8 }, ODD: { count: 1, commission_micro: 0, commission_vnd: 0 } }, orphans_open: 3, wallet_totals_vnd: { pending: 1000, available: 2000, held: 3000 }, withdrawals: { requested: { count: 1, amount_vnd: 100 }, approved: { count: 2, amount_vnd: 200 }, rejected: { count: 3, amount_vnd: 300 }, processing: { count: 4, amount_vnd: 400 }, paid: { count: 5, amount_vnd: 500 }, failed: { count: 6, amount_vnd: 600 }, mystery: { count: 1, amount_vnd: 700 } }, last_sync });

describe("OverviewPage", () => {
  beforeEach(() => { adminOverview.mockReset(); replace.mockReset(); adminOverview.mockResolvedValue(overview()); });
  afterEach(cleanup);
  it("requests selected days and renders all order and withdrawal statuses without exposing micro money", async () => {
    render(<OverviewPage />);
    await screen.findByText("Chưa từng đồng bộ");
    expect(adminOverview).toHaveBeenCalledWith(30);
    fireEvent.change(screen.getByLabelText("Khoảng ngày"), { target: { value: "90" } });
    await waitFor(() => expect(adminOverview).toHaveBeenLastCalledWith(90));
    for (const label of ["Đang chờ", "Hoàn thành", "Đã hủy", "Đã hoàn trả", "Đang chờ duyệt", "Đã duyệt", "Bị từ chối", "Đang xử lý", "Đã chi trả", "Chuyển khoản lỗi"]) expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    expect(screen.getByText("ODD")).toBeTruthy(); expect(screen.getByText("mystery")).toBeTruthy();
    expect(screen.getAllByText("Số đơn: 0")).toHaveLength(2);
    expect(screen.getByText("Chờ xác nhận: 1.000 ₫")).toBeTruthy();
    expect(screen.getByText("Rút được: 2.000 ₫")).toBeTruthy();
    expect(screen.getByText("Đang khóa: 3.000 ₫")).toBeTruthy();
    expect(document.body.textContent).not.toContain("commission_micro"); expect(document.body.textContent).not.toContain("990000");
    expect(screen.getByRole("link", { name: "Xem đơn mồ côi" }).getAttribute("href")).toBe("/admin/orphans");
  });
  it.each([["ok", "Thành công"], ["partial", "Một phần"], ["failed", "Thất bại"], ["unmapped", "unmapped"]])("shows sync result %s", async (result, label) => {
    adminOverview.mockResolvedValue(overview({ result, finished_at: "2026-11-27T10:00:00Z" })); render(<OverviewPage />); expect(await screen.findByText(new RegExp(label))).toBeTruthy();
  });
  it("redirects for auth and MFA failures and reports network failure", async () => {
    const ApiError = (await import("@/lib/api-client")).ApiError;
    adminOverview.mockRejectedValueOnce(new ApiError(401, "session_expired", "expired", null)); render(<OverviewPage />); await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    cleanup(); replace.mockClear(); adminOverview.mockRejectedValueOnce(new ApiError(403, "mfa_required", "mfa", null)); render(<OverviewPage />); await waitFor(() => expect(replace).toHaveBeenCalledWith("/admin/mfa"));
    cleanup(); adminOverview.mockRejectedValueOnce(new ApiError(0, "network", "network", null)); render(<OverviewPage />); expect((await screen.findByRole("alert")).textContent).toContain("Không kết nối được máy chủ");
  });
});
