/**
 * Chỉ những (phương thức, đường dẫn) này được chuyển tiếp tới backend /api/v1. So khớp TƯỜNG MINH:
 * đường dẫn cố định so khớp chính xác; chỗ có id yêu cầu đúng một đoạn số nguyên dương (không wildcard, không `..`).
 * Route admin vẫn do backend kiểm role + TOTP; allowlist chỉ thu hẹp những gì trình duyệt được phép gọi.
 */
const ID = /^[1-9][0-9]{0,11}$/;

type Rule = { method: string; segments: ReadonlyArray<string | RegExp>; idempotent?: boolean };

const RULES: ReadonlyArray<Rule> = [
  { method: "POST", segments: ["links"] },
  { method: "GET", segments: ["me", "links"] },
  { method: "GET", segments: ["me", "wallet"] },
  { method: "GET", segments: ["me", "wallet", "entries"] },
  { method: "GET", segments: ["me", "orders"] },
  { method: "GET", segments: ["auth", "me"] },
  // Rút tiền (người dùng)
  { method: "GET", segments: ["me", "bank-accounts"] },
  { method: "POST", segments: ["me", "bank-accounts"] },
  { method: "GET", segments: ["me", "withdrawals"] },
  { method: "GET", segments: ["me", "withdrawals", "rules"] },
  { method: "POST", segments: ["me", "withdrawals"], idempotent: true },
  // Đăng nhập hai lớp (verify đi qua /bff/auth/mfa-verify vì phải đổi cookie)
  { method: "GET", segments: ["auth", "mfa", "status"] },
  { method: "POST", segments: ["auth", "mfa", "setup"] },
  { method: "POST", segments: ["auth", "mfa", "enable"] },
  { method: "POST", segments: ["auth", "mfa", "disable"] },
  // Admin: tổng quan, người dùng, đơn, đơn mồ côi, cookie Shopee (backend kiểm admin + TOTP)
  { method: "GET", segments: ["admin", "overview"] },
  { method: "GET", segments: ["admin", "users"] },
  { method: "PATCH", segments: ["admin", "users", ID] },
  { method: "GET", segments: ["admin", "orders"] },
  { method: "GET", segments: ["admin", "orphans"] },
  { method: "POST", segments: ["admin", "orphans", ID, "assign"] },
  { method: "PUT", segments: ["admin", "shopee-session"] },
  { method: "GET", segments: ["admin", "shopee-session", "status"] },
  // Admin: duyệt/chi trả
  { method: "GET", segments: ["admin", "withdrawals"] },
  { method: "GET", segments: ["admin", "withdrawals", "export.csv"] },
  { method: "POST", segments: ["admin", "withdrawals", ID, "approve"] },
  { method: "POST", segments: ["admin", "withdrawals", ID, "reject"] },
  { method: "POST", segments: ["admin", "withdrawals", ID, "fail"] },
  { method: "POST", segments: ["admin", "withdrawals", ID, "mark-paid"] },
  { method: "GET", segments: ["admin", "withdrawals", ID, "payout-account"] },
];

function find(method: string, segments: string[]): Rule | undefined {
  if (segments.some((s) => s === "" || s === "." || s === ".." || /[\\/%]/.test(s))) return undefined;
  const m = method.toUpperCase();
  return RULES.find((r) => r.method === m && r.segments.length === segments.length
    && r.segments.every((p, i) => (typeof p === "string" ? p === segments[i] : p.test(segments[i]))));
}

export function isAllowed(method: string, segments: string[]): boolean {
  return find(method, segments) !== undefined;
}

/** Route này BẮT BUỘC có header Idempotency-Key (chống bấm hai lần). */
export function requiresIdempotencyKey(method: string, segments: string[]): boolean {
  return find(method, segments)?.idempotent === true;
}

export const IDEMPOTENCY_KEY = /^[A-Za-z0-9_-]{8,100}$/;
