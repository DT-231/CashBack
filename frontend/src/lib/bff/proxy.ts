/** /bff/api/<path>: chuyển tiếp có danh sách cho phép, gắn Bearer từ cookie, tự làm mới token tối đa một lần. */
import { isAllowed } from "./allowlist";
import { checkCsrf } from "./csrf";
import { clearCookies, readTokens, sessionCookies } from "./cookies";
import { errorResponse } from "./errors";
import { callApi, type Fetch, passThrough, refreshTokens } from "./upstream";

const expired = () => errorResponse(401, "session_expired", "Phiên đăng nhập đã hết hạn", clearCookies());

export async function handleProxy(request: Request, segments: string[], f: Fetch = fetch): Promise<Response> {
  const fail = checkCsrf(request);
  if (fail) return errorResponse(403, fail.code, fail.message);
  if (!isAllowed(request.method, segments)) return errorResponse(404, "not_found", "Không tìm thấy");

  const { access, refresh } = readTokens(request);
  let token = access;
  let setCookies: string[] = [];
  if (!token) {                                   // access hết hạn (cookie tự mất): thử làm mới trước
    if (!refresh) return errorResponse(401, "unauthorized", "Chưa đăng nhập");
    const t = await refreshTokens(f, refresh);
    if (!t) return expired();
    token = t.access_token;
    setCookies = sessionCookies(t);
  }

  const body = request.method === "GET" ? undefined : await request.text();
  const rid = request.headers.get("x-request-id") ?? undefined;
  const path = segments.join("/") + new URL(request.url).search;
  let r = await callApi(f, request.method, path, { token, body, requestId: rid });
  if (r.status === 401 && refresh && setCookies.length === 0) {   // access bị từ chối: làm mới đúng MỘT lần rồi thử lại
    const t = await refreshTokens(f, refresh);
    if (!t) return expired();
    setCookies = sessionCookies(t);
    r = await callApi(f, request.method, path, { token: t.access_token, body, requestId: rid });
  }
  return passThrough(r, setCookies);
}
