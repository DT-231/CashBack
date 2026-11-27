"use client";
import { useRef, useState, type FormEvent } from "react";
import { Alert, Button, TextField } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";

const SENT = "Nếu email này đã đăng ký, chúng tôi đã gửi liên kết đặt lại mật khẩu. Liên kết có hiệu lực 1 giờ.";
export default function ForgotPasswordPage() {
  const [email, setEmail] = useState(""); const [busy, setBusy] = useState(false); const busyRef = useRef(false); const [message, setMessage] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (busyRef.current) return; const value = email.trim(); if (!value) return; busyRef.current = true; setBusy(true); setMessage("");
    try { await api.forgotPassword(value); setMessage(SENT); }
    catch (error) { setMessage(error instanceof ApiError && error.status === 0 ? "Không kết nối được máy chủ" : error instanceof ApiError && (error.status === 429 || error.code === "rate_limited") ? "Bạn thao tác quá nhanh, vui lòng thử lại sau" : SENT); }
    finally { busyRef.current = false; setBusy(false); }
  }
  return <main className="panel auth-panel"><h1>Quên mật khẩu</h1><form onSubmit={submit}><TextField label="Email" id="forgot-email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />{message && (message === SENT ? <p role="status">{message}</p> : <Alert>{message}</Alert>)}<Button type="submit" disabled={busy}>{busy ? "Đang gửi…" : "Gửi liên kết"}</Button></form><a href="/login">Quay lại đăng nhập</a></main>;
}
