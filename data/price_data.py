"""
資料層：取得全市場台股 OHLCV + 股票名稱
- 股票清單：爬 TWSE / TPEx ISIN 查詢頁
- 行情：yfinance（批次下載，平行執行）
"""

import requests
import pandas as pd
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import StringIO

# 全域名稱對照表 {ticker: name}，掃描期間共用
STOCK_NAMES: dict[str, str] = {}


# ──────────────────────────────────────────
# 1. 取得全市場股票清單（含名稱）
# ──────────────────────────────────────────

def _fetch_twse_list() -> list[tuple[str, str]]:
    """上市股票（TWSE），回傳 [(ticker, name), ...]"""
    url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.encoding = "big5"
        df = pd.read_html(StringIO(resp.text))[0]
        df.columns = df.iloc[0]
        df = df.iloc[1:].reset_index(drop=True)
        col = df.columns[0]
        df[["code", "name"]] = df[col].str.split("　", n=1, expand=True)
        df = df[df["code"].str.match(r"^\d{4}$", na=False)]
        return [(f"{r.code}.TW", r.name.strip()) for r in df.itertuples()]
    except Exception as e:
        print(f"[WARN] TWSE 清單抓取失敗：{e}")
        return []


def _fetch_tpex_list() -> list[tuple[str, str]]:
    """上櫃股票（TPEx），回傳 [(ticker, name), ...]"""
    url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.encoding = "big5"
        df = pd.read_html(StringIO(resp.text))[0]
        df.columns = df.iloc[0]
        df = df.iloc[1:].reset_index(drop=True)
        col = df.columns[0]
        df[["code", "name"]] = df[col].str.split("　", n=1, expand=True)
        df = df[df["code"].str.match(r"^\d{4}$", na=False)]
        return [(f"{r.code}.TWO", r.name.strip()) for r in df.itertuples()]
    except Exception as e:
        print(f"[WARN] TPEx 清單抓取失敗：{e}")
        return []


def get_all_tickers(market: str = "both") -> list[str]:
    """
    market: 'twse' / 'tpex' / 'both'
    同時填充全域 STOCK_NAMES，回傳 ticker 清單
    """
    global STOCK_NAMES
    pairs: list[tuple[str, str]] = []
    if market in ("twse", "both"):
        pairs += _fetch_twse_list()
    if market in ("tpex", "both"):
        pairs += _fetch_tpex_list()

    STOCK_NAMES = {ticker: name for ticker, name in pairs}
    tickers = list(STOCK_NAMES.keys())
    print(f"[LIST] 全市場股票清單：{len(tickers)} 支")
    return tickers


def get_name(ticker: str) -> str:
    """回傳股票中文名稱，找不到回傳代碼"""
    return STOCK_NAMES.get(ticker, ticker.replace(".TW", "").replace(".TWO", ""))


# ──────────────────────────────────────────
# 2. 批次下載 OHLCV
# ──────────────────────────────────────────

def _fetch_single(ticker: str, period: str = "3mo") -> tuple[str, pd.DataFrame | None]:
    try:
        df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
        if df.empty or len(df) < 20:
            return ticker, None
        df.columns = [c.lower() if isinstance(c, str) else c[0].lower() for c in df.columns]
        return ticker, df
    except Exception:
        return ticker, None


def fetch_market_data(
    tickers: list[str],
    period: str = "3mo",
    max_workers: int = 20,
) -> dict[str, pd.DataFrame]:
    result = {}
    total = len(tickers)
    print(f"[DL]  開始下載 {total} 支股票行情（{max_workers} 執行緒）...")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch_single, t, period): t for t in tickers}
        done = 0
        for future in as_completed(futures):
            ticker, df = future.result()
            done += 1
            if df is not None:
                result[ticker] = df
            if done % 100 == 0:
                print(f"   進度：{done}/{total}（成功 {len(result)} 支）")

    print(f"[OK] 下載完成：{len(result)}/{total} 支有效")
    return result


# ──────────────────────────────────────────
# 3. 過濾低流動性個股
# ──────────────────────────────────────────

def filter_by_liquidity(
    data: dict[str, pd.DataFrame],
    min_avg_volume: int = 1000,
) -> dict[str, pd.DataFrame]:
    filtered = {
        t: df
        for t, df in data.items()
        if df["volume"].tail(20).mean() >= min_avg_volume * 1000
    }
    print(f"[FILTER] 流動性過濾後：{len(filtered)} 支（門檻：日均 {min_avg_volume} 張）")
    return filtered
