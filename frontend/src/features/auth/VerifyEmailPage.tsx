"use client";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Alert, Button, TextField } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
const INVALID = "Liên kết không hợp lệ hoặc đã hết hạn";
export default function VerifyEmailPage() {
  const params = useSearchParams(); const started = useRef(false); const scrubbed = useRef(false); const [status, setStatus] = useState("Đang xác minh…"); const [invalid, setInvalid] = useState(false); const [email, setEmail] = useState(""); const [busy, setBusy] = useState(false); const [sent, setSent] = useState(false); const [resendError, setResendError] = useState(""); const resendRef = useRef(false);
  useEffect(() => { if (started.current) return; started.current = true; const token = params.get("token") ?? ""; if (!scrubbed.current) { scrubbed.current = true; window.history.replaceState(null, "", window.location.pathname); } if (!token) { setStatus(INVALID); setInvalid(true); return; }
    api.verifyEmail(token).then(() => setStatus("Email đã được xác minh.")).catch((cause: unknown) => { if (cause instanceof ApiError && cause.code === "invalid_token") { setStatus(INVALID); setInvalid(true); } else setStatus(cause instanceof ApiError && cause.status === 0 ? "Không kết nối được máy chủ" : "Không thể xác minh email. Vui lòng thử lại."); });
  }, [params]);
  async function resend() { if (resendRef.current || !email.trim()) return; resendRef.current = true; setBusy(true); setResendError(""); try { await api.resendVerification(email.trim()); setSent(true); } catch (cause) { setResendError(cause instanceof ApiError && cause.status === 0 ? "Không kết nối được máy chủ" : "Không thể gửi email xác minh. Vui lòng thử lại."); } finally { setEmail(""); resendRef.current = false; setBusy(false); } }
  return <main className="panel auth-panel"><h1>Xác minh email</h1>{invalid ? <><Alert>{INVALID}</Alert><form onSubmit={(e) => { e.preventDefault(); void resend(); }}><TextField label="Email" id="verify-email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />{resendError && <Alert>{resendError}</Alert>}{sent && <p role="status">Nếu tài khoản cần xác minh, chúng tôi đã gửi email mới.</p>}<Button type="submit" disabled={busy}>{busy ? "Đang gửi…" : "Gửi lại email xác minh"}</Button></form></> : <p role="status">{status}</p>}{status === "Email đã được xác minh." && <a href="/login">Đăng nhập</a>}</main>;
}
