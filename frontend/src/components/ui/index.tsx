"use client";

import { useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode } from "react";

export function Button(props: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button {...props} className={`button ${props.className ?? ""}`} />;
}

export function TextField({ label, id, ...props }: InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return <label className="field" htmlFor={id}>{label}<input id={id} {...props} /></label>;
}

export function Alert({ children }: { children: ReactNode }) {
  return <p role="alert" className="alert">{children}</p>;
}

export function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return <Button type="button" onClick={async () => { try { await navigator.clipboard.writeText(value); setCopied(true); } catch { setCopied(false); } }}>{copied ? "Đã sao chép" : "Sao chép"}</Button>;
}
