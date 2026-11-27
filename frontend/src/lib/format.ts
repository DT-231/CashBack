/** Chỉ ĐỊNH DẠNG để hiển thị. Không cộng/trừ/nhân/chia tiền hay ngày ở đây hay ở bất kỳ đâu trong UI. */
const vnd = new Intl.NumberFormat("vi-VN");

export function formatVnd(amount: number): string {
  return `${vnd.format(amount)} ₫`;
}

export function formatPercent(pct: number): string {
  return `${new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(pct)}%`;
}

export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
    hour12: false, timeZone: "Asia/Ho_Chi_Minh",
  }).format(d);
}
