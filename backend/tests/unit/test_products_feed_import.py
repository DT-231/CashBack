import csv

from app.modules.products import feed_import as fi


def write(tmp_path, text, enc="utf-8-sig", name="src.csv"):
    p = tmp_path / name
    p.write_bytes(text.encode(enc))
    return p


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_semicolon_bom_vn_numbers_and_header_offset(tmp_path):
    src = write(tmp_path,
                "Chương trình khuyến mãi;;;\n"
                "Tên sản phẩm;ID sản phẩm;ID shop;Giá;Tỷ lệ hoa hồng;Đã bán\n"
                "Nồi A;900001;7001;690.000;8%;1.200\n"
                "Nồi B;900002;7002;159.000;6%;5.100\n")
    res = fi.convert(src, tmp_path / "out.csv")
    assert res["ok"] and res["delimiter"] == ";" and res["header_row"] == 1 and res["rows_kept"] == 2
    rows = read(tmp_path / "out.csv")
    assert [r["product_name"] for r in rows] == ["Nồi A", "Nồi B"]   # sắp theo price*rate*sold giảm dần
    assert rows[0]["price"] == "690000" and float(rows[0]["commission_rate"]) == 8.0


def test_ids_from_link_dedup_and_drops(tmp_path):
    src = write(tmp_path,
                "product_name,product_link,price,commission_rate,sales\n"
                "A,https://shopee.vn/a-i.7001.900001,100,5,10\n"
                "A lặp,https://shopee.vn/product/7001/900001,100,5,10\n"
                ",https://shopee.vn/product/1/2,1,1,1\n"
                "Không id,https://example.com/x,1,1,1\n")
    res = fi.convert(src, tmp_path / "o.csv")
    assert res["rows_kept"] == 1
    assert res["dropped"] == {"trùng item": 1, "thiếu tên sản phẩm": 1, "thiếu item_id/shop_id": 1}


def test_thresholds_and_dry_run(tmp_path):
    src = write(tmp_path, "itemid,shopid,product_name,price,commission_rate,sales\n"
                          "1,1,Lo,100,1,5\n2,2,Hi,100,9,500\n")
    res = fi.convert(src, tmp_path / "o.csv", min_rate=5, min_sales=100, dry_run=True)
    assert res["rows_kept"] == 1 and not (tmp_path / "o.csv").exists()
    assert res["dropped"]["rate dưới ngưỡng"] == 1


def test_nothing_kept_reports_error(tmp_path):
    src = write(tmp_path, "a,b\n1,2\n")
    res = fi.convert(src, tmp_path / "o.csv")
    assert not res["ok"] and "tên cột" in res["error"]


def test_empty_file(tmp_path):
    assert fi.convert(write(tmp_path, ""), tmp_path / "o.csv") == {"ok": False, "error": "file rỗng"}


def test_encoding_sniff_cp1258(tmp_path):
    p = write(tmp_path, "itemid,shopid,product_name\n1,2,Nồi chiên\n", enc="utf-16")
    text, enc = fi.sniff_text(p)
    assert "Nồi chiên" in text and enc in ("utf-16",)


def test_to_int_and_to_float():
    assert fi.to_int("1.200") == 1200 and fi.to_int("x", 7) == 7
    assert fi.to_float("1.250.000") == 1250000 and fi.to_float("259,5") == 259.5 and fi.to_float("8%") == 8
