"""
籌碼資料層 — 爬取公開資訊觀測站（TWSE）
1. 三大法人買賣超（T86）
2. 融資融券餘額（MI_MARGN）
"""

import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ      = ZoneInfo("Asia/Taipei")
HEADERS = {"User-Agent": "Mozilla/5.0"}


def _to_int(s) -> int:
    """把 '1,234,567' 或整數轉成 int"""
    try:
        return int(str(s).replace(",", "").strip())
    except Exception:
        return 0


# ──────────────────────────────────────────
# 1. 三大法人買賣超（T86）
# ──────────────────────────────────────────

def fetch_institutional(date_str: str) -> dict[str, dict]:
    """
    回傳 {code: {foreign_net, trust_net, dealer_net, total_net}}
    單位：張（原始是「股」，除以 1000）
    """
    url    = "https://www.twse.com.tw/rwd/zh/fund/T86"
    params = {"response": "json", "date": date_str, "selectType": "ALL"}
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        data = resp.json()
        if data.get("stat") != "OK" or not data.get("data"):
            return {}

        # 欄位 index（確認於 2026-06-03）
        # [0]=代號 [1]=名稱
        # [4]=外資買賣超(股) [10]=投信買賣超(股) [11]=自營商買賣超(股) [18]=三大法人(股)
        result = {}
        for row in data["data"]:
            if len(row) < 19:
                continue
            code = str(row[0]).strip()
            if not code[:4].isdigit():
                continue
            result[code] = {
                "foreign_net": _to_int(row[4])  // 1000,
                "trust_net":   _to_int(row[10]) // 1000,
                "dealer_net":  _to_int(row[11]) // 1000,
                "total_net":   _to_int(row[18]) // 1000,
            }
        print(f"[OK] 三大法人：{len(result)} 支（{date_str}）")
        return result
    except Exception as e:
        print(f"[WARN] 三大法人抓取失敗（{date_str}）：{e}")
        return {}


# ──────────────────────────────────────────
# 2. 融資融券餘額（MI_MARGN）
# ──────────────────────────────────────────

def fetch_margin(date_str: str) -> dict[str, dict]:
    """
    回傳 {code: {margin_balance, margin_change, short_balance, short_change}}
    單位：張（原始已是交易單位）
    """
    url    = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN"
    params = {"response": "json", "date": date_str, "selectType": "ALL"}
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        data = resp.json()
        if data.get("stat") != "OK":
            return {}

        tables = data.get("tables", [])
        # table[1] = 個股明細
        # 欄位：[代號, 名稱, 融資買進, 融資賣出, 融資現金償還, 融資前日餘額, 融資今日餘額, ...,
        #        融券買進, 融券賣出, 融券現券償還, 融券前日餘額, 融券今日餘額, ...]
        if len(tables) < 2:
            return {}

        result = {}
        for row in tables[1].get("data", []):
            code = str(row[0]).strip()
            if not code[:4].isdigit():
                continue
            margin_prev = _to_int(row[5])
            margin_now  = _to_int(row[6])
            short_prev  = _to_int(row[11])
            short_now   = _to_int(row[12])
            result[code] = {
                "margin_balance": margin_now,
                "margin_change":  margin_now - margin_prev,
                "short_balance":  short_now,
                "short_change":   short_now - short_prev,
            }
        print(f"[OK] 融資融券：{len(result)} 支（{date_str}）")
        return result
    except Exception as e:
        print(f"[WARN] 融資融券抓取失敗（{date_str}）：{e}")
        return {}


# ──────────────────────────────────────────
# 3. 自動找最近有效交易日
# ──────────────────────────────────────────

def fetch_latest_chips() -> tuple[dict, dict]:
    """
    往回最多找 7 個日曆日，跳過週末，回傳最近有效的籌碼資料
    """
    now = datetime.now(TZ)
    for delta in range(0, 8):
        d = now - timedelta(days=delta)
        if d.weekday() >= 5:   # 週六=5, 週日=6
            continue
        date_str = d.strftime("%Y%m%d")
        inst = fetch_institutional(date_str)
        marg = fetch_margin(date_str)
        if inst or marg:
            return inst, marg

    print("[WARN] 找不到有效交易日籌碼資料")
    return {}, {}
