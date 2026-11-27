import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "@/lib/api-client";

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

describe("api-client: rút tiền, admin, TOTP", () => {
  const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json" } });
  type Fn = ReturnType<typeof vi.fn>;
  const all = (f: Fn) => f.mock.calls as unknown as [string, RequestInit][];
  const call = (f: Fn, i = 0) => all(f)[i];
  const sig = (f: Fn) => all(f).map((c) => `${c[1].method} ${c[0]}`);

  it("requestWithdrawal gửi Idempotency-Key và X-CSRF, đúng body", async () => {
    const f = vi.fn(async () => json({ id: 1 }, 201));
    vi.stubGlobal("fetch", f);
    await api.requestWithdrawal({ amount_vnd: 200000, bank_account_id: 3 }, "key-1234567890");
    const [url, init] = call(f);
    expect(url).toBe("/bff/api/me/withdrawals");
    expect(init.method).toBe("POST");
    const h = init.headers as Record<string, string>;
    expect(h["idempotency-key"]).toBe("key-1234567890");
    expect(h["x-csrf"]).toBe("1");
    expect(JSON.parse(String(init.body))).toEqual({ amount_vnd: 200000, bank_account_id: 3 });
  });
  it("các đường dẫn và phương thức của người dùng", async () => {
    const f = vi.fn(async () => json([]));
    vi.stubGlobal("fetch", f);
    await api.withdrawalRules(); await api.bankAccounts(); await api.myWithdrawals({ limit: 10, offset: 20 });
    await api.addBankAccount({ bank_code: "VCB", account_no: "123456789", account_name: "A B" });
    expect(sig(f)).toEqual([
      "GET /bff/api/me/withdrawals/rules", "GET /bff/api/me/bank-accounts", "GET /bff/api/me/withdrawals?limit=10&offset=20",
      "POST /bff/api/me/bank-accounts"]);
  });
  it("các đường dẫn admin (id số, status lọc)", async () => {
    const f = vi.fn(async () => json({}));
    vi.stubGlobal("fetch", f);
    await api.adminWithdrawals({ status: "approved", limit: 5 });
    await api.adminApprove(7); await api.adminReject(7, "ly do"); await api.adminFail(7, "loi"); await api.adminMarkPaid(7, "FT1234");
    await api.adminPayoutAccount(7);
    expect(sig(f)).toEqual([
      "GET /bff/api/admin/withdrawals?status=approved&limit=5", "POST /bff/api/admin/withdrawals/7/approve",
      "POST /bff/api/admin/withdrawals/7/reject", "POST /bff/api/admin/withdrawals/7/fail",
      "POST /bff/api/admin/withdrawals/7/mark-paid", "GET /bff/api/admin/withdrawals/7/payout-account"]);
    expect(JSON.parse(String(call(f, 2)[1].body))).toEqual({ reason: "ly do" });
    expect(JSON.parse(String(call(f, 4)[1].body))).toEqual({ provider_ref: "FT1234" });
  });
  it("TOTP: verify đi qua /bff/auth/mfa-verify (đổi cookie), còn lại qua /bff/api", async () => {
    const f = vi.fn(async () => json({ ok: true }));
    vi.stubGlobal("fetch", f);
    await api.mfaVerify({ code: "123456" }); await api.mfaVerify({ recovery_code: "aaaaa-bbbbb" });
    await api.mfaStatus(); await api.mfaSetup(); await api.mfaEnable("123456");
    expect(sig(f)).toEqual([
      "POST /bff/auth/mfa-verify", "POST /bff/auth/mfa-verify", "GET /bff/api/auth/mfa/status",
      "POST /bff/api/auth/mfa/setup", "POST /bff/api/auth/mfa/enable"]);
    expect(JSON.parse(String(call(f, 1)[1].body))).toEqual({ recovery_code: "aaaaa-bbbbb" });
  });
  it("adminExportCsv trả Blob và báo lỗi mfa_required như ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("a,b", { status: 200, headers: { "content-type": "text/csv" } })));
    expect(await (await api.adminExportCsv()).text()).toBe("a,b");
    vi.stubGlobal("fetch", vi.fn(async () => json({ error: { code: "mfa_required", message: "cần TOTP", request_id: "r" } }, 403)));
    const e = await api.adminExportCsv().catch((x) => x);
    expect(e).toBeInstanceOf(ApiError);
    expect(e.isMfaRequired).toBe(true);
    expect(e.isAuth).toBe(false);
  });
  it("mfa_invalid (401) không bị coi là hết phiên", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({ error: { code: "mfa_invalid", message: "sai", request_id: "r" } }, 401)));
    const e = await api.mfaVerify({ code: "000000" }).catch((x) => x);
    expect(e).toBeInstanceOf(ApiError);
    expect(e.isAuth).toBe(false);
    expect(e.isMfaRequired).toBe(false);
  });
});
