/** Chạy một lần khi server Next.js khởi động: cảnh báo rõ nếu BFF_SHARED_SECRET thiếu/ngắn (chỉ production, dev không ồn). */
export async function register() {
  if (process.env.NEXT_RUNTIME === "edge" || process.env.NODE_ENV !== "production") return;
  const { startupWarnings } = await import("@/lib/bff/config");
  for (const w of startupWarnings()) console.warn(`[bff] CẢNH BÁO: ${w}`);
}
