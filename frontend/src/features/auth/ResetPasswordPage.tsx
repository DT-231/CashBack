"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useSearchParams } from "next/navigation";
import { Alert, Button, TextField } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
const INVALID = "Liên kết không hợp lệ hoặc đã hết hạn";
export default function ResetPasswordPage() {
  const params = useSearchParams(); const scrubbed = useRef(false); const [token, setToken] = useState(""); const [password, setPassword] = useState(""); const [confirm, setConfirm] = useState(""); const [error, setError] = useState(""); const [done, setDone] = useState(false); const [busy, setBusy] = useState(false); const busyRef = useRef(false);
  useEffect(() => { if (scrubbed.current) return; scrubbed.current = true; const value = params.get("token") ?? ""; window.history.replaceState(null, "", window.location.pathname); setToken(value); if (!value) setError(INVALID); }, [params]);
  async function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (busyRef.current || !token) return; if (password.length < 10) { setError("Mật khẩu chưa hợp lệ (tối thiểu 10 ký tự)"); setPassword(""); setConfirm(""); return; } if (password !== confirm) { setError("Hai mật khẩu chưa khớp"); setPassword(""); setConfirm(""); return; }
    busyRef.current = true; setBusy(true); setError(""); const submitted = password;
    try { await api.resetPassword(token, submitted); setDone(true); setToken(""); }
    catch (cause) { const invalidToken = cause instanceof ApiError && cause.code === "invalid_token"; if (invalidToken) setToken(""); setError(cause instanceof ApiError && cause.status === 0 ? "Không kết nối được máy chủ" : cause instanceof ApiError && (cause.status === 429 || cause.code === "rate_limited") ? "Bạn thao tác quá nhanh, vui lòng thử lại sau" : cause instanceof ApiError && cause.code === "validation_error" ? "Mật khẩu chưa hợp lệ (tối thiểu 10 ký tự)" : invalidToken ? INVALID : "Không thể đặt lại mật khẩu. Vui lòng thử lại."); }
    finally { setPassword(""); setConfirm(""); busyRef.current = false; setBusy(false); }
  }
  return <main className="panel auth-panel"><h1>Đặt lại mật khẩu</h1>{done ? <><p role="status">Đã đặt lại mật khẩu. Hãy đăng nhập lại.</p><a href="/login">Đăng nhập</a></> : error === INVALID ? <><Alert>{INVALID}</Alert><a href="/forgot-password">Gửi liên kết mới</a></> : <form onSubmit={submit}><TextField label="Mật khẩu mới" id="reset-password" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} required /><TextField label="Nhập lại mật khẩu" id="reset-confirm" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />{error && <Alert>{error}</Alert>}<Button type="submit" disabled={busy || !token}>{busy ? "Đang lưu…" : "Đặt lại mật khẩu"}</Button></form>}</main>;
}
