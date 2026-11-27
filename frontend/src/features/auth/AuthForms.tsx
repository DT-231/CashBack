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
  const registering = mode === "register";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    if (registering && password.length < 10) { setError("Mật khẩu cần có ít nhất 10 ký tự"); return; }
    setBusy(true); setError("");
    try {
      if (registering) await api.register(email, password);
      await api.login(email, password);
      router.push("/links");
    } catch (cause) { setError(message(cause, registering)); }
    finally { setBusy(false); }
  }

  return <main className="panel auth-panel"><h1>{registering ? "Tạo tài khoản" : "Đăng nhập"}</h1>
    <form onSubmit={submit}>
      <TextField label="Email" id={`${mode}-email`} type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      <TextField label="Mật khẩu" id={`${mode}-password`} type="password" autoComplete={registering ? "new-password" : "current-password"} required value={password} onChange={(e) => setPassword(e.target.value)} />
      {error && <Alert>{error}</Alert>}
      <Button type="submit" disabled={busy}>{busy ? "Đang xử lý…" : registering ? "Đăng ký" : "Đăng nhập"}</Button>
    </form>
  </main>;
}
