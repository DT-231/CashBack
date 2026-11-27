/** Chỉ những đường dẫn này (so khớp CHÍNH XÁC, không wildcard) được chuyển tiếp tới backend /api/v1. */
const ALLOWED: ReadonlyArray<readonly [string, string]> = [
  ["POST", "links"],
  ["GET", "me/links"],
  ["GET", "me/wallet"],
  ["GET", "me/wallet/entries"],
  ["GET", "me/orders"],
  ["GET", "auth/me"],
];

export function isAllowed(method: string, segments: string[]): boolean {
  if (segments.some((s) => s === "" || s === "." || s === ".." || /[\\/%]/.test(s))) return false;
  const path = segments.join("/");
  return ALLOWED.some(([m, p]) => m === method.toUpperCase() && p === path);
}
