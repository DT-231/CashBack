"use client";

import { useEffect, useState, type FormEvent } from "react";
import { ApiError, api } from "@/lib/api-client";
import type { LinkOut, UserLinkOut } from "@/lib/types";
import { formatDateTime } from "@/lib/format";
import { Alert, Button, CopyButton, TextField } from "@/components/ui";

const LIMIT = 50;
function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 0) return "Không kết nối được máy chủ";
    if (error.code === "invalid_input") return error.message;
    return error.message || "Có lỗi xảy ra. Vui lòng thử lại.";
  }
  return "Có lỗi xảy ra. Vui lòng thử lại.";
}
function productName(product: { name: string | null; shop_id: number; item_id: number }) {
  return product.name || `Sản phẩm ${product.item_id} (shop ${product.shop_id})`;
}

export default function LinksPage() {
  const [url, setUrl] = useState("");
  const [created, setCreated] = useState<LinkOut | null>(null);
  const [links, setLinks] = useState<UserLinkOut[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [listError, setListError] = useState("");

  async function loadFirst() {
    setListError("");
    try { setLinks(await api.myLinks({ limit: LIMIT, offset: 0 })); }
    catch (cause) { setListError(errorMessage(cause)); }
    finally { setLoaded(true); }
  }
  useEffect(() => { void loadFirst(); }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return;
    setBusy(true); setError(""); setCreated(null);
    try { setCreated(await api.createLink(url)); setUrl(""); await loadFirst(); }
    catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(false); }
  }
  async function loadMore() {
    if (loadingMore) return;
    setLoadingMore(true); setListError("");
    try { const more = await api.myLinks({ limit: LIMIT, offset: links.length }); setLinks((current) => [...current, ...more]); }
    catch (cause) { setListError(errorMessage(cause)); }
    finally { setLoadingMore(false); }
  }

  return <main className="page">
    <section className="panel"><h1>Tạo link hoàn tiền</h1><p>Dán link sản phẩm Shopee để tạo link dành cho bạn.</p>
      <form onSubmit={submit}><TextField label="Link sản phẩm Shopee" id="shopee-url" type="url" required value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://shopee.vn/..." />
        {error && <Alert>{error}</Alert>}<Button type="submit" disabled={busy}>{busy ? "Đang tạo link…" : "Tạo link"}</Button></form>
      {created && <section className="result" aria-label="Link vừa tạo"><h2>{productName(created.product)}</h2>
        {created.go_url ? <p>Link của bạn: <a href={created.go_url}>{created.go_url}</a> <CopyButton value={created.go_url} /></p> : <p role="status">Link chuyển hướng chưa sẵn sàng</p>}
        <p>Link dự phòng: <a href={created.direct_url}>{created.direct_url}</a> <CopyButton value={created.direct_url} /></p>
      </section>}
    </section>
    <section className="panel"><h2>Link của tôi</h2>
      {!loaded ? <p role="status">Đang tải danh sách…</p> : links.length === 0 && !listError ? <p>Bạn chưa tạo link nào</p> : null}
      {listError && <Alert>{listError}</Alert>}
      {links.length > 0 && <ul className="link-list">{links.map((link) => <li key={link.code}>
        <h3>{productName(link.product)}</h3><p>Số click: {link.clicks}</p><p>Ngày tạo: {formatDateTime(link.created_at)}</p>
        {link.go_url && <CopyButton value={link.go_url} />}
      </li>)}</ul>}
      {links.length >= LIMIT && <Button type="button" disabled={loadingMore} onClick={loadMore}>{loadingMore ? "Đang tải…" : "Xem thêm"}</Button>}
    </section>
  </main>;
}
