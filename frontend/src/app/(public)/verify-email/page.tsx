import { Suspense } from "react";
import VerifyEmailPage from "@/features/auth/VerifyEmailPage";
export default function Page() { return <Suspense fallback={<main className="page"><p role="status">Đang tải…</p></main>}><VerifyEmailPage /></Suspense>; }
