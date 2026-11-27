// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import UsersPage from "./UsersPage";

const { adminUsers, adminSetUserStatus, replace, router } = vi.hoisted(() => { const replace = vi.fn(); return { adminUsers: vi.fn(), adminSetUserStatus: vi.fn(), replace, router: { replace } }; });
vi.mock("@/lib/api-client", () => ({ ApiError: class ApiError extends Error { constructor(public status: number, public code: string, message: string, public requestId: string | null = null) { super(message); } get isAuth() { return this.status === 401 && ["session_expired", "unauthorized"].includes(this.code); } get isMfaRequired() { return this.status === 403 && this.code === "mfa_required"; } }, api: { adminUsers, adminSetUserStatus } }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
const user = (id: number, role: string = "member", status: string = "active") => ({ id, email: `person${id}@example.test`, role, status, created_at: "2026-11-27T10:00:00Z", available_vnd: 1000, pending_vnd: 2000, held_vnd: 3000 });
describe("UsersPage", () => {
  beforeEach(() => { adminUsers.mockReset(); adminSetUserStatus.mockReset(); replace.mockReset(); adminUsers.mockResolvedValue([user(1)]); adminSetUserStatus.mockResolvedValue(undefined); }); afterEach(cleanup);
  it("searches only on submit and uses the query for appended pages", async () => {
    const firstPage = Array.from({ length: 50 }, (_, i) => user(i + 1)); adminUsers.mockResolvedValueOnce([user(1)]).mockResolvedValueOnce(firstPage).mockResolvedValueOnce([user(51)]);
    render(<UsersPage />); await screen.findByText(/#1 · person1/); fireEvent.change(screen.getByLabelText("Tìm theo email"), { target: { value: "abc@example.test" } }); expect(adminUsers).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Tìm" })); await screen.findByText(/#50 · person50/); await screen.findByRole("button", { name: "Xem thêm" }); fireEvent.click(screen.getByRole("button", { name: "Xem thêm" }));
    await screen.findByText(/#51/); expect(adminUsers).toHaveBeenLastCalledWith({ q: "abc@example.test", limit: 50, offset: 50 }); expect(screen.getByText(/#1 · person1/)).toBeTruthy();
  });
  it("hides pagination for short first and later pages", async () => {
    adminUsers.mockResolvedValueOnce([user(1)]).mockResolvedValueOnce(Array.from({ length: 50 }, (_, i) => user(i + 1))).mockResolvedValueOnce([user(51)]);
    render(<UsersPage />);
    await screen.findByText(/#1 · person1/);
    expect(screen.queryByRole("button", { name: "Xem thêm" })).toBeNull();

    cleanup();
    render(<UsersPage />);
    await screen.findByText(/#50 · person50/);
    fireEvent.click(screen.getByRole("button", { name: "Xem thêm" }));
    expect(await screen.findByRole("button", { name: "Đang tải…" })).toBeTruthy();
    await screen.findByText(/#51 · person51/);
    await waitFor(() => expect(screen.queryByRole("button", { name: "Xem thêm" })).toBeNull());
  });
  it("redirects on auth and MFA errors during the initial load", async () => {
    const ApiError = (await import("@/lib/api-client")).ApiError;
    adminUsers.mockRejectedValueOnce(new ApiError(401, "session_expired", "expired", null));
    render(<UsersPage />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));

    cleanup(); replace.mockClear();
    adminUsers.mockRejectedValueOnce(new ApiError(403, "mfa_required", "mfa", null));
    render(<UsersPage />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/admin/mfa"));
  });
  it("shows known role and status labels and omits actions for admins", async () => {
    adminUsers.mockResolvedValue([user(1, "member", "unverified"), user(2, "staff", "active"), user(3, "admin", "locked")]); render(<UsersPage />);
    await screen.findByText("Vai trò: Thành viên"); expect(screen.getByText("Vai trò: Nhân viên")).toBeTruthy(); expect(screen.getByText("Vai trò: Quản trị")).toBeTruthy();
    expect(screen.getByText("Trạng thái: Chưa xác minh")).toBeTruthy(); expect(screen.getByText("Trạng thái: Hoạt động")).toBeTruthy(); expect(screen.getByText("Trạng thái: Đã khóa")).toBeTruthy();
    const adminRow = screen.getByText(/#3 · person3/).closest("li")!; expect(adminRow.querySelector("button")).toBeNull();
  });
  it("validates reason and submits status once with the entered reason", async () => {
    render(<UsersPage />); await screen.findByText(/#1 · person1/); fireEvent.change(screen.getByLabelText(/Lý do khóa/), { target: { value: "   " } });
    fireEvent.submit(screen.getByLabelText(/Lý do khóa/).closest("form")!); expect(adminSetUserStatus).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText(/Lý do khóa/), { target: { value: "vi phạm" } }); const form = screen.getByLabelText(/Lý do khóa/).closest("form")!;
    fireEvent.submit(form); fireEvent.submit(form); await waitFor(() => expect(adminSetUserStatus).toHaveBeenCalledTimes(1)); expect(adminSetUserStatus).toHaveBeenCalledWith(1, "locked", "vi phạm");
  });
  it("disables the status action and shows progress while the request is pending", async () => {
    let resolveStatus!: () => void;
    adminSetUserStatus.mockImplementation(() => new Promise<void>((resolve) => { resolveStatus = resolve; }));
    render(<UsersPage />);
    await screen.findByText(/#1 · person1/);
    fireEvent.change(screen.getByLabelText(/Lý do khóa/), { target: { value: "lý do" } });
    fireEvent.submit(screen.getByLabelText(/Lý do khóa/).closest("form")!);
    const savingButton = await screen.findByRole("button", { name: "Đang lưu…" });
    expect((savingButton as HTMLButtonElement).disabled).toBe(true);
    fireEvent.submit(screen.getByLabelText(/Lý do khóa/).closest("form")!);
    expect(adminSetUserStatus).toHaveBeenCalledTimes(1);
    resolveStatus();
  });
  it("reloads the submitted query after a successful status change and clears the reason", async () => {
    adminUsers.mockResolvedValueOnce([user(1)]).mockResolvedValueOnce([user(1)]).mockResolvedValueOnce([user(1)]);
    render(<UsersPage />);
    await screen.findByText(/#1 · person1/);
    fireEvent.change(screen.getByLabelText("Tìm theo email"), { target: { value: "find@example.test" } });
    fireEvent.click(screen.getByRole("button", { name: "Tìm" }));
    await waitFor(() => expect(adminUsers).toHaveBeenLastCalledWith({ q: "find@example.test", limit: 50, offset: 0 }));
    const reasonInput = screen.getByLabelText(/Lý do khóa/);
    fireEvent.change(reasonInput, { target: { value: "lý do hợp lệ" } });
    fireEvent.submit(reasonInput.closest("form")!);
    await waitFor(() => expect(adminSetUserStatus).toHaveBeenCalledWith(1, "locked", "lý do hợp lệ"));
    await waitFor(() => expect(adminUsers).toHaveBeenCalledTimes(3));
    expect(adminUsers).toHaveBeenLastCalledWith({ q: "find@example.test", limit: 50, offset: 0 });
    expect((screen.getByLabelText(/Lý do khóa/) as HTMLInputElement).value).toBe("");
  });
  it("formats each wallet balance and shows the empty state", async () => {
    adminUsers.mockResolvedValueOnce([{ ...user(1), pending_vnd: 1000, available_vnd: 2000, held_vnd: 3000 }]);
    render(<UsersPage />);
    expect(await screen.findByText("Ví: Chờ 1.000 ₫ · Rút được 2.000 ₫ · Đang khóa 3.000 ₫")).toBeTruthy();

    cleanup(); adminUsers.mockResolvedValueOnce([]);
    render(<UsersPage />);
    expect(await screen.findByText("Không tìm thấy người dùng.")).toBeTruthy();
  });
  it("maps mutation errors, reloads when user is missing, and redirects auth/MFA", async () => {
    const ApiError = (await import("@/lib/api-client")).ApiError; render(<UsersPage />); await screen.findByText(/#1 · person1/);
    adminSetUserStatus.mockRejectedValueOnce(new ApiError(403, "invalid_target", "raw", null)); fireEvent.change(screen.getByLabelText(/Lý do khóa/), { target: { value: "lý do" } }); fireEvent.submit(screen.getByLabelText(/Lý do khóa/).closest("form")!); expect((await screen.findByRole("alert")).textContent).toContain("Không được đổi trạng thái tài khoản này");
    adminSetUserStatus.mockRejectedValueOnce(new ApiError(404, "user_not_found", "raw", null)); fireEvent.submit(screen.getByLabelText(/Lý do khóa/).closest("form")!); expect((await screen.findByRole("alert")).textContent).toContain("Không tìm thấy người dùng, đã tải lại danh sách");
    adminSetUserStatus.mockRejectedValueOnce(new ApiError(403, "forbidden", "raw", null)); fireEvent.submit(screen.getByLabelText(/Lý do khóa/).closest("form")!); expect((await screen.findByRole("alert")).textContent).toContain("Chỉ admin được thực hiện");
    adminSetUserStatus.mockRejectedValueOnce(new ApiError(422, "custom", "Thông báo API", null)); fireEvent.submit(screen.getByLabelText(/Lý do khóa/).closest("form")!); expect((await screen.findByRole("alert")).textContent).toContain("Thông báo API");
    adminSetUserStatus.mockRejectedValueOnce(new ApiError(401, "unauthorized", "expired", null)); fireEvent.submit(screen.getByLabelText(/Lý do khóa/).closest("form")!); await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    adminSetUserStatus.mockRejectedValueOnce(new ApiError(403, "mfa_required", "mfa", null)); fireEvent.submit(screen.getByLabelText(/Lý do khóa/).closest("form")!); await waitFor(() => expect(replace).toHaveBeenCalledWith("/admin/mfa"));
  });
  it("reloads after user_not_found and maps mutation network errors", async () => {
    const ApiError = (await import("@/lib/api-client")).ApiError;
    render(<UsersPage />);
    await screen.findByText(/#1 · person1/);
    const form = screen.getByLabelText(/Lý do khóa/).closest("form")!;
    fireEvent.change(screen.getByLabelText(/Lý do khóa/), { target: { value: "lý do" } });
    const initialCalls = adminUsers.mock.calls.length;
    adminSetUserStatus.mockRejectedValueOnce(new ApiError(404, "user_not_found", "raw", null));
    fireEvent.submit(form);
    await screen.findByText("Không tìm thấy người dùng, đã tải lại danh sách");
    await waitFor(() => expect(adminUsers).toHaveBeenCalledTimes(initialCalls + 1));

    adminSetUserStatus.mockRejectedValueOnce(new ApiError(0, "network", "raw network message", null));
    fireEvent.submit(form);
    expect((await screen.findByRole("alert")).textContent).toContain("Không kết nối được máy chủ");
  });
});
