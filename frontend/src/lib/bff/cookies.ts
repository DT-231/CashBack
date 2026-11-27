/** Đọc/ghi cookie HttpOnly. Token chỉ nằm ở đây, JS trình duyệt không bao giờ thấy. */
import { cookieNames, REFRESH_MAX_AGE, secureCookies } from "./config";

export type Tokens = { access_token: string; refresh_token: string; expires_in: number };

export function parseCookies(header: string | null): Record<string, string> {
  const out: Record<string, string> = {};
  for (const part of (header ?? "").split(";")) {
    const i = part.indexOf("=");
    if (i < 0) continue;
    const k = part.slice(0, i).trim();
    if (k && !(k in out)) out[k] = decodeURIComponent(part.slice(i + 1).trim());
  }
  return out;
}

type Opts = { maxAge: number; path: string; secure: boolean; sameSite: "Lax" | "Strict" };

function serialize(name: string, value: string, o: Opts): string {
  const attrs = [`${name}=${encodeURIComponent(value)}`, `Path=${o.path}`, `Max-Age=${o.maxAge}`, "HttpOnly", `SameSite=${o.sameSite}`];
  if (o.secure) attrs.push("Secure");
  return attrs.join("; ");
}

export function readTokens(request: Request): { access?: string; refresh?: string } {
  const n = cookieNames();
  const c = parseCookies(request.headers.get("cookie"));
  return { access: c[n.access] || undefined, refresh: c[n.refresh] || undefined };
}

/** access: SameSite=Lax (người vào từ link Facebook/Zalo vẫn được nhận ra khi điều hướng); refresh: Strict (chỉ BFF dùng). Hai chuỗi Set-Cookie cho một phiên mới/được làm mới. */
export function sessionCookies(t: Tokens): string[] {
  const n = cookieNames();
  const secure = secureCookies();
  return [
    serialize(n.access, t.access_token, { maxAge: Math.max(1, Math.floor(t.expires_in)), path: "/", secure, sameSite: "Lax" }),
    serialize(n.refresh, t.refresh_token, { maxAge: REFRESH_MAX_AGE, path: "/bff", secure, sameSite: "Strict" }),
  ];
}

export function clearCookies(): string[] {
  const n = cookieNames();
  const secure = secureCookies();
  return [
    serialize(n.access, "", { maxAge: 0, path: "/", secure, sameSite: "Lax" }),
    serialize(n.refresh, "", { maxAge: 0, path: "/bff", secure, sameSite: "Strict" }),
  ];
}
