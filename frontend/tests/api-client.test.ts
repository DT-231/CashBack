import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api-client";

afterEach(() => vi.unstubAllGlobals());

describe("api.myOrders", () => {
  it("gọi GET /bff/api/me/orders với limit/offset, không gửi X-CSRF (GET)", async () => {
    const f = vi.fn(async () => new Response("[]", { status: 200, headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", f);
    expect(await api.myOrders({ limit: 20, offset: 40 })).toEqual([]);
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/bff/api/me/orders?limit=20&offset=40");
    expect(init.method).toBe("GET");
    expect((init.headers as Record<string, string>)["x-csrf"]).toBeUndefined();
  });
  it("không tham số thì không có query", async () => {
    const f = vi.fn(async () => new Response("[]", { status: 200, headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", f);
    await api.myOrders();
    expect((f.mock.calls[0] as unknown as [string])[0]).toBe("/bff/api/me/orders");
  });
});
