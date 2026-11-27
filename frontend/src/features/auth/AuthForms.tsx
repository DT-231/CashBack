"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { ApiError, api } from "@/lib/api-client";
import { Alert, Button, TextField } from "@/components/ui";

function message(error: unknown, registering = false): string {
  if (!(error instanceof ApiError)) return "Có lỗi xảy ra. Vui lòng thử lại.";
  if (error.status === 0) return "Không kết nối được máy chủ";
  if (error.status === 429 || error.code === "rate_limited") return "Bạn thử quá nhiều lần, vui lòng đợi một lát";
  if (registering && error.code === "email_taken") return "Email này đã được đăng ký";
  if (registering && error.code === "validation_error") return error.message;
  if (error.code === "invalid_credentials") return "Email hoặc mật khẩu không đúng";
  if (error.code === "account_locked") return "Tài khoản đã bị khóa";
  if (error.code === "email_unverified") return "Vui lòng xác minh email";
  return error.message || "Có lỗi xảy ra. Vui lòng thử lại.";
}

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [resending, setResending] = useState(false);
  const [resent, setResent] = useState(false);
  const [unverified, setUnverified] = useState(false);
  const registering = mode === "register";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    if (registering && password.length < 10) { setError("Mật khẩu cần có ít nhất 10 ký tự"); return; }
    setBusy(true); setError("");
    let registered = false;
    try {
      if (registering) { await api.register(email, password); registered = true; }
      await api.login(email, password);
      router.push("/links");
    } catch (cause) {
      if (registered) { setError("Tài khoản đã được tạo, vui lòng đăng nhập"); router.replace("/login"); return; }
      if (!registering && cause instanceof ApiError && cause.isAuth) { router.replace("/login"); return; }
      setUnverified(cause instanceof ApiError && cause.code === "email_unverified");
      setError(message(cause, registering));
    }
    finally { setBusy(false); }
  }

  async function resend() {
    if (resending) return;
    setResending(true); setResent(false);
    try { await api.resendVerification(email); setResent(true); }
    catch (cause) { if (cause instanceof ApiError && cause.isAuth) router.replace("/login"); else setError(cause instanceof ApiError && cause.status === 0 ? "Không kết nối được máy chủ" : "Không thể gửi email xác minh. Vui lòng thử lại."); }
    finally { setResending(false); }
  }

  return <main className="panel auth-panel"><h1>{registering ? "Tạo tài khoản" : "Đăng nhập"}</h1>
    <form onSubmit={submit}>
      <TextField label="Email" id={`${mode}-email`} type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      <TextField label="Mật khẩu" id={`${mode}-password`} type="password" autoComplete={registering ? "new-password" : "current-password"} required value={password} onChange={(e) => setPassword(e.target.value)} />
      {error && <Alert>{error}</Alert>}
      {!registering && <a href="/forgot-password">Quên mật khẩu?</a>}
      {unverified && !resent && <Button type="button" disabled={resending} onClick={resend}>{resending ? "Đang gửi…" : "Gửi lại email xác minh"}</Button>}
      {resent && <p role="status">Nếu tài khoản cần xác minh, chúng tôi đã gửi email mới.</p>}
      <Button type="submit" disabled={busy}>{busy ? "Đang xử lý…" : registering ? "Đăng ký" : "Đăng nhập"}</Button>
    </form>
  </main>;
}
