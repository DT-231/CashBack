/** Lỗi do chính BFF tạo ra, cùng định dạng với backend: {"error":{code,message,request_id}}. */
export function errorResponse(status: number, code: string, message: string, extra: string[] = []): Response {
  const h = new Headers({ "content-type": "application/json", "cache-control": "no-store" });
  for (const c of extra) h.append("set-cookie", c);
  return new Response(JSON.stringify({ error: { code, message, request_id: null } }), { status, headers: h });
}
