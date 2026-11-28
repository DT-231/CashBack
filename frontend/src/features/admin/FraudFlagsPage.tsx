"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Alert, Button } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import type { FraudFlag } from "@/lib/types";
import { formatDateTime } from "@/lib/format";

const LIMIT = 50;
const ruleLabels: Record<string, string> = { shared_ip: "Nhiều tài khoản cùng IP", high_cancel_rate: "Tỷ lệ hủy/hoàn cao", click_burst: "Click dồn dập" };
const statusLabels: Record<string, string> = { open: "Đang mở", dismissed: "Đã bỏ qua", confirmed: "Đã xác nhận" };
const detailLabels: Record<string, string> = { distinct_users: "Số tài khoản", orders: "Số đơn", cancelled_or_returned: "Hủy/hoàn", max_clicks_per_hour: "Click tối đa/giờ" };
const filters: [string, string][] = [["open", "Đang mở"], ["dismissed", "Đã bỏ qua"], ["confirmed", "Đã xác nhận"]];

export default function FraudFlagsPage() {
  const router = useRouter();
  const [status, setStatus] = useState("open");
  const [rows, setRows] = useState<FraudFlag[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState(false);
  const pageLock = useRef(false);
  const actionLock = useRef(false);

  const handleError = useCallback((cause: unknown, fallback: string) => {
    if (cause instanceof ApiError && cause.isAuth) router.replace("/login");
    else if (cause instanceof ApiError && cause.isMfaRequired) router.replace("/admin/mfa");
    else setError(cause instanceof ApiError && cause.status === 0 ? "Không kết nối được máy chủ" : cause instanceof ApiError ? cause.message : fallback);
  }, [router]);

  const loadFirst = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const page = await api.adminFraudFlags({ status, limit: LIMIT, offset: 0 });
      setRows(page); setHasMore(page.length === LIMIT);
    } catch (cause) { handleError(cause, "Không thể tải cờ gian lận."); }
    finally { setLoading(false); }
  }, [handleError, status]);

  useEffect(() => { void loadFirst(); }, [loadFirst]);

  async function loadMore() {
    if (pageLock.current) return;
    pageLock.current = true; setLoadingMore(true); setError("");
    try {
      const page = await api.adminFraudFlags({ status, limit: LIMIT, offset: rows.length });
      setRows((current) => [...current, ...page]); setHasMore(page.length === LIMIT);
    } catch (cause) { handleError(cause, "Không thể tải cờ gian lận."); }
    finally { pageLock.current = false; setLoadingMore(false); }
  }

  async function resolve(row: FraudFlag, decision: "dismissed" | "confirmed") {
    const note = (notes[row.id] ?? "").trim();
    if (note.length < 3 || actionLock.current) return;
    actionLock.current = true; setBusy(true); setError(""); setNotice("");
    try {
      await api.adminResolveFraudFlag(row.id, decision, note);
      await loadFirst();
      setNotice(`Đã xử lý cờ #${row.id}: ${statusLabels[decision]}`);
    } catch (cause) {
      if (cause instanceof ApiError && ["flag_not_found", "flag_closed"].includes(cause.code)) {
        await loadFirst(); setError(cause.code === "flag_closed" ? "Cờ này đã được xử lý ở nơi khác, đã tải lại danh sách" : "Không tìm thấy cờ, đã tải lại danh sách");
      } else if (cause instanceof ApiError && cause.code === "forbidden") setError("Chỉ admin được thực hiện");
      else handleError(cause, "Không thể xử lý cờ.");
    } finally { actionLock.current = false; setBusy(false); }
  }

  return <main className="page"><section className="panel"><h1>Cờ gian lận</h1>
    <nav aria-label="Lọc trạng thái">{filters.map(([value, label]) => <Button key={value} type="button" className={status === value ? undefined : "secondary"} aria-pressed={status === value} onClick={() => setStatus(value)}>{label}</Button>)}</nav>
    {error && <Alert>{error}</Alert>}{notice && <p role="status">{notice}</p>}
    {loading ? <p role="status">Đang tải cờ gian lận…</p> : rows.length === 0 ? <p>Không có cờ gian lận.</p> : <ul className="link-list">{rows.map((row) => <li key={row.id}>
      <h2>#{row.id} · {row.email}</h2><p>Người dùng: {row.user_id}</p><p>Luật: {ruleLabels[row.rule] ?? row.rule}</p><p>Điểm: {row.score}</p>
      <p>Trạng thái: {statusLabels[row.status] ?? row.status}</p>
      {Object.entries(row.detail ?? {}).map(([key, value]) => <p key={key}>{detailLabels[key] ?? key}: {String(value)}</p>)}
      <p>Tạo lúc: {formatDateTime(row.created_at)}</p>
      {row.resolved_at !== null && <p>Xử lý lúc: {formatDateTime(row.resolved_at)}</p>}
      {row.resolution_note !== null && <p>Ghi chú: {row.resolution_note}</p>}
      {row.status === "open" && <form onSubmit={(event: FormEvent) => event.preventDefault()} aria-label={`Xử lý cờ #${row.id}`}>
        <label className="field" htmlFor={`flag-note-${row.id}`}>Ghi chú (bắt buộc)<input id={`flag-note-${row.id}`} value={notes[row.id] ?? ""} onChange={(event) => setNotes((current) => ({ ...current, [row.id]: event.target.value }))} /></label>
        <Button type="button" disabled={busy || (notes[row.id] ?? "").trim().length < 3} onClick={() => void resolve(row, "dismissed")}>Bỏ qua</Button>
        <Button type="button" disabled={busy || (notes[row.id] ?? "").trim().length < 3} onClick={() => void resolve(row, "confirmed")}>Xác nhận gian lận</Button>
      </form>}
    </li>)}</ul>}
    {hasMore && <Button type="button" disabled={loadingMore} onClick={() => void loadMore()}>{loadingMore ? "Đang tải…" : "Xem thêm"}</Button>}
  </section></main>;
}
