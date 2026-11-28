import { Suspense } from "react";
import ResetPasswordPage from "@/features/auth/ResetPasswordPage";
export default function Page() { return <Suspense fallback={<main className="page"><p role="status">Đang tải…</p></main>}><ResetPasswordPage /></Suspense>; }
