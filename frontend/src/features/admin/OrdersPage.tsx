"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Alert, Button } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import type { AdminOrder } from "@/lib/types";
import { formatDateTime, formatVnd } from "@/lib/format";

const LIMIT = 50;
const orderStatuses = [["all", "Tất cả"], ["PENDING", "Đang chờ"], ["COMPLETED", "Hoàn thành"], ["CANCELLED", "Đã hủy"], ["RETURNED", "Đã hoàn trả"]];
const sources = [["all", "Tất cả"], ["user", "Người dùng"], ["post", "Bài đăng"], ["legacy", "Cũ"], ["unknown", "Không rõ"]];
const statusLabels: Record<string, string> = { PENDING: "Đang chờ", COMPLETED: "Hoàn thành", CANCELLED: "Đã hủy", RETURNED: "Đã hoàn trả" };
const sourceLabels: Record<string, string> = { user: "Người dùng", post: "Bài đăng", legacy: "Cũ", unknown: "Không rõ" };

export default function OrdersPage() {
  const router = useRouter(); const [status, setStatus] = useState("all"); const [source, setSource] = useState("all");
  const [rows, setRows] = useState<AdminOrder[]>([]); const [loading, setLoading] = useState(true); const [loadingMore, setLoadingMore] = useState(false); const [hasMore, setHasMore] = useState(false); const [error, setError] = useState(""); const pageLock = useRef(false);
  const loadFirst = useCallback(async (nextStatus: string, nextSource: string) => {
    setLoading(true); setError("");
    try { const page = await api.adminOrders({ status: nextStatus === "all" ? undefined : nextStatus, source: nextSource === "all" ? undefined : nextSource, limit: LIMIT, offset: 0 }); setRows(page); setHasMore(page.length === LIMIT); }
    catch (cause) { if (cause instanceof ApiError && cause.isAuth) router.replace("/login"); else if (cause instanceof ApiError && cause.isMfaRequired) router.replace("/admin/mfa"); else setError(cause instanceof ApiError && cause.status === 0 ? "Không kết nối được máy chủ" : cause instanceof ApiError ? cause.message : "Không thể tải đơn hàng."); }
    finally { setLoading(false); }
  }, [router]);
  useEffect(() => { void loadFirst("all", "all"); }, [loadFirst]);
  async function changeStatus(value: string) { setStatus(value); setRows([]); setHasMore(false); await loadFirst(value, source); }
  async function changeSource(value: string) { setSource(value); setRows([]); setHasMore(false); await loadFirst(status, value); }
  async function loadMore() {
    if (pageLock.current) return; pageLock.current = true; setLoadingMore(true); setError("");
    try { const page = await api.adminOrders({ status: status === "all" ? undefined : status, source: source === "all" ? undefined : source, limit: LIMIT, offset: rows.length }); setRows((current) => [...current, ...page]); setHasMore(page.length === LIMIT); }
    catch (cause) { if (cause instanceof ApiError && cause.isAuth) router.replace("/login"); else if (cause instanceof ApiError && cause.isMfaRequired) router.replace("/admin/mfa"); else setError(cause instanceof ApiError && cause.status === 0 ? "Không kết nối được máy chủ" : cause instanceof ApiError ? cause.message : "Không thể tải đơn hàng."); }
    finally { pageLock.current = false; setLoadingMore(false); }
  }
  return <main className="page"><section className="panel"><h1>Đơn hàng</h1>
    <div className="admin-filters"><label className="field" htmlFor="order-status">Lọc trạng thái<select id="order-status" value={status} onChange={(event) => void changeStatus(event.target.value)}>{orderStatuses.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label className="field" htmlFor="order-source">Lọc nguồn<select id="order-source" value={source} onChange={(event) => void changeSource(event.target.value)}>{sources.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label></div>
    {error && <Alert>{error}</Alert>}{loading ? <p role="status">Đang tải đơn hàng…</p> : rows.length === 0 ? <p>Không có đơn hàng.</p> : <ul className="link-list">{rows.map((row) => <li key={row.id}>
      <h2>#{row.id} · {row.order_sn}</h2><p>Trạng thái: {statusLabels[row.status] ?? row.status}</p><p>Nguồn: {sourceLabels[row.source_type] ?? row.source_type}</p><p>Người dùng: {row.user_id ?? "—"}</p><p>Hoa hồng: {formatVnd(row.commission_vnd)}</p>
      {row.purchase_time && <p>Ngày mua: {formatDateTime(row.purchase_time)}</p>}{row.completed_at && <p>Ngày hoàn tất: {formatDateTime(row.completed_at)}</p>}
    </li>)}</ul>}
    {hasMore && <Button type="button" disabled={loadingMore} onClick={() => void loadMore()}>{loadingMore ? "Đang tải…" : "Xem thêm"}</Button>}
  </section></main>;
}
