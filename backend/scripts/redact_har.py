#!/usr/bin/env python3
"""Xóa cookie, token, header xác thực khỏi file HAR trước khi gửi cho người khác.

    python3 backend/scripts/redact_har.py in.har out.har

Giữ lại URL, tham số báo cáo, và phần thân phản hồi (đơn hàng, sub_id) để đọc được dữ liệu.
Luôn mở out.har bằng mắt trước khi gửi; script chỉ là lớp bảo vệ thứ nhất.
"""
import json
import re
import sys

# Che theo mẫu tên (bắt cả X-CSRFToken, X-Sap-Sec, af-ac-enc-*...) thay vì danh sách cố định dễ sót.
SENSITIVE_HEADERS = re.compile(r"cookie|auth|token|csrf|sap-|sign|enc|session|secret|key", re.I)
SENSITIVE_PARAMS = re.compile(r"(token|csrf|sign|signature|spc_|cookie|session|password|key)", re.I)
MASK = "[REDACTED]"
BODY_SECRET = re.compile(r'("(?:[^"]*(?:token|csrf|password|cookie|session|secret)[^"]*)"\s*:\s*)"[^"]*"', re.I)


def _headers(items):
    for h in items or []:
        if SENSITIVE_HEADERS.search(str(h.get("name", ""))):
            h["value"] = MASK


def _params(items):
    for p in items or []:
        if SENSITIVE_PARAMS.search(str(p.get("name", ""))):
            p["value"] = MASK


def _scrub_url(url: str) -> str:
    return re.sub(r"([?&][^=&]*(?:token|csrf|sign|signature|spc_|session|key)[^=&]*=)[^&]*", r"\1" + MASK, url, flags=re.I)


def redact(har: dict) -> dict:
    for e in har.get("log", {}).get("entries", []):
        req, res = e.get("request", {}), e.get("response", {})
        _headers(req.get("headers")); _headers(res.get("headers"))
        req["cookies"] = []; res["cookies"] = []
        _params(req.get("queryString")); _params((req.get("postData") or {}).get("params"))
        if "url" in req:
            req["url"] = _scrub_url(req["url"])
        pd = req.get("postData") or {}
        if isinstance(pd.get("text"), str):
            pd["text"] = BODY_SECRET.sub(lambda m: m.group(1) + f'"{MASK}"', pd["text"])
        c = res.get("content") or {}
        if isinstance(c.get("text"), str):
            c["text"] = BODY_SECRET.sub(lambda m: m.group(1) + f'"{MASK}"', c["text"])
    return har


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Cách dùng: redact_har.py in.har out.har", file=sys.stderr)
        return 2
    with open(argv[0], encoding="utf-8") as f:
        har = json.load(f)
    with open(argv[1], "w", encoding="utf-8") as f:
        json.dump(redact(har), f, ensure_ascii=False, indent=1)
    print(f"Đã ghi {argv[1]}. Mở file và tìm 'cookie', 'token', 'csrf' bằng mắt trước khi gửi.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
