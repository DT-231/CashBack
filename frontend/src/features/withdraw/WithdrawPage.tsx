"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { ApiError, api } from "@/lib/api-client";
import type { BankAccountOut, WalletOut, WithdrawalOut, WithdrawalRules } from "@/lib/types";
import { formatDateTime, formatVnd } from "@/lib/format";
import { Alert, Button } from "@/components/ui";

const LIMIT = 50;
const statusLabels: Record<string, string> = {
  requested: "Đang chờ duyệt", approved: "Đã duyệt", rejected: "Bị từ chối",
  processing: "Đang xử lý", paid: "Đã chi trả", failed: "Chuyển khoản lỗi",
};
const errorLabels: Record<string, string> = {
  below_minimum: "Số tiền thấp hơn mức tối thiểu", insufficient_funds: "Số dư rút được không đủ",
  withdrawal_open_exists: "Bạn đang có một yêu cầu rút chưa xử lý xong",
  idempotency_conflict: "Yêu cầu này đã được gửi với nội dung khác; vui lòng tải lại trang",
  bank_account_cooling_down: "Tài khoản này chưa dùng được để rút", invalid_bank_account: "Tài khoản ngân hàng không hợp lệ",
  too_many_bank_accounts: "Đã đạt số tài khoản tối đa", withdrawals_disabled: "Tính năng rút tiền chưa mở",
  rate_limited: "Bạn thao tác quá nhanh, vui lòng thử lại sau",
  validation_error: "Thông tin chưa hợp lệ, vui lòng kiểm tra lại",
};

export default function WithdrawPage() {
  const router = useRouter();
  const [rules, setRules] = useState<WithdrawalRules | null>(null);
  const [wallet, setWallet] = useState<WalletOut | null>(null);
  const [accounts, setAccounts] = useState<BankAccountOut[]>([]);
  const [withdrawals, setWithdrawals] = useState<WithdrawalOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [bankCode, setBankCode] = useState("");
  const [accountNo, setAccountNo] = useState("");
  const [accountName, setAccountName] = useState("");
  const [amount, setAmount] = useState("");
  const [selectedAccount, setSelectedAccount] = useState("");
  const [formError, setFormError] = useState("");
  const [success, setSuccess] = useState("");
  const [adding, setAdding] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [hasMore, setHasMore] = useState(false);
  const submissionLock = useRef(false);
  const pageLock = useRef(false);
  const idempotencyKey = useRef("");

  function authError(cause: unknown) {
    if (cause instanceof ApiError && cause.isAuth) { router.replace("/login"); return true; }
    return false;
  }
  function errorMessage(cause: unknown) {
    if (cause instanceof ApiError && cause.status === 0) return "Không kết nối được máy chủ";
    if (cause instanceof ApiError) return errorLabels[cause.code] ?? cause.message;
    return "Không thể hoàn tất yêu cầu. Vui lòng thử lại.";
  }
  async function refreshAccounts() { setAccounts(await api.bankAccounts()); }
  async function refreshWalletAndHistory() {
    const [nextWallet, first] = await Promise.all([api.wallet(), api.myWithdrawals({ limit: LIMIT, offset: 0 })]);
    setWallet(nextWallet);
    setWithdrawals(first);
    setHasMore(first.length === LIMIT);
  }

  useEffect(() => {
    let active = true;
    Promise.all([api.withdrawalRules(), api.bankAccounts(), api.wallet(), api.myWithdrawals({ limit: LIMIT, offset: 0 })])
      .then(([nextRules, nextAccounts, nextWallet, first]) => {
        if (!active) return;
        setRules(nextRules); setAccounts(nextAccounts); setWallet(nextWallet); setWithdrawals(first); setHasMore(first.length === LIMIT);
      }).catch((cause: unknown) => {
        if (!active) return;
        if (!authError(cause)) setLoadError(errorMessage(cause));
      }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [router]);

  async function addAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (adding) return;
    setAdding(true); setFormError(""); setSuccess("");
    try {
      await api.addBankAccount({ bank_code: bankCode, account_no: accountNo, account_name: accountName });
      setAccountNo(""); setBankCode(""); setAccountName("");
      await refreshAccounts();
      setSuccess("Đã thêm tài khoản ngân hàng");
    } catch (cause) {
      if (!authError(cause)) setFormError(errorMessage(cause));
    } finally { setAdding(false); }
  }

  async function requestWithdrawal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submissionLock.current) return;
    submissionLock.current = true; setSubmitting(true); setFormError(""); setSuccess("");
    if (!idempotencyKey.current) idempotencyKey.current = crypto.randomUUID();
    try {
      await api.requestWithdrawal({ amount_vnd: Number(amount), bank_account_id: Number(selectedAccount) }, idempotencyKey.current);
      idempotencyKey.current = ""; setAmount(""); setSuccess("Đã gửi yêu cầu rút");
      await refreshWalletAndHistory();
    } catch (cause) {
      if (!authError(cause)) setFormError(errorMessage(cause));
    } finally { submissionLock.current = false; setSubmitting(false); }
  }

  async function loadMore() {
    if (pageLock.current) return;
    pageLock.current = true; setLoadingMore(true); setHistoryError("");
    try {
      const more = await api.myWithdrawals({ limit: LIMIT, offset: withdrawals.length });
      setWithdrawals((current) => [...current, ...more]); setHasMore(more.length === LIMIT);
    } catch (cause) {
      if (!authError(cause)) setHistoryError(errorMessage(cause));
    } finally { pageLock.current = false; setLoadingMore(false); }
  }

  if (loading) return <main className="page"><p role="status">Đang tải thông tin rút tiền…</p></main>;
  return <main className="page">
    <section className="panel"><h1>Rút tiền</h1>{loadError && <Alert>{loadError}</Alert>}
      {rules?.withdrawals_enabled === false ? <p>Tính năng rút tiền chưa mở</p> : rules && <>
        {wallet && <p>Rút được: {formatVnd(wallet.available_vnd)}</p>}
        <p>Tối thiểu mỗi lần: {formatVnd(rules.min_withdraw_vnd)}</p>
        <p>Tài khoản mới dùng được sau {rules.bank_change_cooldown_hours} giờ kể từ khi thêm</p>
        <h2>Tài khoản ngân hàng</h2>
        {accounts.length === 0 ? <p>Chưa có tài khoản ngân hàng.</p> : <ul className="link-list">{accounts.map((account) => <li key={account.id}>
          <p>{account.bank_code} · {account.account_name} · •••• {account.last4}</p>
          {!account.usable_now && <p>Chưa dùng được để rút. Dùng được từ {formatDateTime(account.usable_from)}</p>}
        </li>)}</ul>}
        <form onSubmit={addAccount}>
          <label className="field">Mã ngân hàng<input value={bankCode} onChange={(event) => setBankCode(event.target.value)} required /></label>
          <label className="field">Số tài khoản<input inputMode="numeric" autoComplete="off" value={accountNo} onChange={(event) => setAccountNo(event.target.value)} required /></label>
          <label className="field">Tên chủ tài khoản<input value={accountName} onChange={(event) => setAccountName(event.target.value)} required /></label>
          <Button type="submit" disabled={adding}>{adding ? "Đang thêm…" : "Thêm tài khoản"}</Button>
        </form>
        <form onSubmit={requestWithdrawal}>
          <label className="field">Tài khoản nhận<select required value={selectedAccount} onChange={(event) => { setSelectedAccount(event.target.value); idempotencyKey.current = ""; }}>
            <option value="">Chọn tài khoản</option>{accounts.filter((account) => account.usable_now).map((account) => <option key={account.id} value={account.id}>{account.bank_code} · •••• {account.last4}</option>)}
          </select></label>
          <label className="field">Số tiền<input inputMode="numeric" pattern="[0-9]+" value={amount} onChange={(event) => { setAmount(event.target.value); idempotencyKey.current = ""; }} required /></label>
          {formError && <Alert>{formError}</Alert>}{success && <p role="status">{success}</p>}
          <Button type="submit" disabled={submitting}>{submitting ? "Đang gửi…" : "Rút tiền"}</Button>
        </form>
      </>}
    </section>
    {rules?.withdrawals_enabled !== false && <section className="panel"><h2>Lịch sử yêu cầu rút</h2>
      {historyError && <Alert>{historyError}</Alert>}
      {withdrawals.length === 0 ? <p>Chưa có yêu cầu rút tiền nào.</p> : <ul className="link-list">{withdrawals.map((withdrawal) => <li key={withdrawal.id}>
        <p>Số tiền: {formatVnd(withdrawal.amount_vnd)}</p>
        <p>{withdrawal.bank_code ?? ""} · •••• {withdrawal.last4 ?? ""}</p>
        <p>Trạng thái: {statusLabels[withdrawal.status] ?? withdrawal.status}</p>
        <p>Ngày: {formatDateTime(withdrawal.created_at)}</p>
        {withdrawal.provider_ref && <p>Mã giao dịch: {withdrawal.provider_ref}</p>}
        {withdrawal.decided_reason && <p>Lý do: {withdrawal.decided_reason}</p>}
      </li>)}</ul>}
      {hasMore && <Button type="button" disabled={loadingMore} onClick={loadMore}>{loadingMore ? "Đang tải…" : "Xem thêm"}</Button>}
    </section>}
  </main>;
}
