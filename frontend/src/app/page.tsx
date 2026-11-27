import Link from "next/link";

export default function Home() {
  return <main className="page hero"><h1>CashBack</h1><p>Tạo link sản phẩm Shopee và nhận hoàn tiền khi mua sắm.</p>
    <nav aria-label="Tài khoản"><Link className="button" href="/login">Đăng nhập</Link><Link className="button secondary" href="/register">Đăng ký</Link></nav>
  </main>;
}
