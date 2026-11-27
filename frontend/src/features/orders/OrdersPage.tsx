"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, api } from "@/lib/api-client";
import type { OrderOut } from "@/lib/types";
import { formatDateTime, formatVnd } from "@/lib/format";
import { Alert, Button } from "@/components/ui";

const LIMIT = 50;
const statusLabels: Record<OrderOut["status"], string> = {
  PENDING: "Đang chờ", COMPLETED: "Hoàn thành", CANCELLED: "Đã hủy", RETURNED: "Đã hoàn trả",
};
const refundLabels: Record<OrderOut["refund_state"], string> = {
  none: "Chưa có hoàn tiền", pending: "Chờ xác nhận", available: "Rút được", cancelled: "Đã hủy", reversed: "Đã thu hồi",
};

export default function OrdersPage() {
  const router = useRouter();
  const [orders, setOrders] = useState<OrderOut[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    api.myOrders({ limit: LIMIT, offset: 0 }).then((first) => {
      if (!active) return;
      setOrders(first);
      setHasMore(first.length === LIMIT);
    }).catch((cause: unknown) => {
      if (!active) return;
      if (cause instanceof ApiError && cause.isAuth) { router.replace("/login"); return; }
      setError(cause instanceof ApiError && cause.status === 0 ? "Không kết nối được máy chủ" : "Không thể tải đơn hàng. Vui lòng thử lại.");
    }).finally(() => { if (active) setLoaded(true); });
    return () => { active = false; };
  }, [router]);

  async function loadMore() {
    if (loadingMore) return;
    setLoadingMore(true);
    setError("");
    try {
      const more = await api.myOrders({ limit: LIMIT, offset: orders.length });
      setOrders((current) => [...current, ...more]);
      setHasMore(more.length === LIMIT);
    } catch (cause) {
      if (cause instanceof ApiError && cause.isAuth) router.replace("/login");
      else setError(cause instanceof ApiError && cause.status === 0 ? "Không kết nối được máy chủ" : "Không thể tải đơn hàng. Vui lòng thử lại.");
    } finally { setLoadingMore(false); }
  }

  return <main className="page"><section className="panel"><h1>Đơn hàng của tôi</h1>
    {error && <Alert>{error}</Alert>}
    {!loaded && <p role="status">Đang tải đơn hàng…</p>}
    {loaded && orders.length === 0 && !error && <p>Bạn chưa có đơn hàng nào.</p>}
    {orders.length > 0 && <ul className="link-list">{orders.map((order) => <li key={order.id}>
      <h2>Đơn hàng …{order.order_ref}</h2>
      <p>Trạng thái đơn: {statusLabels[order.status]}</p>
      {order.product_name && <p>Sản phẩm: {order.product_name}</p>}
      {order.purchased_at && <p>Ngày mua: {formatDateTime(order.purchased_at)}</p>}
      <p>Hoàn tiền: {formatVnd(order.refund_vnd)} · {refundLabels[order.refund_state]}</p>
      {order.expected_release_at && <p>Dự kiến mở khóa: {formatDateTime(order.expected_release_at)}</p>}
    </li>)}</ul>}
    {hasMore && <Button type="button" disabled={loadingMore} onClick={loadMore}>{loadingMore ? "Đang tải…" : "Xem thêm"}</Button>}
  </section></main>;
}
