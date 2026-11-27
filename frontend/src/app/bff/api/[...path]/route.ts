import { handleProxy } from "@/lib/bff/proxy";

export const dynamic = "force-dynamic";

async function handler(request: Request, ctx: { params: Promise<{ path: string[] }> }) {
  return handleProxy(request, (await ctx.params).path);
}
export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const DELETE = handler;
export const PATCH = handler;
