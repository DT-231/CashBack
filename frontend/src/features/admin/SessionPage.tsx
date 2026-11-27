"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Alert, Button } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import type { ShopeeSessionStatus } from "@/lib/types";
import { formatDateTime } from "@/lib/format";

const statusLabels: Record<string, string> = { unknown: "Chưa rõ", healthy: "Hoạt động tốt", degraded: "Có vấn đề", expired: "Hết hạn", blocked: "Bị chặn" };

export default function SessionPage() {
  const router = useRouter();
  const [status, setStatus] = useState<ShopeeSessionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [cookie, setCookie] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const lock = useRef(false);

  function handleError(cause: unknown, fallback: string) {
    if (cause instanceof ApiError && cause.isAuth) router.replace("/login");
    else if (cause instanceof ApiError && cause.isMfaRequired) router.replace("/admin/mfa");
    else if (cause instanceof ApiError && cause.status === 0) setError("Không kết nối được máy chủ");
    else if (cause instanceof ApiError && cause.code === "invalid_cookie") setError("Cookie không hợp lệ (dạng a=b; c=d, tối đa 8KB)");
    else if (cause instanceof ApiError && cause.code === "not_configured") setError("Máy chủ chưa cấu hình khóa mã hóa (BANK_ENC_KEY)");
    else if (cause instanceof ApiError && cause.code === "forbidden") setError("Chỉ admin được thực hiện");
    else if (cause instanceof ApiError) setError(cookie ? cause.message.split(cookie).join("[đã ẩn]") : cause.message);
    else setError(fallback);
  }

  async function reload() {
    setLoading(true); setError("");
    try { setStatus(await api.adminShopeeSessionStatus()); }
    catch (cause) { handleError(cause, "Không thể tải trạng thái phiên Shopee."); }
    finally { setLoading(false); }
  }

  useEffect(() => { void reload(); return () => { setCookie(""); }; }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!cookie.trim() || lock.current) return;
    lock.current = true; setSaving(true); setError(""); setNotice("");
    try {
      await api.adminSetShopeeCookie(cookie);
      setCookie("");
      await reload();
      setNotice("Đã lưu cookie (không hiển thị lại)");
    } catch (cause) {
      setCookie("");
      handleError(cause, "Không thể lưu cookie.");
    } finally { lock.current = false; setSaving(false); }
  }

  return <main className="page"><section className="panel"><h1>Cookie Shopee</h1>
    {error && <Alert>{error}</Alert>}{notice && <p role="status">{notice}</p>}
    {loading && !status ? <p role="status">Đang tải trạng thái phiên…</p> : status && <section aria-label="Trạng thái phiên Shopee">
      <p>{status.has_cookie ? "Đã lưu cookie" : "Chưa có cookie"}</p><p>Trạng thái: {statusLabels[status.status] ?? status.status}</p>
      <p>Số lần lỗi liên tiếp: {status.failure_count}</p>
      {status.last_ok_at !== null && <p>Lần OK gần nhất: {formatDateTime(status.last_ok_at)}</p>}
      {status.updated_at !== null && <p>Cập nhật lúc: {formatDateTime(status.updated_at)}</p>}
    </section>}
    <form onSubmit={(event) => void submit(event)}>
      <label className="field" htmlFor="shopee-cookie">Dán cookie mới<textarea id="shopee-cookie" autoComplete="off" value={cookie} onChange={(event) => setCookie(event.target.value)} /></label>
      <Button type="submit" disabled={saving || !cookie.trim()}>{saving ? "Đang lưu…" : "Lưu cookie"}</Button>
    </form>
  </section></main>;
}
