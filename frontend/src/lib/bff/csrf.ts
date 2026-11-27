/** Chống CSRF cho mọi phương thức ghi: SameSite=Strict (ở cookie) cộng kiểm tra tại đây. */
const SAFE = new Set(["GET", "HEAD", "OPTIONS"]);

export type CsrfFailure = { code: string; message: string } | null;

export function checkCsrf(request: Request): CsrfFailure {
  if (SAFE.has(request.method.toUpperCase())) return null;
  if (request.headers.get("x-csrf") !== "1") return { code: "csrf", message: "Thiếu header X-CSRF" };
  const origin = request.headers.get("origin");
  if (!origin || origin !== new URL(request.url).origin) return { code: "csrf", message: "Origin không hợp lệ" };
  const ct = (request.headers.get("content-type") ?? "").toLowerCase();
  if (!ct.startsWith("application/json")) return { code: "csrf", message: "Chỉ nhận application/json" };
  return null;
}
