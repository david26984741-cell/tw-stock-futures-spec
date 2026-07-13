#!/usr/bin/env python3
# 每日抓取股票期貨標的收盤價（上市 TWSE + 上櫃 TPEx），輸出 prices.json
# 由 GitHub Actions 於收盤後執行；網站讀取同源 prices.json（無 CORS 問題）
import json, urllib.request, datetime, sys

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.tpex.org.tw/",
}

def get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read().decode("utf-8", "replace")
    return json.loads(raw)

def clean_price(v):
    if v is None: return None
    s = str(v).replace(",", "").strip()
    try:
        f = float(s); return f if f > 0 else None
    except: return None

def pick(d, keys):
    for k in keys:
        if k in d and d[k] not in (None, ""): return d[k]
    return None

def roc_to_ad(s):
    s = str(s).strip()
    if len(s) == 7 and s.isdigit():
        return f"{int(s[:3])+1911}-{s[3:5]}-{s[5:7]}"
    if len(s) == 8 and s.isdigit():   # 西元 yyyymmdd
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s

secids = set(str(it["underlyingId"]) for it in json.load(open("stock_futures.json", encoding="utf-8")))
prices, dates, debug = {}, {}, {}

# 1) 上市 TWSE
try:
    tw = get_json("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL")
    for row in tw:
        code = str(pick(row, ["Code"]))
        if code in secids:
            p = clean_price(pick(row, ["ClosingPrice"]))
            if p is not None:
                prices[code] = p
                dates[code] = roc_to_ad(pick(row, ["Date"]))
    debug["twse"] = {"records": len(tw), "matched": sum(1 for c in secids if c in prices)}
except Exception as e:
    debug["twse"] = {"error": repr(e)}

# 2) 上櫃 TPEx（多端點嘗試 + 欄位自動偵測）
code_keys = ["SecuritiesCompanyCode", "Code", "CompanyCode", "SecuritiesCode", "stkno"]
price_keys = ["Close", "ClosingPrice", "close", "LastPrice", "ClosePrice"]
date_keys = ["Date", "date"]
tpex_endpoints = [
    "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes",
    "https://wwwc.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes",
    "https://www.tpex.org.tw/openapi/v1/tpex_esb_latest_statistics",
]
debug["tpex_tries"] = []
for url in tpex_endpoints:
    entry = {"url": url}
    try:
        tp = get_json(url)
        entry["records"] = len(tp)
        entry["keys"] = list(tp[0].keys()) if tp else []
        added = 0
        for row in tp:
            code = pick(row, code_keys)
            if code is None: continue
            code = str(code).strip()
            if code in secids and code not in prices:
                p = clean_price(pick(row, price_keys))
                if p is not None:
                    prices[code] = p; added += 1
                    d = pick(row, date_keys)
                    if d: dates[code] = roc_to_ad(d)
        entry["added"] = added
        debug["tpex_tries"].append(entry)
        if added > 0: break
    except Exception as e:
        entry["error"] = repr(e)[:200]
        debug["tpex_tries"].append(entry)

quote_date = sorted(dates.values())[-1] if dates else ""
missing = sorted(c for c in secids if c not in prices)
out = {
    "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "quoteDate": quote_date,
    "count": len(prices),
    "total": len(secids),
    "prices": {k: prices[k] for k in sorted(prices)},
    "missing": missing,
    "debug": debug,
}
json.dump(out, open("prices.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"matched {len(prices)}/{len(secids)}; missing {len(missing)}")
print("debug:", json.dumps(debug, ensure_ascii=False)[:500])
