#!/usr/bin/env python3
# 每日抓取股票期貨標的之收盤價（上市 TWSE + 上櫃 TPEx），輸出 prices.json
# 由 GitHub Actions 於收盤後執行，網站讀取同源 prices.json（無 CORS 問題）
import json, urllib.request, datetime, sys

UA = {"User-Agent": "Mozilla/5.0 (compatible; sf-price-bot/1.0)"}

def get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))

def clean_price(v):
    if v is None: return None
    s = str(v).replace(",", "").strip()
    if s in ("", "--", "---", "N/A", "0", "0.00"): 
        try:
            f=float(s); 
            return f if f>0 else None
        except: return None
    try:
        f = float(s); return f if f > 0 else None
    except: return None

def pick(d, keys):
    for k in keys:
        if k in d and d[k] not in (None, ""): return d[k]
    return None

def roc_to_ad(s):
    # '1150709' -> '2026-07-09'
    s = str(s).strip()
    if len(s) == 7:
        return f"{int(s[:3])+1911}-{s[3:5]}-{s[5:7]}"
    return s

# 需要報價的證券代號
secids = set()
for it in json.load(open("stock_futures.json", encoding="utf-8")):
    secids.add(str(it["underlyingId"]))

prices, dates = {}, {}

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
    print("TWSE matched:", sum(1 for c in secids if c in prices))
except Exception as e:
    print("TWSE error:", e, file=sys.stderr)

# 2) 上櫃 TPEx（欄位名稱防禦式偵測）
tpex_urls = [
    "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes",
]
code_keys = ["SecuritiesCompanyCode", "Code", "CompanyCode", "stkno", "SecuritiesCode"]
price_keys = ["Close", "ClosingPrice", "close", "LastPrice"]
date_keys = ["Date", "date"]
before = len(prices)
for url in tpex_urls:
    try:
        tp = get_json(url)
        for row in tp:
            code = pick(row, code_keys)
            if code is None: continue
            code = str(code).strip()
            if code in secids and code not in prices:
                p = clean_price(pick(row, price_keys))
                if p is not None:
                    prices[code] = p
                    d = pick(row, date_keys)
                    dates[code] = roc_to_ad(d) if d else ""
        print("TPEx cumulative matched:", sum(1 for c in secids if c in prices))
        break
    except Exception as e:
        print("TPEx error:", e, file=sys.stderr)

quote_date = ""
if dates:
    quote_date = sorted(dates.values())[-1]

missing = sorted(c for c in secids if c not in prices)
out = {
    "updated": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "quoteDate": quote_date,
    "count": len(prices),
    "total": len(secids),
    "prices": {k: prices[k] for k in sorted(prices)},
    "missing": missing,
}
json.dump(out, open("prices.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"Wrote prices.json: {len(prices)}/{len(secids)} matched, {len(missing)} missing")
if missing:
    print("missing sample:", missing[:20])
