import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { isAllowed } from "@/lib/bff/allowlist";
import { handleAuth } from "@/lib/bff/auth";
import { clearCookies, parseCookies, sessionCookies } from "@/lib/bff/cookies";
import { checkCsrf } from "@/lib/bff/csrf";
import { handleProxy } from "@/lib/bff/proxy";

const ORIGIN = "https://app.test";
const ACCESS = "ACCESS.jwt.token";
const REFRESH = "refresh-token-abcdefghijklmnopqrstuvwxyz0123456789";
const TOK = (n: number) => ({ access_token: `NEW.access.${n}`, refresh_token: `new-refresh-${n}-abcdefghijklmnopqrstuvwxyz`, expires_in: 900 });

type Call = { method: string; url: string; headers: Record<string, string>; body?: string };
function fakeApi(handler: (c: Call) => { status?: number; json?: unknown; headers?: Record<string, string> }) {
  const calls: Call[] = [];
  const f = (async (url: string, init: RequestInit) => {
    const c: Call = { method: init.method ?? "GET", url, headers: (init.headers ?? {}) as Record<string, string>, body: init.body as string | undefined };
    calls.push(c);
    const r = handler(c);
    return new Response(r.json === undefined ? null : JSON.stringify(r.json), {
      status: r.status ?? 200, headers: { "content-type": "application/json", ...(r.headers ?? {}) },
    });
  }) as unknown as typeof fetch;
  return { f, calls };
}

function req(method: string, path: string, o: { cookie?: string; body?: unknown; csrf?: boolean; origin?: string | null; ct?: string } = {}) {
  const headers: Record<string, string> = {};
  if (o.cookie) headers.cookie = o.cookie;
  if (method !== "GET") {
    if (o.csrf !== false) headers["x-csrf"] = "1";
    if (o.origin !== null) headers.origin = o.origin ?? ORIGIN;
    headers["content-type"] = o.ct ?? "application/json";
  }
  return new Request(`${ORIGIN}${path}`, { method, headers, body: method === "GET" ? undefined : JSON.stringify(o.body ?? {}) });
}
const withTokens = `access=${ACCESS}; refresh=${REFRESH}`;
const refreshOnly = `refresh=${REFRESH}`;
const setCookies = (r: Response) => r.headers.getSetCookie();

beforeEach(() => { vi.stubEnv("API_BASE_URL", "http://api.test"); vi.stubEnv("NODE_ENV", "test"); });
afterEach(() => vi.unstubAllEnvs());

describe("csrf", () => {
  it("cho GET qua, chặn ghi thiếu X-CSRF / sai Origin / không phải JSON", () => {
    expect(checkCsrf(req("GET", "/bff/api/me/wallet"))).toBeNull();
    expect(checkCsrf(req("POST", "/x", { csrf: false }))?.code).toBe("csrf");
    expect(checkCsrf(req("POST", "/x", { origin: "https://evil.test" }))?.code).toBe("csrf");
    expect(checkCsrf(req("POST", "/x", { origin: null }))?.code).toBe("csrf");
    expect(checkCsrf(req("POST", "/x", { ct: "text/plain" }))?.code).toBe("csrf");
    expect(checkCsrf(req("POST", "/x"))).toBeNull();
  });
});

describe("allowlist", () => {
  it("chỉ khớp chính xác đường dẫn và phương thức", () => {
    expect(isAllowed("GET", ["me", "wallet"])).toBe(true);
    expect(isAllowed("POST", ["links"])).toBe(true);
    expect(isAllowed("POST", ["me", "wallet"])).toBe(false);
    expect(isAllowed("GET", ["me", "wallet", "x"])).toBe(false);
    expect(isAllowed("GET", ["admin", "users"])).toBe(false);
    expect(isAllowed("GET", ["auth", "login"])).toBe(false);
    for (const bad of [["me", "..", "wallet"], ["..", "me", "wallet"], ["me", "%2e%2e"], ["me\\wallet"], ["me", ""], ["me/wallet"]]) {
      expect(isAllowed("GET", bad)).toBe(false);
    }
  });
});

describe("cookies", () => {
  it("HttpOnly, SameSite=Strict, đúng Path và Max-Age", () => {
    const [a, r] = sessionCookies(TOK(1));
    expect(a).toMatch(/^access=NEW\.access\.1; Path=\/; Max-Age=900; HttpOnly; SameSite=Strict$/);
    expect(r).toMatch(/Path=\/bff; Max-Age=2592000; HttpOnly; SameSite=Strict$/);
    expect(a).not.toMatch(/Secure/);
  });
  it("production: tiền tố __Host-/__Secure- và cờ Secure", () => {
    vi.stubEnv("NODE_ENV", "production");
    const [a, r] = sessionCookies(TOK(1));
    expect(a.startsWith("__Host-access=")).toBe(true);
    expect(r.startsWith("__Secure-refresh=")).toBe(true);
    expect(a).toContain("; Secure");
    expect(r).toContain("; Secure");
    expect(clearCookies().every((c) => c.includes("Max-Age=0") && c.includes("HttpOnly"))).toBe(true);
  });
  it("parse cookie", () => {
    expect(parseCookies("a=1; b=hai%20ba; c")).toEqual({ a: "1", b: "hai ba" });
  });
});

describe("login", () => {
  it("đổi token thành cookie, KHÔNG trả token trong body/header", async () => {
    const { f } = fakeApi(() => ({ json: TOK(1) }));
    const r = await handleAuth(req("POST", "/bff/auth/login", { body: { email: "a@b.c", password: "x" } }), "login", f);
    expect(r.status).toBe(200);
    expect(await r.json()).toEqual({ ok: true });
    expect(setCookies(r)).toHaveLength(2);
    const dump = [...r.headers.entries()].filter(([k]) => k !== "set-cookie").join("|");
    expect(dump).not.toContain("NEW.access");
    expect(dump).not.toContain("new-refresh");
  });
  it("sai mật khẩu: chuyển nguyên lỗi, không đặt cookie", async () => {
    const { f } = fakeApi(() => ({ status: 401, json: { error: { code: "invalid_credentials", message: "Sai", request_id: "r1" } } }));
    const r = await handleAuth(req("POST", "/bff/auth/login"), "login", f);
    expect(r.status).toBe(401);
    expect((await r.json()).error.code).toBe("invalid_credentials");
    expect(setCookies(r)).toHaveLength(0);
  });
  it("chặn CSRF và phương thức sai trước khi gọi backend", async () => {
    const { f, calls } = fakeApi(() => ({ json: TOK(1) }));
    expect((await handleAuth(req("POST", "/x", { csrf: false }), "login", f)).status).toBe(403);
    expect((await handleAuth(req("GET", "/x"), "login", f)).status).toBe(405);
    expect((await handleAuth(req("POST", "/x"), "khong-co", f)).status).toBe(404);
    expect(calls).toHaveLength(0);
  });
});

describe("register", () => {
  it("chuyển tiếp, không đặt cookie", async () => {
    const { f, calls } = fakeApi(() => ({ status: 201, json: { id: 1, email: "a@b.c", role: "member", status: "active" } }));
    const r = await handleAuth(req("POST", "/x", { body: { email: "a@b.c", password: "mat-khau-dai-1" } }), "register", f);
    expect(r.status).toBe(201);
    expect(setCookies(r)).toHaveLength(0);
    expect(calls[0].url).toBe("http://api.test/api/v1/auth/register");
  });
});

describe("proxy", () => {
  it("gắn Bearer, giữ query, bỏ Set-Cookie của backend, no-store", async () => {
    const { f, calls } = fakeApi(() => ({ json: { pending_vnd: 1 }, headers: { "set-cookie": "evil=1", "x-request-id": "rid" } }));
    const r = await handleProxy(req("GET", "/bff/api/me/wallet/entries?limit=5", { cookie: withTokens }), ["me", "wallet", "entries"], f);
    expect(r.status).toBe(200);
    expect(calls[0].url).toBe("http://api.test/api/v1/me/wallet/entries?limit=5");
    expect(calls[0].headers.authorization).toBe(`Bearer ${ACCESS}`);
    expect(setCookies(r)).toHaveLength(0);
    expect(r.headers.get("cache-control")).toBe("no-store");
    expect(r.headers.get("x-request-id")).toBe("rid");
  });
  it("không cookie: 401 và không gọi backend; đường dẫn lạ: 404", async () => {
    const { f, calls } = fakeApi(() => ({ json: {} }));
    const r = await handleProxy(req("GET", "/x"), ["me", "wallet"], f);
    expect(r.status).toBe(401);
    expect((await r.json()).error.code).toBe("unauthorized");
    expect((await handleProxy(req("GET", "/x", { cookie: withTokens }), ["admin", "users"], f)).status).toBe(404);
    expect((await handleProxy(req("POST", "/x", { cookie: withTokens, csrf: false }), ["links"], f)).status).toBe(403);
    expect(calls).toHaveLength(0);
  });
  it("access bị từ chối: làm mới đúng MỘT lần rồi thử lại, đặt cookie mới", async () => {
    const { f, calls } = fakeApi((c) => {
      if (c.url.endsWith("/auth/refresh")) return { json: TOK(2) };
      return c.headers.authorization === `Bearer ${ACCESS}` ? { status: 401, json: { error: { code: "unauthorized", message: "x", request_id: null } } } : { json: { ok: 1 } };
    });
    const r = await handleProxy(req("GET", "/x", { cookie: withTokens }), ["me", "wallet"], f);
    expect(r.status).toBe(200);
    expect(calls.map((c) => c.url.split("/api/v1/")[1])).toEqual(["me/wallet", "auth/refresh", "me/wallet"]);
    expect(calls[1].body).toContain(REFRESH);
    expect(calls[2].headers.authorization).toBe("Bearer NEW.access.2");
    expect(setCookies(r)).toHaveLength(2);
    expect(await r.text()).not.toContain("NEW.access");
  });
  it("access đã hết hạn (cookie mất) nhưng còn refresh: làm mới trước rồi gọi", async () => {
    const { f, calls } = fakeApi((c) => (c.url.endsWith("/auth/refresh") ? { json: TOK(3) } : { json: { ok: 1 } }));
    const r = await handleProxy(req("GET", "/x", { cookie: refreshOnly }), ["me", "links"], f);
    expect(r.status).toBe(200);
    expect(calls.map((c) => c.url.split("/api/v1/")[1])).toEqual(["auth/refresh", "me/links"]);
    expect(setCookies(r)).toHaveLength(2);
  });
  it("làm mới thất bại: 401 session_expired và xóa cookie", async () => {
    const { f } = fakeApi((c) => (c.url.endsWith("/auth/refresh") ? { status: 401, json: { error: { code: "invalid_refresh", message: "x", request_id: null } } } : { status: 401, json: {} }));
    for (const cookie of [withTokens, refreshOnly]) {
      const r = await handleProxy(req("GET", "/x", { cookie }), ["me", "wallet"], f);
      expect(r.status).toBe(401);
      expect((await r.json()).error.code).toBe("session_expired");
      expect(setCookies(r).every((c) => c.includes("Max-Age=0"))).toBe(true);
    }
  });
  it("không lặp vô hạn: thử lại vẫn 401 thì chuyển 401 nguyên trạng", async () => {
    const { f, calls } = fakeApi((c) => (c.url.endsWith("/auth/refresh") ? { json: TOK(4) } : { status: 401, json: { error: { code: "unauthorized", message: "x", request_id: null } } }));
    const r = await handleProxy(req("GET", "/x", { cookie: withTokens }), ["me", "wallet"], f);
    expect(r.status).toBe(401);
    expect(calls.filter((c) => c.url.endsWith("/auth/refresh"))).toHaveLength(1);
  });
  it("vừa làm mới (access đã mất) mà API vẫn 401: KHÔNG làm mới lần hai bằng refresh token cũ đã xoay vòng", async () => {
    const { f, calls } = fakeApi((c) => (c.url.endsWith("/auth/refresh") ? { json: TOK(6) } : { status: 401, json: { error: { code: "unauthorized", message: "x", request_id: null } } }));
    const r = await handleProxy(req("GET", "/x", { cookie: refreshOnly }), ["me", "wallet"], f);
    expect(r.status).toBe(401);
    expect(calls.filter((c) => c.url.endsWith("/auth/refresh"))).toHaveLength(1);
    expect(setCookies(r)).toHaveLength(2);                 // cookie mới đã được đặt, không mất phiên
  });
  it("POST links chuyển tiếp thân JSON", async () => {
    const { f, calls } = fakeApi(() => ({ json: { code: "abc12345" } }));
    await handleProxy(req("POST", "/x", { cookie: withTokens, body: { url: "https://shopee.vn/product/1/2" } }), ["links"], f);
    expect(calls[0].method).toBe("POST");
    expect(JSON.parse(calls[0].body!)).toEqual({ url: "https://shopee.vn/product/1/2" });
  });
});

describe("logout", () => {
  it("thu hồi ở backend rồi xóa cookie", async () => {
    const { f, calls } = fakeApi(() => ({ status: 204 }));
    const r = await handleAuth(req("POST", "/x", { cookie: withTokens }), "logout", f);
    expect(r.status).toBe(204);
    expect(calls[0].url).toBe("http://api.test/api/v1/auth/logout");
    expect(calls[0].headers.authorization).toBe(`Bearer ${ACCESS}`);
    expect(setCookies(r).every((c) => c.includes("Max-Age=0"))).toBe(true);
  });
  it("access hết hạn: làm mới rồi mới đăng xuất; backend lỗi vẫn xóa cookie", async () => {
    const { f, calls } = fakeApi((c) => (c.url.endsWith("/auth/refresh") ? { json: TOK(5) } : { status: 500, json: {} }));
    const r = await handleAuth(req("POST", "/x", { cookie: refreshOnly }), "logout", f);
    expect(r.status).toBe(204);
    expect(calls.map((c) => c.url.split("/api/v1/")[1])).toEqual(["auth/refresh", "auth/logout"]);
    expect(setCookies(r)).toHaveLength(2);
  });
  it("không có cookie nào: vẫn 204 và không gọi backend", async () => {
    const { f, calls } = fakeApi(() => ({ status: 204 }));
    expect((await handleAuth(req("POST", "/x"), "logout", f)).status).toBe(204);
    expect(calls).toHaveLength(0);
  });
});
