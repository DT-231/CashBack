import { handleHealth } from "@/lib/bff/health";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export function GET() {
  return handleHealth();
}
