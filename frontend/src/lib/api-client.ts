/**
 * NƠI DUY NHẤT trình duyệt gọi backend (qua BFF cùng origin: cookie HttpOnly, JS không thấy token).
 * Component KHÔNG được gọi `fetch` trực tiếp. Xem docs/adr/0005-web-luu-token-bff-httponly.md.
 */
import type { ApiErrorBody, EntryOut, LinkOut, OrderOut, UserLinkOut, UserOut, WalletOut } from "./types";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public requestId: string | null) {
    super(message);
  }
  /** Chưa đăng nhập hoặc phiên hết hạn: UI nên chuyển về trang đăng nhập. */
  get isAuth(): boolean {
    return this.status === 401 && (this.code === "session_expired" || this.code === "unauthorized");
  }
}

async function request<T>(method: string, url: string, body?: unknown, f: typeof fetch = fetch): Promise<T> {
  const headers: Record<string, string> = { accept: "application/json" };
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

const qs = (p: Record<string, number | undefined>) => {
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
  walletEntries: (p: { limit?: number; offset?: number } = {}) =>
    request<EntryOut[]>("GET", `/bff/api/me/wallet/entries${qs(p)}`),
};
