#!/usr/bin/env python3
# 每日抓取：標的收盤價（TWSE 上市 + TPEx 上櫃）與股票期貨全市場未沖銷口數（TAIFEX）
# 特性：
#   1. 任一來源失敗／當日尚未公布時，沿用前一交易日既有資料（不會變空白）
#   2. 產生 prices.json（網站線上讀取）
#   3. 同步把最新快照內嵌回 index.html（即使離線或直接開啟檔案也看得到資料）
import json, os, re, urllib.request, datetime

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
        return json.loads(r.read().decode("utf-8", "replace"))

def num(v):
    try: return float(str(v).replace(",", "").strip())
    except: return None

def pick(d, keys):
    for k in keys:
        if k in d and d[k] not in (None, ""): return d[k]
    return None

def to_ad(s):
    s = str(s).strip()
    if len(s) == 7 and s.isdigit(): return f"{int(s[:3])+1911}-{s[3:5]}-{s[5:7]}"
    if len(s) == 8 and s.isdigit(): return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s

items = json.load(open("stock_futures.json", encoding="utf-8"))
secids   = set(str(i["underlyingId"]) for i in items)
futcodes = set(i["futuresCode"] for i in items)

# 讀取前一次結果，作為 fallback 基準
prev = {}
if os.path.exists("prices.json"):
    try: prev = json.load(open("prices.json", encoding="utf-8"))
    except Exception: prev = {}
prev_prices, prev_oi = prev.get("prices", {}), prev.get("oi", {})

prices, dates, debug = {}, {}, {}

# 1) 上市 TWSE 收盤價
try:
    tw = get_json("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL")
    for row in tw:
        code = str(pick(row, ["Code"]))
        if code in secids:
            p = num(pick(row, ["ClosingPrice"]))
            if p and p > 0:
                prices[code] = p; dates[code] = to_ad(pick(row, ["Date"]))
    debug["twse"] = {"records": len(tw), "matched": len(prices)}
except Exception as e:
    debug["twse"] = {"error": repr(e)[:200]}

# 2) 上櫃 TPEx 收盤價
try:
    tp = get_json("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes")
    added = 0
    for row in tp:
        code = pick(row, ["SecuritiesCompanyCode", "Code", "CompanyCode"])
        if code is None: continue
        code = str(code).strip()
        if code in secids and code not in prices:
            p = num(pick(row, ["Close", "ClosingPrice"]))
            if p and p > 0:
                prices[code] = p; added += 1
                d = pick(row, ["Date"])
                if d: dates[code] = to_ad(d)
    debug["tpex"] = {"records": len(tp), "added": added}
except Exception as e:
    debug["tpex"] = {"error": repr(e)[:200]}

# 3) TAIFEX 全市場未沖銷口數（僅一般時段、排除價差月份、加總各到期月）
oi, oi_date = {}, ""
try:
    fut = get_json("https://openapi.taifex.com.tw/v1/DailyMarketReportFut")
    for row in fut:
        if row.get("TradingSession") != "一般": continue
        month = str(row.get("ContractMonth(Week)", ""))
        if "/" in month: continue
        c = str(row.get("Contract", "")).strip()
        if c not in futcodes: continue
        v = num(row.get("OpenInterest"))
        if v is None: continue
        oi[c] = oi.get(c, 0) + int(v)
        if not oi_date: oi_date = to_ad(row.get("Date", ""))
    debug["taifex_oi"] = {"records": len(fut), "matched": len(oi)}
except Exception as e:
    debug["taifex_oi"] = {"error": repr(e)[:200]}

# --- Fallback：沿用前一交易日資料，避免任何欄位變空白 ---
carried_p = 0
for k, v in prev_prices.items():
    if k not in prices and k in secids:
        prices[k] = v; carried_p += 1
carried_oi = 0
for k, v in prev_oi.items():
    if k not in oi and k in futcodes:
        oi[k] = v; carried_oi += 1
if not oi and prev.get("oiDate"): oi_date = prev["oiDate"]
if not oi_date: oi_date = prev.get("oiDate", "")
debug["carried_forward"] = {"prices": carried_p, "oi": carried_oi}

quote_date = sorted(dates.values())[-1] if dates else prev.get("quoteDate", "")

out = {
    "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "quoteDate": quote_date,
    "oiDate": oi_date,
    "count": len(prices),
    "total": len(secids),
    "oiCount": len(oi),
    "oiTotal": len(futcodes),
    "prices": {k: prices[k] for k in sorted(prices)},
    "oi": {k: oi[k] for k in sorted(oi)},
    "missing": sorted(c for c in secids if c not in prices),
    "debug": debug,
}
json.dump(out, open("prices.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# --- 將最新快照內嵌回 index.html（離線／本機開啟也有資料） ---
try:
    html = open("index.html", encoding="utf-8").read()
    fb = {"prices": out["prices"], "oi": out["oi"], "quoteDate": out["quoteDate"],
          "oiDate": out["oiDate"], "count": out["count"], "total": out["total"],
          "oiCount": out["oiCount"]}
    block = "/*FALLBACK_START*/const FALLBACK=" + json.dumps(fb, ensure_ascii=False, separators=(",", ":")) + ";/*FALLBACK_END*/"
    new_html, cnt = re.subn(r"/\*FALLBACK_START\*/.*?/\*FALLBACK_END\*/", lambda m: block, html, flags=re.S)
    if cnt == 1 and new_html != html:
        open("index.html", "w", encoding="utf-8").write(new_html)
        print("index.html fallback snapshot updated")
    else:
        print("index.html unchanged (markers found=%d)" % cnt)
except Exception as e:
    print("index.html inject skipped:", repr(e)[:150])

print(f"prices {len(prices)}/{len(secids)} (carried {carried_p}) | OI {len(oi)}/{len(futcodes)} (carried {carried_oi}) | {json.dumps(debug, ensure_ascii=False)[:300]}")
