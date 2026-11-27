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
export type ApiErrorBody = { error: { code: string; message: string; request_id: string | null } };
