"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { ApiError, api } from "@/lib/api-client";
import { Button } from "@/components/ui";

export default function MemberLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { let active = true; api.me().then(() => { if (active) setReady(true); }).catch((cause) => {
    if (!active) return;
    if (cause instanceof ApiError && cause.isAuth) router.replace("/login");
    else { setError(cause instanceof ApiError && cause.status === 0 ? "Không kết nối được máy chủ" : "Không thể tải tài khoản. Vui lòng thử lại."); setReady(true); }
  }); return () => { active = false; }; }, [router]);
  async function logout() { try { await api.logout(); } catch { /* Về đăng nhập kể cả khi phiên đã hết hạn. */ } finally { router.replace("/login"); } }
  if (!ready) return <main className="page"><p role="status">Đang tải tài khoản…</p></main>;
  return <><header className="topbar"><a href="/links">CashBack</a><nav aria-label="Khu vực thành viên"><a href="/links">Link của tôi</a><a href="/orders">Đơn hàng</a><a href="/wallet">Ví của tôi</a></nav><Button type="button" onClick={logout}>Đăng xuất</Button></header>{error ? <main className="page"><p role="alert">{error}</p></main> : children}</>;
}
