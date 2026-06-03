"""
重大公告資料層 — 改用 yfinance 新聞 + MOPS 即時重訊
TWSE 舊 API 已失效，改用可靠來源
"""

import requests
from data.fundamental_data import fetch_stock_news

POSITIVE_KEYWORDS = [
    "獲利", "盈餘", "EPS", "配息", "股利", "法說", "營收創新高", "新高",
    "轉型", "合作", "訂單", "買回", "庫藏股", "增資", "投資", "中標",
    "突破", "拿下", "合約", "策略聯盟", "漲價", "擴產", "新產品",
]
NEGATIVE_KEYWORDS = [
    "虧損", "虧損擴大", "停業", "下市", "警示", "違約", "裁員",
    "火災", "停工", "訴訟", "罰款", "處分", "召回", "下架", "衰退",
]


def fetch_announcements(date_str: str | None = None) -> dict[str, list[str]]:
    """
    從 MOPS 抓取當日重大訊息
    失敗時靜默回傳空字典（由 AnnouncementAgent 給中性分）
    """
    result: dict[str, list[str]] = {}
    try:
        # MOPS 即時重大訊息 RSS
        headers = {"User-Agent": "Mozilla/5.0"}
        url = "https://mops.twse.com.tw/mops/web/ajax_t05st01"
        params = {
            "encodeURIComponent": "1",
            "step": "1",
            "firstin": "1",
            "off": "1",
            "TYPEK": "sii",
            "d1": date_str or "",
        }
        resp = requests.post(url, data=params, headers=headers, timeout=10)
        # 嘗試解析簡易格式
        if resp.status_code == 200 and "<table" in resp.text:
            from html.parser import HTMLParser
            class TableParser(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.in_td = False
                    self.cells = []
                    self.current = []
                def handle_starttag(self, tag, attrs):
                    if tag == "td":
                        self.in_td = True
                def handle_endtag(self, tag):
                    if tag == "td":
                        self.in_td = False
                        self.cells.append("".join(self.current).strip())
                        self.current = []
                    elif tag == "tr" and len(self.cells) >= 4:
                        code  = self.cells[0].strip()
                        title = self.cells[3].strip() if len(self.cells) > 3 else ""
                        if code.isdigit() and len(code) == 4 and title:
                            result.setdefault(code, []).append(title)
                        self.cells = []
                def handle_data(self, data):
                    if self.in_td:
                        self.current.append(data)
            p = TableParser()
            p.feed(resp.text)
    except Exception:
        pass   # 靜默失敗，回傳空字典

    if result:
        print(f"[OK] 重大公告：{len(result)} 支有公告")
    else:
        print("[INFO] 重大公告：無資料（使用 yfinance 新聞替代）")
    return result


def get_news_sentiment(ticker: str) -> tuple[int, list[str]]:
    """
    用 yfinance 新聞做情緒判斷（補充公告資料不足時）
    回傳 (score_delta, signals)
    """
    news = fetch_stock_news(ticker, max_news=5)
    if not news:
        return 0, []

    titles = [n["title"] for n in news]
    pos = sum(1 for t in titles for kw in POSITIVE_KEYWORDS if kw in t)
    neg = sum(1 for t in titles for kw in NEGATIVE_KEYWORDS if kw in t)

    if pos > neg:
        return min(pos * 5, 15), [f"新聞偏多({titles[0][:20]})"]
    elif neg > pos:
        return -min(neg * 5, 15), [f"新聞偏空({titles[0][:20]})"]
    return 0, []


def classify_announcement(titles: list[str]) -> tuple[int, list[str]]:
    if not titles:
        return 0, []
    pos = sum(1 for t in titles for kw in POSITIVE_KEYWORDS if kw in t)
    neg = sum(1 for t in titles for kw in NEGATIVE_KEYWORDS if kw in t)
    if pos > 0 and neg == 0:
        return min(pos * 8, 20), [f"利多公告x{pos}（{titles[0][:15]}）"]
    elif neg > 0 and pos == 0:
        return -min(neg * 10, 20), [f"利空公告x{neg}（{titles[0][:15]}）"]
    elif pos > 0 and neg > 0:
        return (pos - neg) * 3, [f"公告混雜(利多{pos}/利空{neg})"]
    return 3, [f"有公告（{titles[0][:15]}）"]
