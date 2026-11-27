"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Alert, Button } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import type { MfaStatus } from "@/lib/types";

function message(cause: unknown) {
  if (cause instanceof ApiError) {
    if (cause.isAuth) return "__auth__";
    if (cause.isMfaRequired) return "__mfa__";
    if (cause.status === 0) return "Không kết nối được máy chủ";
    if (cause.code === "mfa_invalid") return "Mã không đúng hoặc đã dùng";
    if (cause.code === "rate_limited") return "Bạn thử quá nhiều lần, vui lòng đợi";
    if (cause.code === "mfa_state") return "Trạng thái TOTP không hợp lệ, vui lòng tải lại";
    return cause.message;
  }
  return "Không thể hoàn tất yêu cầu. Vui lòng thử lại.";
}

export default function MfaPage() {
  const router = useRouter();
  const [status, setStatus] = useState<MfaStatus | null>(null);
  const [setup, setSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [codes, setCodes] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);
  const [code, setCode] = useState("");
  const [recovery, setRecovery] = useState(false);
  const [recoveryCode, setRecoveryCode] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function handleError(cause: unknown) {
    const text = message(cause);
    if (text === "__auth__") router.replace("/login");
    else if (text === "__mfa__") router.replace("/admin/mfa");
    else setError(text);
  }
  useEffect(() => {
    let active = true;
    api.mfaStatus().then((value) => { if (active) { setStatus(value); if (value.enabled && value.verified) router.replace("/admin/withdrawals"); } })
      .catch((cause: unknown) => { if (active) handleError(cause); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; setSetup(null); setCodes([]); setCode(""); setRecoveryCode(""); };
  }, [router]);

  async function startSetup() {
    if (busy) return;
    setBusy(true); setError("");
    try { setSetup(await api.mfaSetup()); }
    catch (cause) { handleError(cause); }
    finally { setBusy(false); }
  }
  async function enable(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError("");
    try { const result = await api.mfaEnable(code); setCodes(result.recovery_codes); setSaved(false); setStatus({ enabled: true, pending: false, verified: false }); setSetup(null); }
    catch (cause) { handleError(cause); }
    finally { setCode(""); setBusy(false); }
  }
  async function verify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError("");
    try {
      await api.mfaVerify(recovery ? { recovery_code: recoveryCode } : { code });
      setCode(""); setRecoveryCode(""); setSetup(null); setCodes([]);
      router.replace("/admin/withdrawals");
    } catch (cause) { handleError(cause); }
    finally { setCode(""); setRecoveryCode(""); setBusy(false); }
  }

  if (loading) return <main className="page"><p role="status">Đang tải trạng thái đăng nhập hai lớp…</p></main>;
  if (!status) return <main className="page">{error && <Alert>{error}</Alert>}</main>;
  return <main className="page"><section className="panel"><h1>Đăng nhập hai lớp</h1>
    {status.verified ? <><p>Phiên này đã xác minh</p><a className="button" href="/admin/withdrawals">Tới danh sách rút tiền</a></> : <>
      {!status.enabled && <>
        {!setup ? <Button type="button" disabled={busy} onClick={startSetup}>{status.pending ? "Thiết lập lại" : "Thiết lập"}</Button> : <>
          <p>Bí mật TOTP (nhập thủ công vào ứng dụng xác thực)</p><p className="secret-value">{setup.secret}</p>
          <label className="field">Địa chỉ otpauth (chỉ đọc)<textarea readOnly value={setup.otpauth_uri} rows={3} /></label>
          <Button type="button" className="secondary" onClick={() => { setSetup(null); setCode(""); }}>Đóng thiết lập</Button>
          <form onSubmit={enable}>
            <label className="field">Mã xác minh<input inputMode="numeric" autoComplete="one-time-code" maxLength={6} pattern="[0-9]{6}" value={code} onChange={(event) => setCode(event.target.value)} required /></label>
            {error && <Alert>{error}</Alert>}
            <Button type="submit" disabled={busy || !code}>{busy ? "Đang bật…" : "Bật"}</Button>
          </form>
        </>}
      </>}
      {codes.length > 0 && <section className="recovery-panel"><h2>Mã khôi phục</h2><p>Hãy lưu ở nơi an toàn ngoài máy này; sẽ không hiện lại.</p><ul>{codes.map((item, index) => <li key={index}>{item}</li>)}</ul>
        <label className="check-field"><input type="checkbox" checked={saved} onChange={(event) => setSaved(event.target.checked)} /> Tôi đã lưu các mã này</label>
        <Button type="button" disabled={!saved} onClick={() => setCodes([])}>Tiếp tục</Button>
      </section>}
      {status.enabled && codes.length === 0 && <form onSubmit={verify}>
        {recovery ? <label className="field">Mã khôi phục<input autoComplete="off" value={recoveryCode} onChange={(event) => setRecoveryCode(event.target.value)} required /></label>
          : <label className="field">Mã xác minh<input inputMode="numeric" autoComplete="one-time-code" maxLength={6} pattern="[0-9]{6}" value={code} onChange={(event) => setCode(event.target.value)} required /></label>}
        <Button type="button" className="secondary" onClick={() => { setRecovery((current) => !current); setCode(""); setRecoveryCode(""); setError(""); }}>{recovery ? "Dùng mã xác minh" : "Dùng mã khôi phục"}</Button>
        {error && <Alert>{error}</Alert>}
        <Button type="submit" disabled={busy || (recovery ? !recoveryCode : !code)}>{busy ? "Đang xác minh…" : "Xác minh phiên"}</Button>
      </form>}
      {!status.enabled && !setup && error && <Alert>{error}</Alert>}
    </>}
  </section></main>;
}
