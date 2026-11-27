import type { ReactNode } from "react";

export const metadata = { title: "CashBack", description: "Hoàn tiền khi mua hàng Shopee" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
