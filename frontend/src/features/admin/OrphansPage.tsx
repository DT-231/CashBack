"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Alert, Button } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import type { AdminOrphan } from "@/lib/types";
import { formatDateTime, formatVnd } from "@/lib/format";

const LIMIT = 50;
const statusLabels: Record<string, string> = { PENDING: "Đang chờ", COMPLETED: "Hoàn thành", CANCELLED: "Đã hủy", RETURNED: "Đã hoàn trả" };
const validUserId = (value: string) => /^\d+$/.test(value) && Number.isSafeInteger(Number(value)) && Number(value) > 0;

export default function OrphansPage() {
  const router = useRouter();
  const [rows, setRows] = useState<AdminOrphan[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [userIds, setUserIds] = useState<Record<number, string>>({});
  const [reasons, setReasons] = useState<Record<number, string>>({});
  const [confirmId, setConfirmId] = useState<number | null>(null);
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
      const page = await api.adminOrphans({ limit: LIMIT, offset: 0 });
      setRows(page); setHasMore(page.length === LIMIT);
    } catch (cause) { handleError(cause, "Không thể tải đơn mồ côi."); }
    finally { setLoading(false); }
  }, [handleError]);

  useEffect(() => { void loadFirst(); }, [loadFirst]);

  async function loadMore() {
    if (pageLock.current) return;
    pageLock.current = true; setLoadingMore(true); setError("");
    try {
      const page = await api.adminOrphans({ limit: LIMIT, offset: rows.length });
      setRows((current) => [...current, ...page]); setHasMore(page.length === LIMIT);
    } catch (cause) { handleError(cause, "Không thể tải đơn mồ côi."); }
    finally { pageLock.current = false; setLoadingMore(false); }
  }

  function submit(event: FormEvent<HTMLFormElement>, row: AdminOrphan) {
    event.preventDefault();
    const rawId = userIds[row.id] ?? "";
    const reason = reasons[row.id] ?? "";
    if (!validUserId(rawId) || reason.trim().length < 3 || actionLock.current) return;
    setError(""); setNotice(""); setConfirmId(row.id);
  }

  async function assign(row: AdminOrphan) {
    if (actionLock.current) return;
    const userId = Number(userIds[row.id]);
    const reason = reasons[row.id] ?? "";
    actionLock.current = true; setBusy(true); setError(""); setNotice(""); setConfirmId(null);
    try {
      await api.adminAssignOrphan(row.id, userId, reason);
      await loadFirst();
      setNotice(`Đã gán đơn #${row.id} cho người dùng ${userId}`);
    } catch (cause) {
      if (cause instanceof ApiError && ["order_not_found", "not_an_orphan"].includes(cause.code)) {
        const message = cause.code === "order_not_found" ? "Không tìm thấy đơn, đã tải lại danh sách" : "Đơn này đã được xử lý ở nơi khác, đã tải lại danh sách";
        await loadFirst(); setError(message);
      } else if (cause instanceof ApiError && cause.code === "invalid_assignee") setError("Người dùng không hợp lệ (không tồn tại, bị khóa, hoặc là chính bạn)");
      else if (cause instanceof ApiError && cause.code === "forbidden") setError("Chỉ admin được thực hiện");
      else handleError(cause, "Không thể gán đơn.");
    } finally { actionLock.current = false; setBusy(false); }
  }

  return <main className="page"><section className="panel"><h1>Đơn mồ côi</h1>
    {error && <Alert>{error}</Alert>}{notice && <p role="status">{notice}</p>}
    {loading ? <p role="status">Đang tải đơn mồ côi…</p> : rows.length === 0 ? <p>Không có đơn mồ côi.</p> : <ul className="link-list orphan-list">{rows.map((row) => <li key={row.id}>
      <h2>#{row.id} · {row.order_sn}</h2><p>Trạng thái: {statusLabels[row.status] ?? row.status}</p><p>Hoa hồng: {formatVnd(row.commission_vnd)}</p>
      {row.purchase_time !== null && <p>Ngày mua: {formatDateTime(row.purchase_time)}</p>}<p>Lý do mồ côi: {row.reason}</p>
      <form onSubmit={(event) => submit(event, row)} aria-label={`Gán đơn #${row.id}`}>
        <label className="field" htmlFor={`orphan-user-${row.id}`}>ID người dùng<input id={`orphan-user-${row.id}`} inputMode="numeric" value={userIds[row.id] ?? ""} onChange={(event) => setUserIds((current) => ({ ...current, [row.id]: event.target.value }))} /></label>
        <label className="field" htmlFor={`orphan-reason-${row.id}`}>Lý do<input id={`orphan-reason-${row.id}`} value={reasons[row.id] ?? ""} onChange={(event) => setReasons((current) => ({ ...current, [row.id]: event.target.value }))} /></label>
        <Button type="submit" disabled={busy || !validUserId(userIds[row.id] ?? "") || (reasons[row.id] ?? "").trim().length < 3}>{busy ? "Đang gán…" : "Gán"}</Button>
      </form>
      {confirmId === row.id && <div className="orphan-confirm" role="group" aria-label="Xác nhận gán">
        <p>Gán đơn #{row.id} cho người dùng {Number(userIds[row.id])}? Người này sẽ nhận hoàn tiền của đơn.</p>
        <Button type="button" disabled={busy} onClick={() => void assign(row)}>Xác nhận gán</Button><Button type="button" className="secondary" disabled={busy} onClick={() => setConfirmId(null)}>Hủy</Button>
      </div>}
    </li>)}</ul>}
    {hasMore && <Button type="button" disabled={loadingMore} onClick={() => void loadMore()}>{loadingMore ? "Đang tải…" : "Xem thêm"}</Button>}
  </section></main>;
}
