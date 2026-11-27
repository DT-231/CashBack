import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async headers() {
    return [{
      source: "/(.*)",
      headers: [
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "X-Frame-Options", value: "DENY" },
        // Trang đặt lại mật khẩu/xác minh email nhận token từ liên kết: không bao giờ gửi Referer sang nơi khác
        { key: "Referrer-Policy", value: "no-referrer" },
        // Không nhúng khung, không đổi base URI, form chỉ gửi về chính origin, cấm <object>. (CSP chặn script cần nonce qua middleware: chưa làm)
        { key: "Content-Security-Policy", value: "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'" },
        { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
        { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()" },
        { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
      ],
    }];
  },
};
export default config;
