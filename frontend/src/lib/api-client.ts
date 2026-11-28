/**
 * NƠI DUY NHẤT trình duyệt gọi backend (qua BFF cùng origin: cookie HttpOnly, JS không thấy token).
 * Component KHÔNG được gọi `fetch` trực tiếp. Xem docs/adr/0005-web-luu-token-bff-httponly.md.
 */
import type {
  AdminHealth, AdminOrder, FraudFlag, AdminOrphan, AdminOverview, AdminUser, AdminWithdrawalOut, ApiErrorBody, BankAccountIn, BankAccountOut, EntryOut, LedgerIntegrity, LinkOut, MfaEnableOut, MfaSetup, MfaStatus, OrderOut,
  PayoutAccountOut, Reconciliation, ShopeeSessionStatus, UserLinkOut, UserOut, WalletOut, WithdrawalOut, WithdrawalRules, WithdrawalStatus,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public requestId: string | null) {
    super(message);
  }
  /** Chưa đăng nhập hoặc phiên hết hạn: UI nên chuyển về trang đăng nhập. */
  get isAuth(): boolean {
    return this.status === 401 && (this.code === "session_expired" || this.code === "unauthorized");
  }
  /** Route admin cần đăng nhập hai lớp: UI chuyển sang trang thiết lập/nhập mã TOTP. */
  get isMfaRequired(): boolean {
    return this.status === 403 && this.code === "mfa_required";
  }
}

async function request<T>(method: string, url: string, body?: unknown, f: typeof fetch = fetch, extra: Record<string, string> = {}): Promise<T> {
  const headers: Record<string, string> = { accept: "application/json", ...extra };
  if (method !== "GET") {
    headers["content-type"] = "application/json";
    headers["x-csrf"] = "1";
  }
  let r: Response;
  try {
    r = await f(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), credentials: "same-origin" });
  } catch {
    throw new ApiError(0, "network", "Không kết nối được máy chủ. Vui lòng thử lại.", null);
  }
  if (r.status === 204) return undefined as T;
  let data: unknown = null;
  try {
    data = await r.json();
  } catch {
    /* không phải JSON */
  }
  if (!r.ok) {
    const e = (data as ApiErrorBody | null)?.error;
    throw new ApiError(r.status, e?.code ?? "error", e?.message ?? "Có lỗi xảy ra. Vui lòng thử lại.", e?.request_id ?? null);
  }
  return data as T;
}

/** Tải tệp (CSV xuất). Cùng quy tắc lỗi như `request`. */
async function requestBlob(url: string, f: typeof fetch = fetch): Promise<Blob> {
  let r: Response;
  try {
    r = await f(url, { method: "GET", credentials: "same-origin" });
  } catch {
    throw new ApiError(0, "network", "Không kết nối được máy chủ. Vui lòng thử lại.", null);
  }
  if (!r.ok) {
    let data: unknown = null;
    try { data = await r.json(); } catch { /* không phải JSON */ }
    const e = (data as ApiErrorBody | null)?.error;
    throw new ApiError(r.status, e?.code ?? "error", e?.message ?? "Có lỗi xảy ra. Vui lòng thử lại.", e?.request_id ?? null);
  }
  return r.blob();
}

const qs = (p: Record<string, number | string | undefined>) => {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) if (v !== undefined) s.set(k, String(v));
  const t = s.toString();
  return t ? `?${t}` : "";
};

export const api = {
  register: (email: string, password: string) => request<UserOut>("POST", "/bff/auth/register", { email, password }),
  login: (email: string, password: string) => request<{ ok: true }>("POST", "/bff/auth/login", { email, password }),
  logout: () => request<void>("POST", "/bff/auth/logout", {}),
  me: () => request<UserOut>("GET", "/bff/api/auth/me"),
  createLink: (url: string) => request<LinkOut>("POST", "/bff/api/links", { url }),
  myLinks: (p: { limit?: number; offset?: number } = {}) => request<UserLinkOut[]>("GET", `/bff/api/me/links${qs(p)}`),
  wallet: () => request<WalletOut>("GET", "/bff/api/me/wallet"),
  myOrders: (p: { limit?: number; offset?: number } = {}) => request<OrderOut[]>("GET", `/bff/api/me/orders${qs(p)}`),
  // Rút tiền (người dùng)
  withdrawalRules: () => request<WithdrawalRules>("GET", "/bff/api/me/withdrawals/rules"),
  bankAccounts: () => request<BankAccountOut[]>("GET", "/bff/api/me/bank-accounts"),
  addBankAccount: (body: BankAccountIn) => request<BankAccountOut>("POST", "/bff/api/me/bank-accounts", body),
  myWithdrawals: (p: { limit?: number; offset?: number } = {}) => request<WithdrawalOut[]>("GET", `/bff/api/me/withdrawals${qs(p)}`),
  /** `idempotencyKey` do UI tạo MỘT lần cho mỗi lần người dùng bấm "Rút" và giữ nguyên khi thử lại (bấm hai lần không tạo hai yêu cầu). */
  requestWithdrawal: (body: { amount_vnd: number; bank_account_id: number }, idempotencyKey: string) =>
    request<WithdrawalOut>("POST", "/bff/api/me/withdrawals", body, fetch, { "idempotency-key": idempotencyKey }),
  // Đăng nhập hai lớp
  mfaStatus: () => request<MfaStatus>("GET", "/bff/api/auth/mfa/status"),
  mfaSetup: () => request<MfaSetup>("POST", "/bff/api/auth/mfa/setup", {}),
  mfaEnable: (code: string) => request<MfaEnableOut>("POST", "/bff/api/auth/mfa/enable", { code }),
  mfaVerify: (b: { code: string } | { recovery_code: string }) => request<{ ok: true }>("POST", "/bff/auth/mfa-verify", b),
  mfaDisable: (code: string) => request<void>("POST", "/bff/api/auth/mfa/disable", { code }),
  // Admin: duyệt/chi trả
  adminWithdrawals: (p: { status?: WithdrawalStatus; limit?: number; offset?: number } = {}) =>
    request<AdminWithdrawalOut[]>("GET", `/bff/api/admin/withdrawals${qs(p)}`),
  adminApprove: (id: number) => request<AdminWithdrawalOut>("POST", `/bff/api/admin/withdrawals/${id}/approve`, {}),
  adminReject: (id: number, reason: string) => request<AdminWithdrawalOut>("POST", `/bff/api/admin/withdrawals/${id}/reject`, { reason }),
  adminFail: (id: number, reason: string) => request<AdminWithdrawalOut>("POST", `/bff/api/admin/withdrawals/${id}/fail`, { reason }),
  adminMarkPaid: (id: number, provider_ref: string) =>
    request<AdminWithdrawalOut>("POST", `/bff/api/admin/withdrawals/${id}/mark-paid`, { provider_ref }),
  adminPayoutAccount: (id: number) => request<PayoutAccountOut>("GET", `/bff/api/admin/withdrawals/${id}/payout-account`),
  adminExportCsv: () => requestBlob("/bff/api/admin/withdrawals/export.csv"),
  // Admin console
  adminOverview: (days = 30) => request<AdminOverview>("GET", `/bff/api/admin/overview${qs({ days })}`),
  adminUsers: (p: { q?: string; limit?: number; offset?: number } = {}) => request<AdminUser[]>("GET", `/bff/api/admin/users${qs(p)}`),
  adminSetUserStatus: (id: number, status: "active" | "locked", reason: string) =>
    request<void>("PATCH", `/bff/api/admin/users/${id}`, { status, reason }),
  adminOrders: (p: { status?: string; source?: string; limit?: number; offset?: number } = {}) =>
    request<AdminOrder[]>("GET", `/bff/api/admin/orders${qs(p)}`),
  adminOrphans: (p: { limit?: number; offset?: number } = {}) => request<AdminOrphan[]>("GET", `/bff/api/admin/orphans${qs(p)}`),
  adminAssignOrphan: (orderId: number, user_id: number, reason: string) =>
    request<void>("POST", `/bff/api/admin/orphans/${orderId}/assign`, { user_id, reason }),
  adminSetShopeeCookie: (cookie: string) => request<void>("PUT", "/bff/api/admin/shopee-session", { cookie }),
  adminShopeeSessionStatus: () => request<ShopeeSessionStatus>("GET", "/bff/api/admin/shopee-session/status"),
  adminFraudFlags: (p: { status?: string; limit?: number; offset?: number } = {}) => request<FraudFlag[]>("GET", `/bff/api/admin/fraud-flags${qs(p)}`),
  adminResolveFraudFlag: (id: number, status: "dismissed" | "confirmed", note: string) =>
    request<void>("POST", `/bff/api/admin/fraud-flags/${id}/resolve`, { status, note }),
  adminHealth: () => request<AdminHealth>("GET", "/bff/api/admin/health"),
  adminReconciliation: (month: string) => request<Reconciliation>("GET", `/bff/api/admin/reconciliation?month=${encodeURIComponent(month)}`),
  adminLedgerIntegrity: () => request<LedgerIntegrity>("GET", "/bff/api/admin/ledger-integrity"),
  // Khôi phục tài khoản (công khai): token đi trong thân POST
  forgotPassword: (email: string) => request<{ ok: true }>("POST", "/bff/auth/forgot", { email }),
  resetPassword: (token: string, password: string) => request<void>("POST", "/bff/auth/reset", { token, password }),
  verifyEmail: (token: string) => request<void>("POST", "/bff/auth/verify-email", { token }),
  resendVerification: (email: string) => request<{ ok: true }>("POST", "/bff/auth/resend-verification", { email }),
  walletEntries: (p: { limit?: number; offset?: number } = {}) =>
    request<EntryOut[]>("GET", `/bff/api/me/wallet/entries${qs(p)}`),
};
