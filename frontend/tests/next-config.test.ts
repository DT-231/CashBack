import { describe, expect, it } from "vitest";
import config from "../next.config";

describe("security headers (next.config.ts)", async () => {
  const rules = await config.headers!();
  const all = new Map(rules.filter((r) => r.source === "/(.*)").flatMap((r) => r.headers.map((h) => [h.key, h.value] as const)));

  it("áp dụng cho mọi đường dẫn", () => {
    expect(rules.some((r) => r.source === "/(.*)")).toBe(true);
  });
  it("chống nhúng khung, đoán MIME, rò Referer, mở cửa sổ chéo origin", () => {
    expect(all.get("X-Frame-Options")).toBe("DENY");
    expect(all.get("X-Content-Type-Options")).toBe("nosniff");
    expect(all.get("Referrer-Policy")).toBe("no-referrer");
    expect(all.get("Cross-Origin-Opener-Policy")).toBe("same-origin");
  });
  it("CSP cấm khung, <object>, đổi base, và form gửi đi origin khác", () => {
    const csp = all.get("Content-Security-Policy") ?? "";
    for (const d of ["frame-ancestors 'none'", "base-uri 'self'", "form-action 'self'", "object-src 'none'"]) expect(csp).toContain(d);
  });
  it("tắt các tính năng trình duyệt không dùng và bật HSTS", () => {
    const pp = all.get("Permissions-Policy") ?? "";
    for (const f of ["camera=()", "microphone=()", "geolocation=()", "payment=()"]) expect(pp).toContain(f);
    expect(all.get("Strict-Transport-Security")).toMatch(/max-age=\d{7,}/);
  });
  it("không lộ framework", () => {
    expect(config.poweredByHeader).toBe(false);
  });
});
