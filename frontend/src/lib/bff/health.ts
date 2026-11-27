/** GET /bff/health: không cần đăng nhập, không lộ secret, chỉ trạng thái. */
import { startupWarnings, visitorIpStatus } from "./config";

export function handleHealth(): Response {
  const warnings = startupWarnings();
  return new Response(JSON.stringify({ ok: true, visitor_ip: visitorIpStatus(), degraded: warnings.length > 0, warnings }), {
    status: 200, headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}
