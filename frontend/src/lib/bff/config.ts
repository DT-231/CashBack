/** Cấu hình BFF (chỉ chạy phía server). Nơi DUY NHẤT đọc biến môi trường của BFF. */
export function apiBase(): string {
  const v = process.env.API_BASE_URL;
  if (!v) throw new Error("Thiếu biến môi trường API_BASE_URL (chỉ phía server)");
  return v.replace(/\/+$/, "");
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
