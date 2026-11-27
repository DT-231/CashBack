"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Alert, Button } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import type { AdminUser } from "@/lib/types";
import { formatDateTime, formatVnd } from "@/lib/format";

const LIMIT = 50;
const roles: Record<string, string> = { member: "Thành viên", staff: "Nhân viên", admin: "Quản trị" };
const statuses: Record<string, string> = { unverified: "Chưa xác minh", active: "Hoạt động", locked: "Đã khóa" };

export default function UsersPage() {
  const router = useRouter();
  const [query, setQuery] = useState(""); const [submittedQuery, setSubmittedQuery] = useState("");
  const [rows, setRows] = useState<AdminUser[]>([]); const [reason, setReason] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true); const [loadingMore, setLoadingMore] = useState(false); const [hasMore, setHasMore] = useState(false); const [busyId, setBusyId] = useState<number | null>(null); const [error, setError] = useState("");
  const pageLock = useRef(false); const actionLock = useRef(false);
  const loadFirst = useCallback(async (q: string) => {
    setLoading(true); setError("");
    try { const page = await api.adminUsers({ q: q || undefined, limit: LIMIT, offset: 0 }); setRows(page); setHasMore(page.length === LIMIT); }
    catch (cause) { if (cause instanceof ApiError && cause.isAuth) router.replace("/login"); else if (cause instanceof ApiError && cause.isMfaRequired) router.replace("/admin/mfa"); else setError(cause instanceof ApiError && cause.status === 0 ? "Không kết nối được máy chủ" : cause instanceof ApiError ? cause.message : "Không thể tải người dùng."); }
    finally { setLoading(false); }
  }, [router]);
  useEffect(() => { void loadFirst(""); }, [loadFirst]);
  function search(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setSubmittedQuery(query); void loadFirst(query); }
  async function loadMore() {
    if (pageLock.current) return; pageLock.current = true; setLoadingMore(true); setError("");
    try { const page = await api.adminUsers({ q: submittedQuery || undefined, limit: LIMIT, offset: rows.length }); setRows((current) => [...current, ...page]); setHasMore(page.length === LIMIT); }
    catch (cause) { if (cause instanceof ApiError && cause.isAuth) router.replace("/login"); else if (cause instanceof ApiError && cause.isMfaRequired) router.replace("/admin/mfa"); else setError(cause instanceof ApiError && cause.status === 0 ? "Không kết nối được máy chủ" : cause instanceof ApiError ? cause.message : "Không thể tải người dùng."); }
    finally { pageLock.current = false; setLoadingMore(false); }
  }
  async function updateStatus(event: FormEvent<HTMLFormElement>, user: AdminUser) {
    event.preventDefault(); const value = reason[user.id] ?? ""; if (value.trim().length < 3 || actionLock.current) return;
    actionLock.current = true; setBusyId(user.id); setError("");
    try { await api.adminSetUserStatus(user.id, user.status === "locked" ? "active" : "locked", value); setReason((current) => ({ ...current, [user.id]: "" })); await loadFirst(submittedQuery); }
    catch (cause) {
      if (cause instanceof ApiError && cause.isAuth) router.replace("/login");
      else if (cause instanceof ApiError && cause.isMfaRequired) router.replace("/admin/mfa");
      else if (cause instanceof ApiError && cause.code === "invalid_target") setError("Không được đổi trạng thái tài khoản này");
      else if (cause instanceof ApiError && cause.code === "user_not_found") { await loadFirst(submittedQuery); setError("Không tìm thấy người dùng, đã tải lại danh sách"); }
      else if (cause instanceof ApiError && cause.code === "forbidden") setError("Chỉ admin được thực hiện");
      else setError(cause instanceof ApiError && cause.status === 0 ? "Không kết nối được máy chủ" : cause instanceof ApiError ? cause.message : "Không thể cập nhật người dùng.");
    } finally { actionLock.current = false; setBusyId(null); }
  }
  return <main className="page"><section className="panel"><h1>Người dùng</h1>
    <form className="admin-filters" onSubmit={search}><label className="field" htmlFor="user-query">Tìm theo email<input id="user-query" type="search" value={query} onChange={(event) => setQuery(event.target.value)} /></label><Button type="submit" disabled={loading}>Tìm</Button></form>
    {error && <Alert>{error}</Alert>}{loading ? <p role="status">Đang tải người dùng…</p> : rows.length === 0 ? <p>Không tìm thấy người dùng.</p> : <ul className="link-list">{rows.map((user) => <li key={user.id}>
      <h2>#{user.id} · {user.email}</h2><p>Vai trò: {roles[user.role] ?? user.role}</p><p>Trạng thái: {statuses[user.status] ?? user.status}</p><p>Ngày tạo: {formatDateTime(user.created_at)}</p>
      <p>Ví: Chờ {formatVnd(user.pending_vnd)} · Rút được {formatVnd(user.available_vnd)} · Đang khóa {formatVnd(user.held_vnd)}</p>
      {user.role !== "admin" && <form className="admin-row-actions" onSubmit={(event) => void updateStatus(event, user)}><label className="field" htmlFor={`user-reason-${user.id}`}>Lý do {user.status === "locked" ? "mở khóa" : "khóa"}<input id={`user-reason-${user.id}`} minLength={3} value={reason[user.id] ?? ""} onChange={(event) => setReason((current) => ({ ...current, [user.id]: event.target.value }))} required /></label><Button type="submit" disabled={busyId === user.id || (reason[user.id] ?? "").trim().length < 3}>{busyId === user.id ? "Đang lưu…" : user.status === "locked" ? "Mở khóa" : "Khóa"}</Button></form>}
    </li>)}</ul>}
    {hasMore && <Button type="button" disabled={loadingMore} onClick={() => void loadMore()}>{loadingMore ? "Đang tải…" : "Xem thêm"}</Button>}
  </section></main>;
}
