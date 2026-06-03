"""
SummaryAgent — 三星個股深度分析（含公司資訊 + 新聞消息面）+ 市場深度總結
"""

import os
from dotenv import load_dotenv
load_dotenv(override=True)
import anthropic

from agents.voting_agent import VoteResult
from data.price_data import get_name
from data.sector_map import get_sector, get_sector_emoji
from data.fundamental_data import fetch_stock_news, get_company_description


def _client():
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


# ──────────────────────────────────────────
# 三星個股深度分析（含公司資訊 + 新聞）
# ──────────────────────────────────────────

def analyze_three_star_stocks(
    three_star:   list[VoteResult],
    adx_market:   float,
    fundamentals: dict[str, dict] | None = None,
) -> list[dict]:
    """
    每支三星股票做深度分析，包含：
    - 公司業務簡介
    - 技術/籌碼/基本面評分明細
    - 近期新聞消息（最多5則）
    - Claude 深度分析
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or not three_star:
        return []

    client  = _client()
    results = []

    for v in three_star[:10]:
        code     = v.ticker.replace(".TW", "").replace(".TWO", "")
        name     = get_name(v.ticker)
        sector   = get_sector(v.ticker)
        emoji    = get_sector_emoji(sector)
        fund_data = (fundamentals or {}).get(v.ticker, {})

        # ── 公司簡介 ──
        company_desc = get_company_description(fund_data, max_len=120)
        industry_str = fund_data.get("industry", "") or fund_data.get("sector", "")

        # ── 近期新聞（最重要！） ──
        news_items = fetch_stock_news(v.ticker, max_news=5)
        if news_items:
            news_str = "\n".join([
                f"  [{i+1}] {n['title']}（{n['publisher']}）"
                for i, n in enumerate(news_items)
            ])
        else:
            news_str = "  （無近期新聞資料）"

        # ── 基本面摘要 ──
        pe      = fund_data.get("pe")
        roe     = fund_data.get("roe")
        eps     = fund_data.get("eps")
        growth  = fund_data.get("revenue_growth")
        fund_str_parts = []
        if pe:    fund_str_parts.append(f"PE={pe:.1f}")
        if roe:   fund_str_parts.append(f"ROE={roe*100:.1f}%")
        if eps:   fund_str_parts.append(f"EPS={eps:.2f}")
        if growth:fund_str_parts.append(f"營收成長={growth*100:.0f}%")
        fund_str = "、".join(fund_str_parts) if fund_str_parts else "基本面資料不足"

        # ── 各 Agent 評分明細 ──
        score_detail = "\n".join([
            f"  {k}：{sc:.0f}分"
            for k, sc in v.agent_scores.items()
        ])

        # ── 觸發信號 ──
        signals_str = "、".join(v.top_signals[:5])

        prompt = f"""你是台股頂尖投資分析師，對以下個股進行深度專業分析。

【股票資訊】
代號：{code}　名稱：{name}
產業族群：{sector}　細分：{industry_str}
收盤價：＄{v.current_price:.0f}　ADX：{v.adx:.1f}
綜合評分：{v.final_score:.0f}/100（⭐⭐⭐頂級信號）

【公司業務】
{company_desc if company_desc else "（無資料）"}

【各維度評分】
{score_detail}

【觸發信號】
{signals_str}

【基本面數據】
{fund_str}

【近期新聞消息】（請重點分析這些消息對股價的影響）
{news_str}

【大盤環境】
ADX {adx_market:.0f}（{"強趨勢市" if adx_market >= 35 else "趨勢市" if adx_market >= 25 else "盤整市"}）

請用繁體中文給出深度分析，格式：

**🏢 公司定位**
（1句：說明這家公司在產業鏈的角色與核心競爭力）

**📰 消息面解讀**
（根據近期新聞，分析利多/利空因素，說明對股價的短中期影響，2~3句）

**📊 技術面**
（目前均線型態、趨勢強度、量能狀況，1~2句）

**💼 籌碼/基本面**
（法人動向 + 財務亮點，1~2句）

**🎯 操作策略**
（1~4週中短期：進場時機建議、停損位邏輯、目標價估算依據，2~3句）

**⚠️ 主要風險**
（1~2句：消息面潛在風險 + 技術面風險）

精簡專業，字數控制在 200 字內，適合 Discord。"""

        try:
            msg = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            analysis = msg.content[0].text.strip()
        except Exception as e:
            analysis = f"（分析失敗：{e}）"

        results.append({
            "ticker":     v.ticker,
            "code":       code,
            "name":       name,
            "sector":     sector,
            "emoji":      emoji,
            "score":      v.final_score,
            "price":      v.current_price,
            "adx":        v.adx,
            "signals":    v.top_signals,
            "analysis":   analysis,
            "news":       news_items,
            "company":    company_desc,
        })

    return results


# ──────────────────────────────────────────
# 市場深度總結（Sonnet 等級）
# ──────────────────────────────────────────

def generate_summary(
    three_star:     list[VoteResult],
    two_star:       list[VoteResult],
    adx_market:     float,
    sector_ranking: list[tuple[str, float]],
) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return "（未設定 ANTHROPIC_API_KEY，跳過 AI 總結）"

    client    = _client()
    mkt_state = "強趨勢" if adx_market >= 35 else ("趨勢市" if adx_market >= 25 else "盤整市")

    # 前 15 強標的摘要
    top_stocks = []
    for v in (three_star + two_star)[:15]:
        code   = v.ticker.replace(".TW", "").replace(".TWO", "")
        name   = get_name(v.ticker)
        sector = get_sector(v.ticker)
        chips  = ""
        inst   = v.agent_scores.get("InstitutionalAgent", 50)
        if v.has_chips:
            chips = "🏦法人買" if inst >= 70 else ("🔴法人賣" if inst <= 30 else "")
        top_stocks.append(
            f"• {code} {name}｜{sector}｜{v.final_score:.0f}分 {chips}｜{', '.join(v.top_signals[:2])}"
        )

    # 族群主分類聚合
    from data.sector_map import SECTOR_GROUP
    group_scores: dict[str, list[float]] = {}
    group_sectors: dict[str, list[str]]  = {}
    for sector, score in sector_ranking:
        group = SECTOR_GROUP.get(sector, sector)
        group_scores.setdefault(group, []).append(score)
        group_sectors.setdefault(group, []).append(f"{sector}({score:.0f})")
    group_avg = sorted(
        [(g, sum(s)/len(s)) for g, s in group_scores.items()],
        key=lambda x: -x[1]
    )
    sector_str = "\n".join([
        f"  {g}（{sc:.0f}分）：{' / '.join(group_sectors[g][:3])}"
        for g, sc in group_avg[:6]
    ])

    # 三星摘要
    three_star_str = "\n".join([
        f"  ⭐⭐⭐ {v.ticker.replace('.TW','').replace('.TWO','')} {get_name(v.ticker)}"
        f"（{get_sector(v.ticker)}，{v.final_score:.0f}分）"
        for v in three_star[:5]
    ]) or "  （今日無三星信號）"

    prompt = f"""你是台股頂尖量化分析師，根據今日全市場 9 Agent 聯合評分結果，給出深度市場總結。

【今日市場數據】
大盤 ADX：{adx_market:.1f}（{mkt_state}）
三星信號：{len(three_star)} 檔　雙星信號：{len(two_star)} 檔

【三星頂級標的】
{three_star_str}

【各大族群強弱（細分）】
{sector_str}

【今日最強前 15 標的】
{chr(10).join(top_stocks) if top_stocks else "無"}

請用繁體中文給出深度專業總結：

## 📊 今日市場解讀
（大盤趨勢強弱、整體資金動向、市場氛圍，2~3句）

## 🔥 最強族群深度分析
（前 2~3 名族群：各1~2句，說明強勢原因、當前題材驅動力、是否仍有追入價值）

## 💎 今日精選亮點
（三星或最強雙星中，點評 2~3 支最值得關注的股票，各1~2句核心理由，包含消息面觀點）

## 🎯 中短期操作建議
（1~4週策略：進場策略、倉位管理、重點注意事項，3~4句）

## ⚠️ 本週主要風險
（2句：技術面 + 消息面 + 總體環境的主要風險因素）

字數 300~400 字，觀點鮮明有深度，適合 Discord 閱讀。"""

    try:
        msg = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        return f"（AI 總結失敗：{e}）"
