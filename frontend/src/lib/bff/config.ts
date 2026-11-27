/** Cấu hình BFF (chỉ chạy phía server). Nơi DUY NHẤT đọc biến môi trường của BFF. */
export function apiBase(): string {
  const v = process.env.API_BASE_URL;
  if (!v) throw new Error("Thiếu biến môi trường API_BASE_URL (chỉ phía server)");
  return v.replace(/\/+$/, "");
}

/** Bí mật chung BFF↔backend (T-017). Chỉ phía server, KHÔNG tiền tố NEXT_PUBLIC_. Rỗng = không gửi IP khách. */
export function bffSecret(): string {
  return process.env.BFF_SHARED_SECRET ?? "";
}

export type VisitorIpStatus = "ok" | "missing_secret" | "short_secret";
export const MIN_BFF_SECRET = 16;

/** Không bao giờ trả giá trị secret, chỉ trạng thái. */
export function visitorIpStatus(): VisitorIpStatus {
  const n = bffSecret().length;
  return n === 0 ? "missing_secret" : n < MIN_BFF_SECRET ? "short_secret" : "ok";
}

/** Cảnh báo lúc khởi động và trong /bff/health khi secret thiếu/ngắn (mọi khách dùng chung một bộ đếm rate limit). */
export function startupWarnings(): string[] {
  const st = visitorIpStatus();
  if (st === "ok") return [];
  return [`BFF_SHARED_SECRET ${st === "missing_secret" ? "chưa đặt" : `quá ngắn (< ${MIN_BFF_SECRET} ký tự)`}: BFF không gửi IP khách nên backend `
    + "đếm MỌI khách chung một bộ đếm rate limit (một khách đăng nhập sai nhiều lần sẽ chặn tất cả). Đặt cùng BFF_SHARED_SECRET cho backend và BFF"];
}

/** Production: cookie có tiền tố __Host-/__Secure- và cờ Secure. Dev trên http://localhost: bỏ tiền tố và Secure. */
export function secureCookies(): boolean {
  return process.env.NODE_ENV === "production";
}

export function cookieNames(secure = secureCookies()) {
  return secure
    ? { access: "__Host-access", refresh: "__Secure-refresh" }
    : { access: "access", refresh: "refresh" };
}

export const REFRESH_MAX_AGE = 30 * 24 * 3600; // khớp REFRESH_TTL_DAYS mặc định của backend
