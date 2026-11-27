import { handleAuth } from "@/lib/bff/auth";

export const dynamic = "force-dynamic";

export async function POST(request: Request, ctx: { params: Promise<{ action: string }> }) {
  return handleAuth(request, (await ctx.params).action);
}
export const GET = POST;
export const PUT = POST;
export const DELETE = POST;
export const PATCH = POST;
