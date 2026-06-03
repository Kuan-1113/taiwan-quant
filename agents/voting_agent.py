"""
VotingAgent — 整合全部 9 個 Agent，輸出最終評分

權重分配：
  技術面  (Trend + Momentum + Volatility)      × 0.35
  籌碼面  (Institutional + Margin)             × 0.35
  基本面  (Fundamental)                        × 0.15
  消息面  (Announcement + Sentiment)           × 0.15
"""

from dataclasses import dataclass, field
from .base_agent import AgentResult
from config import SCORE_THREE_STAR, SCORE_TWO_STAR, SCORE_ONE_STAR

TECHNICAL_AGENTS     = {"TrendAgent", "MomentumAgent", "VolatilityAgent"}
CHIPS_AGENTS         = {"InstitutionalAgent", "MarginAgent"}
FUNDAMENTAL_AGENTS   = {"FundamentalAgent"}
NEWS_AGENTS          = {"AnnouncementAgent", "SentimentAgent"}

W_TECH  = 0.35
W_CHIPS = 0.35
W_FUND  = 0.15
W_NEWS  = 0.15


@dataclass
class VoteResult:
    ticker:        str
    final_score:   float
    stars:         int
    star_label:    str
    top_signals:   list[str]
    agent_scores:  dict[str, float]
    current_price: float
    adx:       float = 0.0
    atr:       float = 0.0
    has_chips: bool  = False
    has_fund:  bool  = False
    has_news:  bool  = False

    def __repr__(self):
        return f"{self.ticker} {self.star_label} score={self.final_score:.1f}"


def _avg(results: list[AgentResult]) -> float | None:
    if not results:
        return None
    return sum(r.score for r in results) / len(results)


def _is_neutral(r: AgentResult) -> bool:
    """判斷是否為中性（無資料）的結果"""
    return any(kw in s for s in r.signals for kw in ["中性", "未取得", "無資料"])


def aggregate(
    ticker: str,
    results: list[AgentResult],
    current_price: float = 0.0,
) -> VoteResult | None:

    if not results:
        return None

    by_group = {
        "tech":  [r for r in results if r.agent_name in TECHNICAL_AGENTS],
        "chips": [r for r in results if r.agent_name in CHIPS_AGENTS],
        "fund":  [r for r in results if r.agent_name in FUNDAMENTAL_AGENTS],
        "news":  [r for r in results if r.agent_name in NEWS_AGENTS],
    }

    if not by_group["tech"]:
        return None

    tech_score  = _avg(by_group["tech"])
    chips_score = _avg(by_group["chips"])
    fund_score  = _avg(by_group["fund"])
    news_score  = _avg(by_group["news"])

    has_chips = bool(chips_score and not all(_is_neutral(r) for r in by_group["chips"]))
    has_fund  = bool(fund_score  and not all(_is_neutral(r) for r in by_group["fund"]))
    has_news  = bool(news_score  and not all(_is_neutral(r) for r in by_group["news"]))

    # 動態權重：有哪些資料就用哪些
    weight_map = {
        "tech":  W_TECH,
        "chips": W_CHIPS if has_chips else 0,
        "fund":  W_FUND  if has_fund  else 0,
        "news":  W_NEWS  if has_news  else 0,
    }
    score_map = {
        "tech":  tech_score or 0,
        "chips": chips_score or 50,
        "fund":  fund_score  or 50,
        "news":  news_score  or 50,
    }

    total_w = sum(weight_map.values())
    if total_w == 0:
        return None
    final_score = round(
        sum(score_map[k] * weight_map[k] for k in weight_map) / total_w, 1
    )

    # 星級
    if final_score >= SCORE_THREE_STAR:
        stars, star_label = 3, "⭐⭐⭐"
    elif final_score >= SCORE_TWO_STAR:
        stars, star_label = 2, "⭐⭐"
    elif final_score >= SCORE_ONE_STAR:
        stars, star_label = 1, "⭐"
    else:
        return None

    # 整合信號（排除中性標記）
    all_signals = []
    for group in by_group.values():
        for r in group:
            for s in r.signals:
                if s not in all_signals and not any(kw in s for kw in ["ATR=", "中性", "未取得", "無資料"]):
                    all_signals.append(s)
    top_signals = all_signals[:6]

    agent_scores = {r.agent_name: r.score for r in results}

    adx = atr = 0.0
    for r in results:
        if r.agent_name == "TrendAgent":
            adx = r.raw.get("adx", 0.0)
        if r.agent_name == "VolatilityAgent":
            atr = r.raw.get("atr", 0.0)

    return VoteResult(
        ticker=ticker,
        final_score=final_score,
        stars=stars,
        star_label=star_label,
        top_signals=top_signals,
        agent_scores=agent_scores,
        current_price=current_price,
        adx=adx,
        atr=atr,
        has_chips=has_chips,
        has_fund=has_fund,
        has_news=has_news,
    )
