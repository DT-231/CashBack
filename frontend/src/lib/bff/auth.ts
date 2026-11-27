/** /bff/auth/{register,login,logout}. Backend trả token trong body; BFF đổi thành cookie HttpOnly và KHÔNG trả token ra ngoài. */
import { checkCsrf } from "./csrf";
import { clearCookies, readTokens, sessionCookies, type Tokens } from "./cookies";
import { errorResponse } from "./errors";
import { callApi, type Fetch, passThrough, refreshTokens, visitorHeaders } from "./upstream";

export async function handleAuth(request: Request, action: string, f: Fetch = fetch): Promise<Response> {
  if (request.method !== "POST") return errorResponse(405, "method_not_allowed", "Phương thức không được hỗ trợ");
  const fail = checkCsrf(request);
  if (fail) return errorResponse(403, fail.code, fail.message);
  const rid = request.headers.get("x-request-id") ?? undefined;
  const visitor = visitorHeaders(request);

  if (action === "register") {
    return passThrough(await callApi(f, "POST", "auth/register", { body: await request.text(), requestId: rid, visitor }));
  }
  if (action === "login") {
    const r = await callApi(f, "POST", "auth/login", { body: await request.text(), requestId: rid, visitor });
    if (!r.ok) return passThrough(r);
    const t = (await r.json()) as Tokens;
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: (() => {
        const h = new Headers({ "content-type": "application/json", "cache-control": "no-store" });
        for (const c of sessionCookies(t)) h.append("set-cookie", c);
        return h;
      })(),
    });
  }
  if (action === "mfa-verify") {
    // Backend trả cặp token MỚI có trạng thái đã xác minh hai lớp: BFF thay cookie, không trả token ra trình duyệt.
    const { access, refresh } = readTokens(request);
    let token = access;
    if (!token && refresh) token = (await refreshTokens(f, refresh, visitor))?.access_token;
    if (!token) return errorResponse(401, "unauthorized", "Chưa đăng nhập", clearCookies());
    const body = await request.text();
    const r = await callApi(f, "POST", "auth/mfa/verify", { token, body, requestId: rid, visitor });
    if (!r.ok) return passThrough(r);                      // mfa_invalid, mfa_state, rate_limited...: chuyển nguyên, KHÔNG đổi cookie
    const t = (await r.json()) as Tokens;
    const h = new Headers({ "content-type": "application/json", "cache-control": "no-store" });
    for (const c of sessionCookies(t)) h.append("set-cookie", c);
    return new Response(JSON.stringify({ ok: true }), { status: 200, headers: h });
  }
  if (action === "logout") {
    // Muốn thu hồi refresh token ở backend thì cần access token còn hạn: nếu hết hạn thì làm mới rồi mới đăng xuất.
    const { access, refresh } = readTokens(request);
    let token = access;
    if (!token && refresh) token = (await refreshTokens(f, refresh, visitor))?.access_token;
    if (token) await callApi(f, "POST", "auth/logout", { token, requestId: rid, visitor }).catch(() => undefined);
    const h = new Headers({ "cache-control": "no-store" });
    for (const c of clearCookies()) h.append("set-cookie", c);
    return new Response(null, { status: 204, headers: h });
  }
  return errorResponse(404, "not_found", "Không tìm thấy");
}
