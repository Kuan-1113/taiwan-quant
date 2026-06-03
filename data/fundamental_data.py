"""
基本面資料層 — yfinance .info 抓 PE/EPS/市值/公司簡介 + 近期新聞
"""

import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed

_cache: dict[str, dict] = {}
_news_cache: dict[str, list[dict]] = {}


def _fetch_one(ticker: str) -> tuple[str, dict]:
    try:
        t    = yf.Ticker(ticker)
        info = t.info
        return ticker, {
            "pe":             info.get("trailingPE"),
            "forward_pe":     info.get("forwardPE"),
            "eps":            info.get("trailingEps"),
            "roe":            info.get("returnOnEquity"),
            "profit_margin":  info.get("profitMargins"),
            "revenue_growth": info.get("revenueGrowth"),
            "market_cap":     info.get("marketCap"),
            "beta":           info.get("beta"),
            "52w_high":       info.get("fiftyTwoWeekHigh"),
            "52w_low":        info.get("fiftyTwoWeekLow"),
            # 公司基本資訊
            "long_name":      info.get("longName", ""),
            "industry":       info.get("industry", ""),
            "sector":         info.get("sector", ""),
            "description":    info.get("longBusinessSummary", ""),
            "employees":      info.get("fullTimeEmployees"),
        }
    except Exception:
        return ticker, {}


def fetch_fundamentals(tickers: list[str], max_workers: int = 10) -> dict[str, dict]:
    """批次抓取基本面（含公司簡介），結果快取"""
    global _cache
    to_fetch = [t for t in tickers if t not in _cache]
    if not to_fetch:
        return {t: _cache[t] for t in tickers if t in _cache}

    print(f"[FUNDAMENTAL] 抓取 {len(to_fetch)} 支基本面資料...")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch_one, t): t for t in to_fetch}
        for future in as_completed(futures):
            ticker, data = future.result()
            _cache[ticker] = data

    result = {t: _cache[t] for t in tickers if t in _cache}
    ok = sum(1 for d in result.values() if d.get("pe") or d.get("eps"))
    print(f"[OK] 基本面：{ok}/{len(tickers)} 支有有效數據")
    return result


def fetch_stock_news(ticker: str, max_news: int = 5) -> list[dict]:
    """
    抓取單支股票近期新聞（yfinance）
    回傳 [{title, publisher, link, providerPublishTime}, ...]
    """
    if ticker in _news_cache:
        return _news_cache[ticker]
    try:
        news = yf.Ticker(ticker).news or []
        result = []
        for n in news[:max_news]:
            result.append({
                "title":     n.get("title", ""),
                "publisher": n.get("publisher", ""),
                "link":      n.get("link", ""),
            })
        _news_cache[ticker] = result
        return result
    except Exception:
        return []


def get_company_description(info: dict, max_len: int = 150) -> str:
    """從 info dict 取得簡短公司描述"""
    desc = info.get("description", "")
    if not desc:
        industry = info.get("industry", "")
        sector   = info.get("sector", "")
        name     = info.get("long_name", "")
        if name:
            return f"{name}，{sector}・{industry}產業"
        return ""
    # 截取前 max_len 字
    return desc[:max_len] + "..." if len(desc) > max_len else desc
