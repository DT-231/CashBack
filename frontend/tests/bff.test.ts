import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { isAllowed } from "@/lib/bff/allowlist";
import { handleAuth } from "@/lib/bff/auth";
import { clearCookies, parseCookies, sessionCookies } from "@/lib/bff/cookies";
import { checkCsrf } from "@/lib/bff/csrf";
import { handleProxy } from "@/lib/bff/proxy";
import { handleHealth } from "@/lib/bff/health";
import { startupWarnings, visitorIpStatus } from "@/lib/bff/config";

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
  it("mọi phương thức ghi đều cần X-CSRF (cookie truy cập là Lax nên đây là lớp chính)", () => {
    for (const m of ["POST", "PUT", "PATCH", "DELETE"]) expect(checkCsrf(req(m, "/x", { csrf: false }))?.code, m).toBe("csrf");
    for (const m of ["GET", "HEAD"]) expect(checkCsrf(new Request("https://app.test/x", { method: m })), m).toBeNull();
  });
  it("allowlist chỉ có GET đọc và đúng các POST đã biết", () => {
    const writes = ["POST links"];
    const all = [["POST", ["links"]], ["PUT", ["links"]], ["DELETE", ["me", "links"]], ["PATCH", ["me", "wallet"]]] as const;
    for (const [m, seg] of all) expect(isAllowed(m, [...seg]), `${m} ${seg.join("/")}`).toBe(writes.includes(`${m} ${seg.join("/")}`));
  });
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
    expect(isAllowed("GET", ["admin", "agent-keys"])).toBe(false);
    expect(isAllowed("GET", ["auth", "login"])).toBe(false);
    for (const bad of [["me", "..", "wallet"], ["..", "me", "wallet"], ["me", "%2e%2e"], ["me\\wallet"], ["me", ""], ["me/wallet"]]) {
      expect(isAllowed("GET", bad)).toBe(false);
    }
  });
});

describe("cookies", () => {
  it("HttpOnly, access Lax, refresh Strict, đúng Path và Max-Age", () => {
    const [a, r] = sessionCookies(TOK(1));
    expect(a).toMatch(/^access=NEW\.access\.1; Path=\/; Max-Age=900; HttpOnly; SameSite=Lax$/);
    expect(r).toMatch(/Path=\/bff; Max-Age=2592000; HttpOnly; SameSite=Strict$/);
    expect(a).not.toMatch(/Secure/);
  });
  it("xóa cookie giữ nguyên SameSite của từng loại", () => {
    const [a, r] = clearCookies();
    expect(a).toMatch(/Max-Age=0; HttpOnly; SameSite=Lax$/);
    expect(r).toMatch(/Max-Age=0; HttpOnly; SameSite=Strict$/);
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
    expect((await handleProxy(req("GET", "/x", { cookie: withTokens }), ["admin", "agent-keys"], f)).status).toBe(404);
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

describe("T-017: IP thật của khách gửi sang backend", () => {
  const SECRET = "bff-secret-0123456789abcdef";
  const reqWith = (method: string, path: string, extra: Record<string, string>, cookie?: string) => {
    const headers: Record<string, string> = { ...extra };
    if (cookie) headers.cookie = cookie;
    if (method !== "GET") { headers["x-csrf"] = "1"; headers.origin = ORIGIN; headers["content-type"] = "application/json"; }
    return new Request(`${ORIGIN}${path}`, { method, headers, body: method === "GET" ? undefined : "{}" });
  };
  const okTokens = () => ({ json: TOK(1) });

  it("có secret + CF-Connecting-IP hợp lệ: gửi X-Visitor-IP và X-BFF-Secret (đăng nhập)", async () => {
    vi.stubEnv("BFF_SHARED_SECRET", SECRET);
    const { f, calls } = fakeApi(okTokens);
    await handleAuth(reqWith("POST", "/bff/auth/login", { "cf-connecting-ip": "198.51.100.7" }), "login", f);
    expect(calls[0].headers["x-visitor-ip"]).toBe("198.51.100.7");
    expect(calls[0].headers["x-bff-secret"]).toBe(SECRET);
  });
  it("gửi cả khi gọi qua proxy và khi tự làm mới token", async () => {
    vi.stubEnv("BFF_SHARED_SECRET", SECRET);
    const { f, calls } = fakeApi((c) => (c.url.endsWith("auth/refresh") ? okTokens() : { json: { ok: 1 } }));
    await handleProxy(reqWith("GET", "/bff/api/me/links", { "cf-connecting-ip": "2001:db8::1" }, refreshOnly), ["me", "links"], f);
    expect(calls.length).toBe(2);
    for (const c of calls) { expect(c.headers["x-visitor-ip"]).toBe("2001:db8::1"); expect(c.headers["x-bff-secret"]).toBe(SECRET); }
  });
  it("không có secret thì không gửi gì (backend dùng IP kết nối)", async () => {
    const { f, calls } = fakeApi(okTokens);
    await handleAuth(reqWith("POST", "/bff/auth/login", { "cf-connecting-ip": "198.51.100.7" }), "login", f);
    expect(calls[0].headers["x-visitor-ip"]).toBeUndefined();
    expect(calls[0].headers["x-bff-secret"]).toBeUndefined();
  });
  it("IP thiếu hoặc sai định dạng thì không gửi", async () => {
    vi.stubEnv("BFF_SHARED_SECRET", SECRET);
    for (const ip of [undefined, "not-an-ip", "1.2.3.4, 5.6.7.8", "999.1.1.1", ""]) {
      const { f, calls } = fakeApi(okTokens);
      await handleAuth(reqWith("POST", "/bff/auth/login", ip === undefined ? {} : { "cf-connecting-ip": ip }), "login", f);
      expect(calls[0].headers["x-visitor-ip"], String(ip)).toBeUndefined();
      expect(calls[0].headers["x-bff-secret"], String(ip)).toBeUndefined();
    }
  });
  it("header X-Visitor-IP / X-BFF-Secret do khách tự gửi tới BFF không bao giờ được chuyển tiếp", async () => {
    vi.stubEnv("BFF_SHARED_SECRET", SECRET);
    const forged = { "x-visitor-ip": "6.6.6.6", "x-bff-secret": "forged", "cf-connecting-ip": "198.51.100.7" };
    const { f, calls } = fakeApi(okTokens);
    await handleAuth(reqWith("POST", "/bff/auth/login", forged), "login", f);
    expect(calls[0].headers["x-visitor-ip"]).toBe("198.51.100.7");
    expect(calls[0].headers["x-bff-secret"]).toBe(SECRET);
    vi.unstubAllEnvs(); vi.stubEnv("API_BASE_URL", "http://api.test");   // không secret: header giả cũng không lọt
    const second = fakeApi(okTokens);
    await handleAuth(reqWith("POST", "/bff/auth/login", forged), "login", second.f);
    expect(second.calls[0].headers["x-visitor-ip"]).toBeUndefined();
    expect(second.calls[0].headers["x-bff-secret"]).toBeUndefined();
  });
  it("secret không bao giờ xuất hiện trong phản hồi trả cho trình duyệt", async () => {
    vi.stubEnv("BFF_SHARED_SECRET", SECRET);
    const { f } = fakeApi(okTokens);
    const r = await handleAuth(reqWith("POST", "/bff/auth/login", { "cf-connecting-ip": "198.51.100.7" }), "login", f);
    expect(JSON.stringify([...r.headers.entries()]) + (await r.text())).not.toContain(SECRET);
  });
});


describe("cảnh báo BFF_SHARED_SECRET thiếu/ngắn", () => {
  it("trạng thái và cảnh báo theo độ dài secret, không lộ giá trị", () => {
    expect(visitorIpStatus()).toBe("missing_secret");
    expect(startupWarnings()).toHaveLength(1);
    vi.stubEnv("BFF_SHARED_SECRET", "short-secret");
    expect(visitorIpStatus()).toBe("short_secret");
    expect(startupWarnings()[0]).toContain("quá ngắn");
    expect(startupWarnings().join("")).not.toContain("short-secret");
    vi.stubEnv("BFF_SHARED_SECRET", "x".repeat(15)); expect(visitorIpStatus()).toBe("short_secret");
    vi.stubEnv("BFF_SHARED_SECRET", "x".repeat(16)); expect(visitorIpStatus()).toBe("ok");
    expect(startupWarnings()).toEqual([]);
  });
  it("/bff/health báo degraded khi thiếu secret và không lộ secret khi đủ", async () => {
    let j = await handleHealth().json();
    expect(j).toMatchObject({ ok: true, visitor_ip: "missing_secret", degraded: true });
    expect(j.warnings).toHaveLength(1);
    vi.stubEnv("BFF_SHARED_SECRET", "z".repeat(20));
    const r = handleHealth();
    const text = await r.text();
    j = JSON.parse(text);
    expect(j).toMatchObject({ visitor_ip: "ok", degraded: false, warnings: [] });
    expect(text).not.toContain("zzzz");
  });
  it("instrumentation: production cảnh báo qua console.warn; dev im lặng", async () => {
    const { register } = await import("../src/instrumentation");
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    vi.stubEnv("NODE_ENV", "development"); await register();
    expect(warn).not.toHaveBeenCalled();
    vi.stubEnv("NODE_ENV", "production"); await register();
    expect(warn).toHaveBeenCalledTimes(1);
    expect(String(warn.mock.calls[0][0])).toContain("BFF_SHARED_SECRET");
    vi.stubEnv("BFF_SHARED_SECRET", "x".repeat(16)); warn.mockClear(); await register();
    expect(warn).not.toHaveBeenCalled();
    warn.mockRestore();
  });
});

describe("T-041: allowlist tường minh cho rút tiền, admin, TOTP", () => {
  const ok: [string, string[]][] = [
    ["GET", ["me", "bank-accounts"]], ["POST", ["me", "bank-accounts"]], ["GET", ["me", "withdrawals"]], ["POST", ["me", "withdrawals"]],
    ["GET", ["me", "withdrawals", "rules"]], ["GET", ["auth", "mfa", "status"]], ["POST", ["auth", "mfa", "setup"]],
    ["POST", ["auth", "mfa", "enable"]], ["POST", ["auth", "mfa", "disable"]], ["GET", ["admin", "withdrawals"]],
    ["GET", ["admin", "withdrawals", "export.csv"]], ["POST", ["admin", "withdrawals", "7", "approve"]],
    ["POST", ["admin", "withdrawals", "7", "reject"]], ["POST", ["admin", "withdrawals", "123456789012", "fail"]],
    ["POST", ["admin", "withdrawals", "10", "mark-paid"]], ["GET", ["admin", "withdrawals", "7", "payout-account"]],
    ["GET", ["admin", "overview"]], ["GET", ["admin", "users"]], ["PATCH", ["admin", "users", "5"]], ["GET", ["admin", "orders"]],
    ["GET", ["admin", "orphans"]], ["POST", ["admin", "orphans", "9", "assign"]], ["PUT", ["admin", "shopee-session"]],
    ["GET", ["admin", "shopee-session", "status"]], ["GET", ["admin", "health"]], ["GET", ["admin", "reconciliation"]], ["GET", ["admin", "ledger-integrity"]],
    ["GET", ["admin", "fraud-flags"]], ["POST", ["admin", "fraud-flags", "9", "resolve"]],
  ];
  const no: [string, string[]][] = [
    ["GET", ["admin", "withdrawals", "7", "approve"]], ["POST", ["admin", "withdrawals", "7", "payout-account"]],
    ["DELETE", ["admin", "withdrawals", "7"]], ["PUT", ["me", "withdrawals"]], ["PATCH", ["me", "bank-accounts"]],
    ["POST", ["admin", "withdrawals", "abc", "approve"]], ["POST", ["admin", "withdrawals", "0", "approve"]],
    ["POST", ["admin", "withdrawals", "07", "approve"]], ["POST", ["admin", "withdrawals", "1234567890123", "approve"]],
    ["POST", ["admin", "withdrawals", "-1", "approve"]], ["POST", ["admin", "withdrawals", "1.5", "approve"]],
    ["POST", ["admin", "withdrawals", "1e3", "approve"]], ["POST", ["admin", "withdrawals", "7", "approve", "x"]],
    ["POST", ["admin", "withdrawals", "7%2f..", "approve"]], ["POST", ["admin", "withdrawals", "..", "approve"]],
    ["POST", ["admin", "withdrawals", "7", "delete"]], ["POST", ["admin", "fraud-flags"]], ["GET", ["admin", "fraud-flags", "9", "resolve"]], ["POST", ["admin", "fraud-flags", "x", "resolve"]], ["DELETE", ["admin", "fraud-flags", "9"]], ["GET", ["admin", "agent-keys"]], ["GET", ["admin", "audit-logs"]],
    ["POST", ["auth", "mfa", "verify"]], ["POST", ["auth", "login"]], ["POST", ["admin", "withdrawals", "export.csv"]],
    ["POST", ["me", "withdrawals", "rules"]], ["POST", ["auth", "mfa", "status"]], ["GET", ["auth", "mfa", "setup"]],
    ["GET", ["admin", "withdrawals", "7"]], ["GET", ["admin", "withdrawals", "export.csv", "x"]],
    ["POST", ["admin", "overview"]], ["GET", ["admin", "users", "5"]], ["PUT", ["admin", "users", "5"]], ["DELETE", ["admin", "users", "5"]],
    ["PATCH", ["admin", "users", "abc"]], ["PATCH", ["admin", "users", "0"]], ["POST", ["admin", "orders"]], ["GET", ["admin", "orphans", "9", "assign"]],
    ["POST", ["admin", "orphans", "x", "assign"]], ["GET", ["admin", "shopee-session"]], ["POST", ["admin", "shopee-session"]],
    ["GET", ["admin", "shopee-session", "cookie"]], ["POST", ["admin", "health"]], ["POST", ["admin", "reconciliation"]], ["PUT", ["admin", "ledger-integrity"]],
    ["GET", ["admin", "health", "x"]], ["GET", ["auth", "forgot"]], ["POST", ["auth", "reset"]], ["POST", ["auth", "verify"]], ["POST", ["admin", "shopee-session", "status"]], ["GET", ["admin", "agent-keys"]],
  ];
  it.each(ok)("cho qua %s %j", (m, segs) => expect(isAllowed(m, segs)).toBe(true));
  it.each(no)("chặn %s %j", (m, segs) => expect(isAllowed(m, segs)).toBe(false));

  const post = (path: string, headers: Record<string, string> = {}, cookie = withTokens) =>
    new Request(`${ORIGIN}${path}`, { method: "POST", headers: { cookie, "x-csrf": "1", origin: ORIGIN, "content-type": "application/json", ...headers }, body: "{}" });
  const KEY = "abcd1234-efgh-5678";

  it("POST me/withdrawals bắt buộc Idempotency-Key hợp lệ và chuyển tiếp đúng giá trị đó", async () => {
    for (const bad of [undefined, "", "short", "has space in it 123", "caf\u00e9-12345678", "a".repeat(101), "bad/slash-123456"]) {
      const { f, calls } = fakeApi(() => ({ json: {} }));
      const r = await handleProxy(post("/bff/api/me/withdrawals", bad === undefined ? {} : { "idempotency-key": bad }), ["me", "withdrawals"], f);
      expect(r.status, String(bad)).toBe(400);
      expect((await r.json()).error.code).toBe("idempotency_key_required");
      expect(calls).toHaveLength(0);                                              // không gọi backend
    }
    const { f, calls } = fakeApi(() => ({ status: 201, json: { id: 1 } }));
    const r = await handleProxy(post("/bff/api/me/withdrawals", { "idempotency-key": KEY }), ["me", "withdrawals"], f);
    expect(r.status).toBe(201);
    expect(calls[0].headers["idempotency-key"]).toBe(KEY);
  });
  it("Idempotency-Key vẫn được gửi khi BFF phải làm mới token trước", async () => {
    const { f, calls } = fakeApi((c) => (c.url.endsWith("auth/refresh") ? { json: TOK(1) } : { status: 201, json: { id: 1 } }));
    await handleProxy(post("/bff/api/me/withdrawals", { "idempotency-key": KEY }, refreshOnly), ["me", "withdrawals"], f);
    expect(calls.map((c) => c.url.split("/api/v1/")[1])).toEqual(["auth/refresh", "me/withdrawals"]);
    expect(calls[1].headers["idempotency-key"]).toBe(KEY);
    expect(calls[0].headers["idempotency-key"]).toBeUndefined();
  });
  it("route khác không chuyển tiếp Idempotency-Key do khách gửi", async () => {
    const { f, calls } = fakeApi(() => ({ json: {} }));
    await handleProxy(post("/bff/api/me/bank-accounts", { "idempotency-key": KEY }), ["me", "bank-accounts"], f);
    await handleProxy(post("/bff/api/admin/withdrawals/7/approve", { "idempotency-key": KEY }), ["admin", "withdrawals", "7", "approve"], f);
    expect(calls).toHaveLength(2);
    for (const c of calls) expect(c.headers["idempotency-key"]).toBeUndefined();
  });
  it("route admin: gửi Bearer, chuyển nguyên 403 mfa_required, chuyển Content-Disposition của CSV, không lộ Set-Cookie", async () => {
    const { f, calls } = fakeApi(() => ({ status: 403, json: { error: { code: "mfa_required", message: "cần TOTP", request_id: "r" } }, headers: { "set-cookie": "x=1" } }));
    const r = await handleProxy(new Request(`${ORIGIN}/bff/api/admin/withdrawals`, { headers: { cookie: withTokens } }), ["admin", "withdrawals"], f);
    expect(r.status).toBe(403);
    expect((await r.json()).error.code).toBe("mfa_required");
    expect(r.headers.get("set-cookie")).toBeNull();
    expect(calls[0].headers.authorization).toBe(`Bearer ${ACCESS}`);
    const csv = fakeApi(() => ({ status: 200, headers: { "content-type": "text/csv; charset=utf-8", "content-disposition": 'attachment; filename="cashback-payouts.csv"', "x-row-count": "2" } }));
    const c = await handleProxy(new Request(`${ORIGIN}/bff/api/admin/withdrawals/export.csv`, { headers: { cookie: withTokens } }), ["admin", "withdrawals", "export.csv"], csv.f);
    expect(c.headers.get("content-disposition")).toContain("attachment");
    expect(c.headers.get("x-row-count")).toBe("2");
    expect(c.headers.get("cache-control")).toBe("no-store");
  });
  it("admin gọi sai id (không phải số) bị chặn trước khi tới backend", async () => {
    const { f, calls } = fakeApi(() => ({ json: {} }));
    const r = await handleProxy(post("/bff/api/admin/withdrawals/abc/approve"), ["admin", "withdrawals", "abc", "approve"], f);
    expect(r.status).toBe(404);
    expect(calls).toHaveLength(0);
  });
});

describe("T-041: /bff/auth/mfa-verify đổi cookie sang phiên đã xác minh hai lớp", () => {
  const verifyReq = (cookie = withTokens, extra: Record<string, string> = {}) =>
    new Request(`${ORIGIN}/bff/auth/mfa-verify`, { method: "POST", headers: { cookie, "x-csrf": "1", origin: ORIGIN, "content-type": "application/json", ...extra }, body: JSON.stringify({ code: "123456" }) });

  it("thành công: đặt cặp cookie mới (access Lax, refresh Strict), không trả token ra ngoài", async () => {
    const { f, calls } = fakeApi(() => ({ json: TOK(9) }));
    const r = await handleAuth(verifyReq(), "mfa-verify", f);
    expect(r.status).toBe(200);
    const text = await r.text();
    expect(JSON.parse(text)).toEqual({ ok: true });
    expect(text).not.toContain("NEW.access");
    const cookies = setCookies(r);
    expect(cookies).toHaveLength(2);
    expect(cookies[0]).toContain("NEW.access.9");
    expect(cookies[0]).toContain("SameSite=Lax");
    expect(cookies[1]).toContain("SameSite=Strict");
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toContain("/api/v1/auth/mfa/verify");
    expect(calls[0].headers.authorization).toBe(`Bearer ${ACCESS}`);
    expect(calls[0].body).toBe(JSON.stringify({ code: "123456" }));
  });
  it("sai mã: chuyển nguyên lỗi 401 mfa_invalid, KHÔNG đổi cookie, UI không coi là hết phiên", async () => {
    const { f } = fakeApi(() => ({ status: 401, json: { error: { code: "mfa_invalid", message: "Mã không đúng", request_id: "r" } } }));
    const r = await handleAuth(verifyReq(), "mfa-verify", f);
    expect(r.status).toBe(401);
    expect((await r.json()).error.code).toBe("mfa_invalid");
    expect(setCookies(r)).toHaveLength(0);
  });
  it("access hết hạn nhưng còn refresh: làm mới trước rồi mới xác minh bằng access mới", async () => {
    const { f, calls } = fakeApi((c) => (c.url.endsWith("auth/refresh") ? { json: TOK(1) } : { json: TOK(2) }));
    const r = await handleAuth(verifyReq(refreshOnly), "mfa-verify", f);
    expect(r.status).toBe(200);
    expect(calls.map((c) => c.url.split("/api/v1/")[1])).toEqual(["auth/refresh", "auth/mfa/verify"]);
    expect(calls[1].headers.authorization).toBe("Bearer NEW.access.1");
    expect(setCookies(r)[0]).toContain("NEW.access.2");                               // cookie cuối là cặp từ verify
  });
  it("không có token nào: 401 và xóa cookie, không gọi backend", async () => {
    const { f, calls } = fakeApi(() => ({ json: TOK(1) }));
    const r = await handleAuth(verifyReq(""), "mfa-verify", f);
    expect(r.status).toBe(401);
    expect(calls).toHaveLength(0);
    expect(setCookies(r).every((c) => c.includes("Max-Age=0"))).toBe(true);
  });
  it("bắt buộc X-CSRF/Origin/JSON như mọi thao tác ghi", async () => {
    const { f, calls } = fakeApi(() => ({ json: TOK(1) }));
    const noCsrf = new Request(`${ORIGIN}/bff/auth/mfa-verify`, { method: "POST", headers: { cookie: withTokens, origin: ORIGIN, "content-type": "application/json" }, body: "{}" });
    expect((await handleAuth(noCsrf, "mfa-verify", f)).status).toBe(403);
    expect((await handleAuth(verifyReq(withTokens, { origin: "https://evil.test" }), "mfa-verify", f)).status).toBe(403);
    expect(calls).toHaveLength(0);
  });
  it("gửi IP khách cho backend khi có BFF_SHARED_SECRET (giới hạn thử mã theo IP)", async () => {
    vi.stubEnv("BFF_SHARED_SECRET", "s".repeat(20));
    const { f, calls } = fakeApi(() => ({ json: TOK(1) }));
    await handleAuth(verifyReq(withTokens, { "cf-connecting-ip": "198.51.100.7" }), "mfa-verify", f);
    expect(calls[0].headers["x-visitor-ip"]).toBe("198.51.100.7");
  });
});


describe("khôi phục tài khoản qua /bff/auth/* (công khai)", () => {
  const post = (action: string, body: unknown, o: { cookie?: string; csrf?: boolean; headers?: Record<string, string> } = {}) =>
    new Request(`${ORIGIN}/bff/auth/${action}`, { method: "POST", headers: { ...(o.cookie ? { cookie: o.cookie } : {}), ...(o.csrf === false ? {} : { "x-csrf": "1" }), origin: ORIGIN, "content-type": "application/json", ...(o.headers ?? {}) }, body: JSON.stringify(body) });
  const targets: [string, string][] = [["forgot", "auth/forgot"], ["resend-verification", "auth/verify/resend"], ["verify-email", "auth/verify"], ["reset", "auth/reset"]];

  it.each(targets)("%s chuyển tiếp thân yêu cầu tới %s, không cần cookie, không gắn Bearer", async (action, path) => {
    const { f, calls } = fakeApi(() => ({ status: action === "forgot" || action === "resend-verification" ? 202 : 204 }));
    const body = { email: "a@b.c", token: "t".repeat(30), password: "mat-khau-moi-1234" };
    const r = await handleAuth(post(action, body), action, f);
    expect(r.status).toBe(action === "forgot" || action === "resend-verification" ? 202 : 204);
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe(`http://api.test/api/v1/${path}`);
    expect(calls[0].method).toBe("POST");
    expect(calls[0].body).toBe(JSON.stringify(body));
    expect(calls[0].headers.authorization).toBeUndefined();
  });
  it("bắt buộc X-CSRF/Origin/JSON, và chỉ nhận POST", async () => {
    const { f, calls } = fakeApi(() => ({ status: 204 }));
    for (const [action] of targets) {
      expect((await handleAuth(post(action, {}, { csrf: false }), action, f)).status).toBe(403);
      expect((await handleAuth(post(action, {}, { headers: { origin: "https://evil.test" } }), action, f)).status).toBe(403);
    }
    expect((await handleAuth(new Request(`${ORIGIN}/bff/auth/forgot`, { method: "GET" }), "forgot", f)).status).toBe(405);
    expect(calls).toHaveLength(0);
  });
  it("đặt lại mật khẩu thành công xóa cookie của trình duyệt này; thất bại thì không", async () => {
    const ok = fakeApi(() => ({ status: 204 }));
    const r = await handleAuth(post("reset", { token: "t".repeat(30), password: "mat-khau-moi-1234" }, { cookie: withTokens }), "reset", ok.f);
    expect(setCookies(r)).toHaveLength(2);
    expect(setCookies(r).every((c) => c.includes("Max-Age=0"))).toBe(true);
    const bad = fakeApi(() => ({ status: 400, json: { error: { code: "invalid_token", message: "x", request_id: "r" } } }));
    const r2 = await handleAuth(post("reset", { token: "t".repeat(30), password: "mat-khau-moi-1234" }, { cookie: withTokens }), "reset", bad.f);
    expect(r2.status).toBe(400);
    expect((await r2.json()).error.code).toBe("invalid_token");
    expect(setCookies(r2)).toHaveLength(0);
    const other = await handleAuth(post("forgot", { email: "a@b.c" }, { cookie: withTokens }), "forgot", fakeApi(() => ({ status: 202 })).f);
    expect(setCookies(other)).toHaveLength(0);                                      // chỉ `reset` xóa cookie
    const verify = await handleAuth(post("verify-email", { token: "t".repeat(30) }, { cookie: withTokens }), "verify-email", fakeApi(() => ({ status: 204 })).f);
    expect(setCookies(verify)).toHaveLength(0);
  });
  it("gửi IP khách cho backend (giới hạn tốc độ quên mật khẩu theo IP) và không thêm hành động lạ", async () => {
    vi.stubEnv("BFF_SHARED_SECRET", "s".repeat(20));
    const { f, calls } = fakeApi(() => ({ status: 202 }));
    await handleAuth(post("forgot", { email: "a@b.c" }, { headers: { "cf-connecting-ip": "198.51.100.7" } }), "forgot", f);
    expect(calls[0].headers["x-visitor-ip"]).toBe("198.51.100.7");
    for (const unknown of ["verify", "password", "reset/", "Forgot", "forgot "]) expect((await handleAuth(post(unknown, {}), unknown, f)).status).toBe(404);
    expect(calls).toHaveLength(1);
  });
});
