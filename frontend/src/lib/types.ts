/** Kiểu dữ liệu khớp schema của backend (các file schemas.py trong backend/app/modules). UI chỉ hiển thị, KHÔNG tính toán trên các giá trị này. */
export type UserOut = { id: number; email: string; role: "member" | "staff" | "admin"; status: string };

export type ProductOut = { shop_id: number; item_id: number; name: string | null };
export type LinkOut = { code: string; go_url: string | null; direct_url: string; product: ProductOut };
export type UserLinkOut = { code: string; go_url: string | null; product: ProductOut; created_at: string; clicks: number };

export type WalletOut = { pending_vnd: number; available_vnd: number; held_vnd: number; share_pct: number };
export type EntryOut = {
  id: number; kind: string; state: string; amount_vnd: number;
  order_id: number | null; withdrawal_id: number | null; created_at: string;
};

/** Đơn của tôi. Số tiền và mốc thời gian do backend tính; UI chỉ hiển thị (ADR 0005). */
export type OrderOut = {
  id: number;
  order_ref: string;
  status: "PENDING" | "COMPLETED" | "CANCELLED" | "RETURNED";
  product_name: string | null;
  purchased_at: string | null;
  refund_vnd: number;
  refund_state: "none" | "pending" | "available" | "cancelled" | "reversed";
  expected_release_at: string | null;
};
/** Rút tiền. Số tiền, mốc thời gian, cờ usable_now, transfer_note do backend tính; UI chỉ hiển thị (ADR 0005). */
export type BankAccountOut = {
  id: number; bank_code: string; account_name: string; last4: string;
  usable_from: string; usable_now: boolean; created_at: string;
};
export type BankAccountIn = { bank_code: string; account_no: string; account_name: string };
export type WithdrawalStatus = "requested" | "approved" | "rejected" | "processing" | "paid" | "failed";
export type WithdrawalOut = {
  id: number; amount_vnd: number; status: WithdrawalStatus; bank_account_id: number | null;
  bank_code: string | null; last4: string | null; provider_ref: string | null; decided_reason: string | null;
  created_at: string; updated_at: string;
};
export type AdminWithdrawalOut = WithdrawalOut & {
  transfer_note: string; user_id: number; approved_by: number | null; approved_at: string | null;
  paid_by: number | null; paid_at: string | null;
};
export type PayoutAccountOut = { withdrawal_id: number; amount_vnd: number; bank_code: string; account_no: string; account_name: string };
export type WithdrawalRules = {
  withdrawals_enabled: boolean; min_withdraw_vnd: number; bank_change_cooldown_hours: number; max_bank_accounts: number;
};
/** Đăng nhập hai lớp (TOTP) */
export type MfaStatus = { enabled: boolean; pending: boolean; verified: boolean };
export type MfaSetup = { secret: string; otpauth_uri: string };
export type MfaEnableOut = { recovery_codes: string[] };
export type ApiErrorBody = { error: { code: string; message: string; request_id: string | null } };
