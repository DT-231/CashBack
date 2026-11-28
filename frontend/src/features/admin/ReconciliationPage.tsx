"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Alert } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import type { Reconciliation } from "@/lib/types";
import { formatVnd } from "@/lib/format";
const known = [["PENDING", "Đang chờ"], ["COMPLETED", "Hoàn thành"], ["CANCELLED", "Đã hủy"], ["RETURNED", "Đã hoàn trả"]] as const;
const validMonth = /^20\d\d-(0[1-9]|1[0-2])$/;
function currentMonth() { const now = new Date(); return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`; }
export default function ReconciliationPage() {
  const router = useRouter(); const [month, setMonth] = useState(currentMonth); const [data, setData] = useState<Reconciliation | null>(null); const [loading, setLoading] = useState(false); const [error, setError] = useState("");
  useEffect(() => { if (!validMonth.test(month)) { setData(null); setLoading(false); return; } let active = true; setLoading(true); setError(""); api.adminReconciliation(month).then((value) => { if (active) setData(value); }).catch((cause: unknown) => { if (!active) return; if (cause instanceof ApiError && cause.isAuth) router.replace("/login"); else if (cause instanceof ApiError && cause.isMfaRequired) router.replace("/admin/mfa"); else setError(cause instanceof ApiError && cause.status === 0 ? "Không kết nối được máy chủ" : "Không thể tải dữ liệu đối soát."); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, [month, router]);
  const rows = data ? [...known, ...Object.keys(data.orders).filter((key) => !known.some(([status]) => status === key)).map((key) => [key, key] as const)] : [];
  const empty = data && Object.values(data.orders).every((row) => row.count === 0);
  return <main className="page"><section className="panel"><h1>Đối soát tháng</h1><label className="field" htmlFor="reconciliation-month">Tháng<input id="reconciliation-month" type="month" value={month} onChange={(event) => setMonth(event.target.value)} /></label>{error && <Alert>{error}</Alert>}{loading && <p role="status">Đang tải đối soát…</p>}{empty && <p>Không có đơn trong tháng này.</p>}{data && !empty && <><section><h2>Đơn theo trạng thái</h2><div className="admin-grid">{rows.map(([key, label]) => { const row = data.orders[key]; return <article className="admin-card" key={key}><h3>{label}</h3><p>Số đơn: {row?.count ?? 0}</p><p>Hoa hồng Shopee: {formatVnd(row?.commission_vnd ?? 0)}</p><p>Phần gán cho người dùng: {formatVnd(row?.attributed_vnd ?? 0)}</p></article>; })}</div></section><section><h2>Đơn hoàn thành</h2><div className="admin-grid"><article className="admin-card"><p>Hoa hồng Shopee: {formatVnd(data.completed.shopee_commission_vnd)}</p><p>Hoa hồng gán cho người dùng: {formatVnd(data.completed.attributed_commission_vnd)}</p><p>Phần chia người dùng đã cộng dồn: {formatVnd(data.completed.user_share_accrued_vnd)}</p><p>Biên nền tảng: {formatVnd(data.completed.platform_margin_vnd)}</p><p>Chi trả trong tháng: {formatVnd(data.paid_out_vnd)}</p><p>Khoản lỗi admin: {formatVnd(data.admin_loss_vnd)}</p></article></div>{data.note && <p>{data.note}</p>}</section></>}</section></main>;
}
