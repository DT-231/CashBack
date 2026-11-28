// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import OrphansPage from "./OrphansPage";

const { adminOrphans, adminAssignOrphan, replace, router } = vi.hoisted(() => {
  const replace = vi.fn();
  return { adminOrphans: vi.fn(), adminAssignOrphan: vi.fn(), replace, router: { replace } };
});
vi.mock("@/lib/api-client", () => ({
  ApiError: class ApiError extends Error {
    constructor(public status: number, public code: string, message: string, public requestId: string | null = null) { super(message); }
    get isAuth() { return this.status === 401 && ["session_expired", "unauthorized"].includes(this.code); }
    get isMfaRequired() { return this.status === 403 && this.code === "mfa_required"; }
  },
  api: { adminOrphans, adminAssignOrphan },
}));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const orphan = (id: number, status = "PENDING", purchase_time: string | null = "2026-11-28T02:00:00Z") => ({
  id, order_sn: `order-${id}`, status, commission_micro: 987654321, commission_vnd: 12345, purchase_time, utm_content: null, reason: `Lý do nguyên văn ${id}`,
});
const apiError = async (status: number, code: string, message = "lỗi") => {
  const { ApiError } = await import("@/lib/api-client");
  return new ApiError(status, code, message, null);
};

describe("OrphansPage", () => {
  beforeEach(() => { adminOrphans.mockReset(); adminAssignOrphan.mockReset(); replace.mockReset(); adminOrphans.mockResolvedValue([orphan(1)]); adminAssignOrphan.mockResolvedValue(undefined); });
  afterEach(cleanup);

  it("renders all fields, known and unknown labels, formatted VND, and hides null dates and micro values", async () => {
    adminOrphans.mockResolvedValue([orphan(1), orphan(2, "COMPLETED", null), orphan(3, "CANCELLED"), orphan(4, "RETURNED"), orphan(5, "FUTURE")]);
    render(<OrphansPage />);
    await screen.findByText("#1 · order-1");
    for (const label of ["Đang chờ", "Hoàn thành", "Đã hủy", "Đã hoàn trả", "FUTURE"]) expect(screen.getAllByText(`Trạng thái: ${label}`).length).toBe(1);
    expect(screen.getByText("Lý do mồ côi: Lý do nguyên văn 1")).toBeTruthy();
    expect(screen.getAllByText("Hoa hồng: 12.345 ₫")).toHaveLength(5);
    expect(screen.getAllByText(/Ngày mua:/)).toHaveLength(4);
    expect(document.body.textContent).not.toContain("987654321");
  });

  it("loads more by current row count, appends pages, and hides pagination for a short page", async () => {
    const full = Array.from({ length: 50 }, (_, index) => orphan(index + 1));
    adminOrphans.mockResolvedValueOnce(full).mockResolvedValueOnce([orphan(51)]);
    render(<OrphansPage />);
    await screen.findByText("#1 · order-1");
    const more = screen.getByRole("button", { name: "Xem thêm" });
    fireEvent.click(more); fireEvent.click(more);
    await screen.findByText("#51 · order-51");
    expect(adminOrphans).toHaveBeenCalledTimes(2);
    expect(adminOrphans).toHaveBeenLastCalledWith({ limit: 50, offset: 50 });
    expect(screen.getByText("#1 · order-1")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Xem thêm" })).toBeNull();
    cleanup(); adminOrphans.mockResolvedValue([orphan(1)]); render(<OrphansPage />);
    await screen.findByText("#1 · order-1");
    expect(screen.queryByRole("button", { name: "Xem thêm" })).toBeNull();
  });

  it("shows empty state", async () => {
    adminOrphans.mockResolvedValue([]); render(<OrphansPage />);
    expect(await screen.findByText("Không có đơn mồ côi.")).toBeTruthy();
  });

  it("rejects invalid user IDs and short reasons even on direct form submit", async () => {
    render(<OrphansPage />); await screen.findByText("#1 · order-1");
    const user = screen.getByLabelText("ID người dùng"); const reason = screen.getByLabelText("Lý do"); const form = screen.getByRole("form", { name: "Gán đơn #1" });
    for (const value of ["", "abc", "0", "-1", "1.5", "1e3", "0x10", "+5", " 5", "5 ", "99999999999999999999", "٣"]) {
      fireEvent.change(user, { target: { value } }); fireEvent.change(reason, { target: { value: "hợp lệ" } }); fireEvent.submit(form);
      expect(screen.queryByText(/Gán đơn #1 cho người dùng/)).toBeNull();
      expect(adminAssignOrphan).not.toHaveBeenCalled();
    }
    fireEvent.change(user, { target: { value: "1" } });
    for (const value of ["", "  ", "ab", " a "]) {
      fireEvent.change(reason, { target: { value } }); fireEvent.submit(form);
      expect(screen.queryByText(/Gán đơn #1 cho người dùng/)).toBeNull();
      expect(adminAssignOrphan).not.toHaveBeenCalled();
    }
  });

  it("requires explicit confirmation, cancel does not call the API, and double submit assigns once", async () => {
    render(<OrphansPage />); await screen.findByText("#1 · order-1");
    fireEvent.change(screen.getByLabelText("ID người dùng"), { target: { value: "42" } });
    fireEvent.change(screen.getByLabelText("Lý do"), { target: { value: "  Khiếu nại  " } });
    fireEvent.click(screen.getByRole("button", { name: "Gán" }));
    expect(screen.getByText("Gán đơn #1 cho người dùng 42? Người này sẽ nhận hoàn tiền của đơn.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Hủy" })); expect(adminAssignOrphan).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Gán" }));
    const confirm = screen.getByRole("button", { name: "Xác nhận gán" });
    adminOrphans.mockResolvedValueOnce([]);
    fireEvent.click(confirm); fireEvent.click(confirm);
    await screen.findByText("Đã gán đơn #1 cho người dùng 42");
    expect(adminAssignOrphan).toHaveBeenCalledTimes(1);
    expect(adminAssignOrphan).toHaveBeenCalledWith(1, 42, "  Khiếu nại  ");
    await waitFor(() => expect(screen.queryByText("#1 · order-1")).toBeNull());
  });

  it("maps assignment errors and reloads on missing or already assigned orders", async () => {
    const cases = [
      ["invalid_assignee", "Người dùng không hợp lệ (không tồn tại, bị khóa, hoặc là chính bạn)", false],
      ["order_not_found", "Không tìm thấy đơn, đã tải lại danh sách", true],
      ["not_an_orphan", "Đơn này đã được xử lý ở nơi khác, đã tải lại danh sách", true],
      ["forbidden", "Chỉ admin được thực hiện", false],
    ] as const;
    for (const [code, message, reload] of cases) {
      cleanup(); adminOrphans.mockReset().mockResolvedValue([orphan(1)]); adminAssignOrphan.mockRejectedValueOnce(await apiError(code === "forbidden" ? 403 : 422, code));
      render(<OrphansPage />); await screen.findByText("#1 · order-1");
      fireEvent.change(screen.getByLabelText("ID người dùng"), { target: { value: "9" } }); fireEvent.change(screen.getByLabelText("Lý do"), { target: { value: "lý do" } });
      fireEvent.click(screen.getByRole("button", { name: "Gán" })); fireEvent.click(screen.getByRole("button", { name: "Xác nhận gán" }));
      expect((await screen.findByRole("alert")).textContent).toContain(message);
      expect(adminOrphans).toHaveBeenCalledTimes(reload ? 2 : 1);
    }
  });

  it("redirects auth and MFA failures and reports network errors during load and assignment", async () => {
    adminOrphans.mockRejectedValueOnce(await apiError(401, "session_expired")); render(<OrphansPage />); await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    cleanup(); replace.mockClear(); adminOrphans.mockRejectedValueOnce(await apiError(403, "mfa_required")); render(<OrphansPage />); await waitFor(() => expect(replace).toHaveBeenCalledWith("/admin/mfa"));
    cleanup(); adminOrphans.mockRejectedValueOnce(await apiError(0, "network")); render(<OrphansPage />); expect((await screen.findByRole("alert")).textContent).toContain("Không kết nối được máy chủ");
    cleanup(); adminOrphans.mockResolvedValue([orphan(1)]); adminAssignOrphan.mockRejectedValueOnce(await apiError(401, "unauthorized")); render(<OrphansPage />); await screen.findByText("#1 · order-1");
    fireEvent.change(screen.getByLabelText("ID người dùng"), { target: { value: "9" } }); fireEvent.change(screen.getByLabelText("Lý do"), { target: { value: "lý do" } }); fireEvent.click(screen.getByRole("button", { name: "Gán" })); fireEvent.click(screen.getByRole("button", { name: "Xác nhận gán" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    cleanup(); replace.mockClear(); adminOrphans.mockResolvedValue([orphan(1)]); adminAssignOrphan.mockRejectedValueOnce(await apiError(403, "mfa_required")); render(<OrphansPage />); await screen.findByText("#1 · order-1");
    fireEvent.change(screen.getByLabelText("ID người dùng"), { target: { value: "9" } }); fireEvent.change(screen.getByLabelText("Lý do"), { target: { value: "lý do" } }); fireEvent.click(screen.getByRole("button", { name: "Gán" })); fireEvent.click(screen.getByRole("button", { name: "Xác nhận gán" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/admin/mfa"));
    cleanup(); adminOrphans.mockResolvedValue([orphan(1)]); adminAssignOrphan.mockRejectedValueOnce(await apiError(0, "network")); render(<OrphansPage />); await screen.findByText("#1 · order-1");
    fireEvent.change(screen.getByLabelText("ID người dùng"), { target: { value: "9" } }); fireEvent.change(screen.getByLabelText("Lý do"), { target: { value: "lý do" } }); fireEvent.click(screen.getByRole("button", { name: "Gán" })); fireEvent.click(screen.getByRole("button", { name: "Xác nhận gán" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Không kết nối được máy chủ");
  });
});
