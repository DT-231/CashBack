/** Gọi backend. Không bao giờ chuyển tiếp Set-Cookie của backend hay để lộ token ra ngoài. */
import { isIP } from "node:net";
import { apiBase, bffSecret } from "./config";
import type { Tokens } from "./cookies";

export type Fetch = typeof fetch;

/**
 * IP thật của khách cho backend (T-017). Lấy từ CF-Connecting-IP (do Cloudflare đặt, khách không tự đặt được phía sau Tunnel);
 * chỉ gửi khi có BFF_SHARED_SECRET và IP hợp lệ. X-Visitor-IP / X-BFF-Secret do khách gửi tới BFF KHÔNG bao giờ được chuyển tiếp:
 * header gửi đi luôn được dựng từ đầu ở đây.
 */
export function visitorHeaders(request: Request): Record<string, string> {
  const secret = bffSecret();
  const ip = (request.headers.get("cf-connecting-ip") ?? "").trim();
  if (!secret || isIP(ip) === 0) return {};
  return { "x-visitor-ip": ip, "x-bff-secret": secret };
}

export async function callApi(f: Fetch, method: string, path: string, opts: { token?: string; body?: string; requestId?: string; visitor?: Record<string, string>; idempotencyKey?: string }) {
  const headers: Record<string, string> = { accept: "application/json", ...(opts.visitor ?? {}) };
  if (opts.token) headers.authorization = `Bearer ${opts.token}`;
  if (opts.body !== undefined) headers["content-type"] = "application/json";
  if (opts.requestId) headers["x-request-id"] = opts.requestId;
  if (opts.idempotencyKey) headers["idempotency-key"] = opts.idempotencyKey;
  return f(`${apiBase()}/api/v1/${path}`, { method, headers, body: opts.body, redirect: "manual", cache: "no-store" });
}

/** Làm mới token. null nếu refresh token không còn dùng được. */
export async function refreshTokens(f: Fetch, refresh: string, visitor?: Record<string, string>): Promise<Tokens | null> {
  const r = await callApi(f, "POST", "auth/refresh", { body: JSON.stringify({ refresh_token: refresh }), visitor });
  if (!r.ok) return null;
  const j = (await r.json()) as Partial<Tokens>;
  return j.access_token && j.refresh_token && typeof j.expires_in === "number" ? (j as Tokens) : null;
}

/** Chuyển tiếp thân phản hồi nhưng chỉ giữ header an toàn; luôn no-store. */
export async function passThrough(r: Response, setCookies: string[] = []): Promise<Response> {
  const h = new Headers({ "cache-control": "no-store" });
  const ct = r.headers.get("content-type");
  if (ct) h.set("content-type", ct);
  const rid = r.headers.get("x-request-id");
  if (rid) h.set("x-request-id", rid);
  for (const name of ["content-disposition", "x-row-count", "retry-after"]) {      // CSV xuất, số dòng, giới hạn tốc độ
    const v = r.headers.get(name);
    if (v) h.set(name, v);
  }
  for (const c of setCookies) h.append("set-cookie", c);
  const body = r.status === 204 || r.status === 304 ? null : await r.arrayBuffer();
  return new Response(body, { status: r.status, headers: h });
}
