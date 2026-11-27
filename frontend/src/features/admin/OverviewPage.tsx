"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Alert } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import type { AdminOverview } from "@/lib/types";
import { formatDateTime, formatVnd } from "@/lib/format";

const orderStatuses = [["PENDING", "Đang chờ"], ["COMPLETED", "Hoàn thành"], ["CANCELLED", "Đã hủy"], ["RETURNED", "Đã hoàn trả"]] as const;
const withdrawalStatuses = [["requested", "Đang chờ duyệt"], ["approved", "Đã duyệt"], ["rejected", "Bị từ chối"], ["processing", "Đang xử lý"], ["paid", "Đã chi trả"], ["failed", "Chuyển khoản lỗi"]] as const;
const syncLabels: Record<string, string> = { ok: "Thành công", partial: "Một phần", failed: "Thất bại" };

export default function OverviewPage() {
  const router = useRouter();
  const [days, setDays] = useState(30);
  const [data, setData] = useState<AdminOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setLoading(true); setError("");
    api.adminOverview(days).then((value) => { if (active) setData(value); }).catch((cause: unknown) => {
      if (!active) return;
      if (cause instanceof ApiError && cause.isAuth) router.replace("/login");
      else if (cause instanceof ApiError && cause.isMfaRequired) router.replace("/admin/mfa");
      else setError(cause instanceof ApiError && cause.status === 0 ? "Không kết nối được máy chủ" : cause instanceof ApiError ? cause.message : "Không thể tải tổng quan.");
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [days, router]);
  return <main className="page"><section className="panel"><h1>Tổng quan</h1>
    <label className="field" htmlFor="overview-days">Khoảng ngày<select id="overview-days" value={days} onChange={(event) => setDays(Number(event.target.value))}>{[7, 30, 90, 365].map((value) => <option key={value} value={value}>{value} ngày</option>)}</select></label>
    {error && <Alert>{error}</Alert>}{loading && <p role="status">Đang tải tổng quan…</p>}
    {data && <>
      <section className="admin-grid" aria-label="Chỉ số tổng quan">
        <article className="admin-card"><h2>Người dùng</h2><p>Tổng: {data.users.total}</p><p>Mới trong kỳ: {data.users.new}</p><p>Bị khóa: {data.users.locked}</p></article>
        <article className="admin-card"><h2>Hoạt động</h2><p>Lượt nhấp: {data.clicks}</p><p>Liên kết: {data.links}</p></article>
        <article className="admin-card"><h2>Đơn mồ côi chưa gán</h2><p>{data.orphans_open}</p><a href="/admin/orphans">Xem đơn mồ côi</a></article>
        <article className="admin-card"><h2>Tổng ví</h2><p>Chờ xác nhận: {formatVnd(data.wallet_totals_vnd.pending)}</p><p>Rút được: {formatVnd(data.wallet_totals_vnd.available)}</p><p>Đang khóa: {formatVnd(data.wallet_totals_vnd.held)}</p></article>
      </section>
      <section><h2>Đơn hàng theo trạng thái</h2><div className="admin-grid">{[...orderStatuses, ...Object.keys(data.orders).filter((key) => !orderStatuses.some(([known]) => known === key)).map((key) => [key, key] as const)].map(([key, label]) => { const row = data.orders[key]; return <article className="admin-card" key={key}><h3>{label}</h3><p>Số đơn: {row?.count ?? 0}</p><p>Hoa hồng: {formatVnd(row?.commission_vnd ?? 0)}</p></article>; })}</div></section>
      <section><h2>Yêu cầu rút tiền</h2><div className="admin-grid">{[...withdrawalStatuses, ...Object.keys(data.withdrawals).filter((key) => !withdrawalStatuses.some(([known]) => known === key)).map((key) => [key, key] as const)].map(([key, label]) => { const row = data.withdrawals[key]; return <article className="admin-card" key={key}><h3>{label}</h3><p>Số yêu cầu: {row?.count ?? 0}</p><p>Số tiền: {formatVnd(row?.amount_vnd ?? 0)}</p></article>; })}</div></section>
      <section><h2>Đồng bộ gần nhất</h2>{data.last_sync ? <p>{syncLabels[data.last_sync.result] ?? data.last_sync.result} · {formatDateTime(data.last_sync.finished_at)}</p> : <p>Chưa từng đồng bộ</p>}</section>
    </>}
  </section></main>;
}
