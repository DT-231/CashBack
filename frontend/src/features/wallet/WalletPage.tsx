"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, api } from "@/lib/api-client";
import type { EntryOut, WalletOut } from "@/lib/types";
import { formatDateTime, formatPercent, formatVnd } from "@/lib/format";
import { Alert, Button } from "@/components/ui";

const LIMIT = 50;
const kindLabels: Record<string, string> = {
  accrual: "Hoàn tiền", release: "Mở khóa", cancel: "Hủy hoàn tiền", reverse: "Thu hồi",
  hold: "Tạm khóa", payout: "Rút tiền", refund_hold: "Khóa hoàn tiền", adjust: "Điều chỉnh",
};
const stateLabels: Record<string, string> = {
  pending: "Chờ xác nhận", available: "Rút được", cancelled: "Đã hủy", reversed: "Đã thu hồi",
  held: "Đang khóa", paid_out: "Đã thanh toán",
};

export default function WalletPage() {
  const router = useRouter();
  const [wallet, setWallet] = useState<WalletOut | null>(null);
  const [entries, setEntries] = useState<EntryOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState("");
  const [entriesError, setEntriesError] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([api.wallet(), api.walletEntries({ limit: LIMIT, offset: 0 })]).then(([summary, first]) => {
      if (!active) return;
      setWallet(summary);
      setEntries(first);
      setHasMore(first.length === LIMIT);
    }).catch((cause: unknown) => {
      if (!active) return;
      if (cause instanceof ApiError && cause.isAuth) { router.replace("/login"); return; }
      setError(cause instanceof ApiError && cause.status === 0 ? "Không kết nối được máy chủ" : "Không thể tải thông tin ví. Vui lòng thử lại.");
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [router]);

  async function loadMore() {
    if (loadingMore) return;
    setLoadingMore(true);
    setEntriesError("");
    try {
      const more = await api.walletEntries({ limit: LIMIT, offset: entries.length });
      setEntries((current) => [...current, ...more]);
      setHasMore(more.length === LIMIT);
    } catch (cause) {
      if (cause instanceof ApiError && cause.isAuth) router.replace("/login");
      else setEntriesError(cause instanceof ApiError && cause.status === 0 ? "Không kết nối được máy chủ" : "Không thể tải lịch sử ví. Vui lòng thử lại.");
    } finally { setLoadingMore(false); }
  }

  if (loading) return <main className="page"><p role="status">Đang tải ví…</p></main>;
  return <main className="page">
    <section className="panel"><h1>Ví của tôi</h1>
      {error && <Alert>{error}</Alert>}
      {wallet && <>
        <dl className="wallet-balances">
          <div><dt>Chờ xác nhận</dt><dd>{formatVnd(wallet.pending_vnd)}</dd></div>
          <div><dt>Rút được</dt><dd>{formatVnd(wallet.available_vnd)}</dd></div>
          <div><dt>Đang khóa</dt><dd>{formatVnd(wallet.held_vnd)}</dd></div>
        </dl>
        <p>Tỷ lệ hoàn hiện tại: {formatPercent(wallet.share_pct)}</p>
        <p>Đơn cũ giữ tỷ lệ tại thời điểm phát sinh.</p>
        <Button type="button" disabled title="Sắp có">Rút tiền · Sắp có</Button>
      </>}
    </section>
    <section className="panel"><h2>Lịch sử ví</h2>
      {entriesError && <Alert>{entriesError}</Alert>}
      {entries.length === 0 && !loading && !entriesError ? <p>Chưa có giao dịch nào.</p> : null}
      {entries.length > 0 && <ul className="link-list">{entries.map((entry) => <li key={entry.id}>
        <h3>{kindLabels[entry.kind] ?? entry.kind}</h3>
        <p>Trạng thái: {stateLabels[entry.state] ?? entry.state}</p>
        <p>Số tiền: {formatVnd(entry.amount_vnd)}</p>
        <p>Ngày: {formatDateTime(entry.created_at)}</p>
      </li>)}</ul>}
      {hasMore && <Button type="button" disabled={loadingMore} onClick={loadMore}>{loadingMore ? "Đang tải…" : "Xem thêm"}</Button>}
    </section>
  </main>;
}
