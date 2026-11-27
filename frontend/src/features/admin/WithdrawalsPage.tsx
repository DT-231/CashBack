"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Alert, Button } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import type { AdminWithdrawalOut, PayoutAccountOut, WithdrawalStatus } from "@/lib/types";
import { formatDateTime, formatVnd } from "@/lib/format";

const LIMIT = 50;
const statuses: { value: WithdrawalStatus | "all"; label: string }[] = [
  { value: "all", label: "Tất cả" }, { value: "requested", label: "Đang chờ duyệt" }, { value: "approved", label: "Đã duyệt" },
  { value: "rejected", label: "Bị từ chối" }, { value: "paid", label: "Đã chi trả" }, { value: "failed", label: "Chuyển khoản lỗi" },
];
const labels: Record<string, string> = { requested: "Đang chờ duyệt", approved: "Đã duyệt", rejected: "Bị từ chối", processing: "Đang xử lý", paid: "Đã chi trả", failed: "Chuyển khoản lỗi" };

function errorText(cause: unknown) {
  if (cause instanceof ApiError) {
    if (cause.isAuth) return "__auth__";
    if (cause.isMfaRequired) return "__mfa__";
    if (cause.status === 0) return "Không kết nối được máy chủ";
    const messages: Record<string, string> = {
      invalid_transition: "Yêu cầu đã được xử lý ở nơi khác, đã tải lại danh sách",
      duplicate_provider_ref: "Mã giao dịch này đã dùng cho yêu cầu khác",
      forbidden: "Chỉ admin được thực hiện",
      withdrawals_disabled: "Tính năng rút tiền chưa mở",
      insufficient_funds: "Số dư đang khóa không khớp, hãy kiểm tra sổ cái",
    };
    return messages[cause.code] ?? cause.message;
  }
  return "Không thể hoàn tất yêu cầu. Vui lòng thử lại.";
}

export default function WithdrawalsPage() {
  const router = useRouter();
  const [filter, setFilter] = useState<WithdrawalStatus | "all">("all");
  const [rows, setRows] = useState<AdminWithdrawalOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState("");
  const [account, setAccount] = useState<PayoutAccountOut | null>(null);
  const [accountNote, setAccountNote] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [rejectReasons, setRejectReasons] = useState<Record<number, string>>({});
  const [failReasons, setFailReasons] = useState<Record<number, string>>({});
  const [providerRefs, setProviderRefs] = useState<Record<number, string>>({});
  const [exporting, setExporting] = useState(false);
  const [exportMessage, setExportMessage] = useState("");
  const lock = useRef(false);
  const pageLock = useRef(false);
  const accountRequest = useRef(0);

  function clearAccount() {
    accountRequest.current += 1;
    setAccount(null); setAccountNote("");
  }

  function handleError(cause: unknown) {
    const text = errorText(cause);
    if (text === "__auth__") router.replace("/login");
    else if (text === "__mfa__") router.replace("/admin/mfa");
    else setError(text);
  }
  async function loadFirst(nextFilter = filter) {
    setLoading(true); setError(""); clearAccount();
    try {
      const page = await api.adminWithdrawals({ status: nextFilter === "all" ? undefined : nextFilter, limit: LIMIT, offset: 0 });
      setRows(page); setHasMore(page.length === LIMIT);
    } catch (cause) { handleError(cause); }
    finally { setLoading(false); }
  }
  useEffect(() => { void loadFirst("all"); return () => { accountRequest.current += 1; }; }, []);

  async function changeFilter(value: WithdrawalStatus | "all") {
    setFilter(value); setRows([]); setHasMore(false); clearAccount();
    await loadFirst(value);
  }
  async function loadMore() {
    if (pageLock.current) return;
    pageLock.current = true; setLoadingMore(true); setError("");
    try {
      const page = await api.adminWithdrawals({ status: filter === "all" ? undefined : filter, limit: LIMIT, offset: rows.length });
      setRows((current) => [...current, ...page]); setHasMore(page.length === LIMIT);
    } catch (cause) { handleError(cause); }
    finally { pageLock.current = false; setLoadingMore(false); }
  }
  async function act(id: number, action: () => Promise<unknown>) {
    if (lock.current) return;
    lock.current = true; setBusyId(id); setError(""); clearAccount();
    try { await action(); await loadFirst(); }
    catch (cause) {
      const text = errorText(cause);
      if (text === "Yêu cầu đã được xử lý ở nơi khác, đã tải lại danh sách") {
        await loadFirst(); setError(text);
      } else handleError(cause);
    } finally { lock.current = false; setBusyId(null); }
  }
  async function submitReason(event: FormEvent<HTMLFormElement>, row: AdminWithdrawalOut, kind: "reject" | "fail") {
    event.preventDefault();
    const reason = (kind === "reject" ? rejectReasons : failReasons)[row.id] ?? "";
    if (reason.trim().length < 3 || lock.current) return;
    await act(row.id, () => kind === "reject" ? api.adminReject(row.id, reason) : api.adminFail(row.id, reason));
    if (kind === "reject") setRejectReasons((current) => ({ ...current, [row.id]: "" }));
    else setFailReasons((current) => ({ ...current, [row.id]: "" }));
  }
  async function submitPaid(event: FormEvent<HTMLFormElement>, row: AdminWithdrawalOut) {
    event.preventDefault();
    const ref = providerRefs[row.id] ?? "";
    if (!ref.trim() || lock.current) return;
    await act(row.id, () => api.adminMarkPaid(row.id, ref));
    setProviderRefs((current) => ({ ...current, [row.id]: "" }));
  }
  async function viewAccount(row: AdminWithdrawalOut) {
    if (lock.current) return;
    lock.current = true; setBusyId(row.id); setError(""); clearAccount();
    const requestId = ++accountRequest.current;
    try { const result = await api.adminPayoutAccount(row.id); if (accountRequest.current === requestId) { setAccount(result); setAccountNote(row.transfer_note); } }
    catch (cause) { handleError(cause); }
    finally { lock.current = false; setBusyId(null); }
  }
  async function exportCsv() {
    if (lock.current) return;
    lock.current = true; setExporting(true); setError(""); setExportMessage("");
    try {
      const blob = await api.adminExportCsv();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url; link.download = "cashback-payouts.csv"; link.click();
      URL.revokeObjectURL(url);
      setExportMessage("Tệp chứa số tài khoản đầy đủ: lưu an toàn và xóa sau khi chuyển khoản");
    } catch (cause) { handleError(cause); }
    finally { lock.current = false; setExporting(false); }
  }

  return <main className="page admin-withdrawals"><section className="panel"><h1>Yêu cầu rút tiền</h1>
    <label className="field">Lọc trạng thái<select value={filter} onChange={(event) => void changeFilter(event.target.value as WithdrawalStatus | "all")}>{statuses.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
    <Button type="button" disabled={exporting} onClick={exportCsv}>{exporting ? "Đang xuất…" : "Tải CSV chuyển khoản (các yêu cầu đã duyệt)"}</Button>
    {exportMessage && <p role="status">{exportMessage}</p>}{error && <Alert>{error}</Alert>}
    {loading ? <p role="status">Đang tải yêu cầu…</p> : rows.length === 0 ? <p>Không có yêu cầu rút tiền.</p> : <ul className="link-list withdrawal-list">{rows.map((row) => <li key={row.id}>
      <h2>Yêu cầu #{row.id}</h2><p>Người dùng: {row.user_id}</p><p>Số tiền: {formatVnd(row.amount_vnd)}</p>
      <p>Ngân hàng: {row.bank_code ?? ""} · •••• {row.last4 ?? ""}</p><p>Trạng thái: {labels[row.status] ?? row.status}</p>
      <p>Ngày tạo: {formatDateTime(row.created_at)}</p><p>Nội dung chuyển khoản: <span className="transfer-note">{row.transfer_note}</span></p>
      {row.provider_ref && <p>Mã giao dịch: {row.provider_ref}</p>}{row.decided_reason && <p>Lý do: {row.decided_reason}</p>}
      <div className="withdrawal-actions">
        {row.status === "requested" && <>
          <Button type="button" disabled={busyId === row.id} onClick={() => void act(row.id, () => api.adminApprove(row.id))}>{busyId === row.id ? "Đang xử lý…" : "Duyệt"}</Button>
          <form onSubmit={(event) => void submitReason(event, row, "reject")}><label className="field">Lý do từ chối<input minLength={3} value={rejectReasons[row.id] ?? ""} onChange={(event) => setRejectReasons((current) => ({ ...current, [row.id]: event.target.value }))} required /></label><Button type="submit" disabled={busyId === row.id || (rejectReasons[row.id] ?? "").trim().length < 3}>Từ chối</Button></form>
        </>}
        {row.status === "approved" && <>
          <Button type="button" disabled={busyId === row.id} onClick={() => void viewAccount(row)}>{busyId === row.id ? "Đang tải…" : "Xem số tài khoản"}</Button>
          <form onSubmit={(event) => void submitPaid(event, row)}><label className="field">Mã giao dịch ngân hàng<input value={providerRefs[row.id] ?? ""} onChange={(event) => setProviderRefs((current) => ({ ...current, [row.id]: event.target.value }))} required /></label><Button type="submit" disabled={busyId === row.id || !(providerRefs[row.id] ?? "").trim()}>Đánh dấu đã chi trả</Button></form>
          <form onSubmit={(event) => void submitReason(event, row, "fail")}><label className="field">Lý do chuyển khoản lỗi<input minLength={3} value={failReasons[row.id] ?? ""} onChange={(event) => setFailReasons((current) => ({ ...current, [row.id]: event.target.value }))} required /></label><Button type="submit" disabled={busyId === row.id || (failReasons[row.id] ?? "").trim().length < 3}>Chuyển khoản lỗi</Button></form>
          <form onSubmit={(event) => void submitReason(event, row, "reject")}><label className="field">Lý do từ chối<input minLength={3} value={rejectReasons[row.id] ?? ""} onChange={(event) => setRejectReasons((current) => ({ ...current, [row.id]: event.target.value }))} required /></label><Button type="submit" disabled={busyId === row.id || (rejectReasons[row.id] ?? "").trim().length < 3}>Từ chối</Button></form>
        </>}
      </div>
      {account?.withdrawal_id === row.id && <section className="payout-account"><h3>Thông tin tài khoản nhận</h3><p className="sensitive-warning">Thông tin nhạy cảm, mỗi lần xem đều được ghi nhật ký</p>
        <p>Ngân hàng: {account.bank_code}</p><p>Số tài khoản: <span className="sensitive-value">{account.account_no}</span></p><p>Tên chủ tài khoản: {account.account_name}</p><p>Số tiền: {formatVnd(account.amount_vnd)}</p><p>Nội dung chuyển khoản: <span className="transfer-note">{accountNote}</span></p>
        <Button type="button" onClick={clearAccount}>Ẩn</Button>
      </section>}
    </li>)}</ul>}
    {hasMore && <Button type="button" disabled={loadingMore} onClick={loadMore}>{loadingMore ? "Đang tải…" : "Xem thêm"}</Button>}
  </section></main>;
}
