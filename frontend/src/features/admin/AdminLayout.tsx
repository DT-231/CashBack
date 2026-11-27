"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { ApiError, api } from "@/lib/api-client";
import { Button } from "@/components/ui";

export default function AdminLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [allowed, setAllowed] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api.me().then((user) => {
      if (!active) return;
      setAllowed(user.role === "admin");
      setReady(true);
    }).catch((cause: unknown) => {
      if (!active) return;
      if (cause instanceof ApiError && cause.isAuth) router.replace("/login");
      else { setError(cause instanceof ApiError && cause.status === 0 ? "Không kết nối được máy chủ" : "Không thể tải tài khoản. Vui lòng thử lại."); setReady(true); }
    });
    return () => { active = false; };
  }, [router]);
  async function logout() {
    try { await api.logout(); } catch { /* Về đăng nhập kể cả khi phiên đã hết hạn. */ }
    finally { router.replace("/login"); }
  }
  if (!ready) return <main className="page"><p role="status">Đang tải tài khoản…</p></main>;
  if (error) return <main className="page"><p role="alert">{error}</p></main>;
  if (!allowed) return <main className="page"><p role="alert">Bạn không có quyền truy cập</p></main>;
  return <><header className="topbar"><a href="/admin/withdrawals">CashBack</a><nav aria-label="Khu vực quản trị"><a href="/admin/withdrawals">Rút tiền</a><a href="/admin/mfa">Đăng nhập hai lớp</a></nav><Button type="button" onClick={logout}>Đăng xuất</Button></header>{children}</>;
}
