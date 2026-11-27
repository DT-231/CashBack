/** Luật của ADR 0005 cho giao diện: UI không tự tính tiền; component không gọi fetch trực tiếp. Quét mã nguồn UI. */
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { formatDateTime, formatPercent, formatVnd } from "@/lib/format";

const SRC = path.resolve(__dirname, "../src");
const SKIP = [path.join("lib", "bff"), path.join("app", "bff"), path.join("lib", "api-client.ts"), path.join("lib", "format.ts")];

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = path.join(dir, n);
    return statSync(p).isDirectory() ? files(p) : /\.(ts|tsx)$/.test(n) && !/\.test\./.test(n) ? [p] : [];
  });
}
const ui = files(SRC).filter((f) => !SKIP.some((s) => f.includes(s)));
const FORBIDDEN: [RegExp, string][] = [
  [/_vnd\b\s*[*/+\-]=?\s*[\w.(]/, "phép tính trên số tiền (*_vnd)"],
  [/[\w.)\]]\s*[*/+\-]=?\s*[\w.]*_vnd\b/, "phép tính trên số tiền (*_vnd)"],
  [/share_pct\s*[*/+\-]|[*/+\-]\s*[\w.]*share_pct/, "tính với share_pct"],
  [/hold_days|\bholdDays\b/, "tự cộng số ngày giữ"],
  [/\*\s*0?\.6\b|\b60\s*\/\s*100\b|\b0?\.4\b\s*\*/, "tự nhân tỷ lệ chia"],
  [/\b(pending|available|held)_vnd\b[^\n]*\b(reduce|sum)\b|\b(reduce|sum)\b[^\n]*\bamount_vnd\b/, "cộng dồn số tiền"],
  [/Math\.(round|floor|ceil)\([^)]*_vnd/, "làm tròn số tiền"],
  [/\bfetch\s*\(/, "gọi fetch trực tiếp (dùng lib/api-client.ts)"],
];

describe("UI không tự tính tiền, không tự gọi backend", () => {
  it("quét mã nguồn UI", () => {
    const bad: string[] = [];
    for (const f of ui) {
      const text = readFileSync(f, "utf8");
      for (const [re, why] of FORBIDDEN) if (re.test(text)) bad.push(`${path.relative(SRC, f)}: ${why}`);
    }
    expect(bad).toEqual([]);
  });
  it("bộ quét thật sự bắt được vi phạm (kiểm tra chính nó)", () => {
    const samples = ["const x = w.pending_vnd * 0.6;", "total = a.amount_vnd + b.amount_vnd", "x = w.share_pct / 100", "d.setDate(d.getDate() + holdDays)",
      "entries.reduce((s, e) => s + e.amount_vnd, 0)", "Math.floor(w.available_vnd)", "await fetch('/x')"];
    for (const s of samples) expect(FORBIDDEN.some(([re]) => re.test(s)), s).toBe(true);
    for (const ok of ["formatVnd(w.pending_vnd)", "<td>{formatVnd(e.amount_vnd)}</td>", "const rows = entries.map((e) => e.id)"]) {
      expect(FORBIDDEN.some(([re]) => re.test(ok)), ok).toBe(false);
    }
  });
});

describe("format", () => {
  it("chỉ định dạng", () => {
    expect(formatVnd(24225).replace(/\s/g, " ")).toBe("24.225 ₫");
    expect(formatVnd(0)).toContain("0");
    expect(formatPercent(60)).toBe("60%");
    expect(formatDateTime("không phải ngày")).toBe("");
    expect(formatDateTime("2100-01-02T03:04:00Z")).toBe("10:04 02/01/2100");   // locale vi-VN viết giờ trước; đủ 4 chữ số năm; giờ Việt Nam (UTC+7)
  });
});
