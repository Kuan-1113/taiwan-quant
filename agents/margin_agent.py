"""
MarginAgent — 融資融券分析
散戶行為（融資）vs 主力控盤（融資減少 + 融券減少）
"""

from .base_agent import BaseAgent, AgentResult


class MarginAgent(BaseAgent):
    name   = "MarginAgent"
    weight = 1.0

    def analyze(self, ticker: str, chips: dict) -> AgentResult:
        """
        chips: {margin_balance, margin_change, short_balance, short_change}
        單位：張
        """
        if not chips:
            return self._empty_result(ticker)

        margin_balance = chips.get("margin_balance", 0)
        margin_change  = chips.get("margin_change",  0)
        short_balance  = chips.get("short_balance",  0)
        short_change   = chips.get("short_change",   0)

        score   = 0.0
        signals = []

        # ── 融資動向（佔 50分）──
        # 主力控盤：融資餘額低且繼續減少（散戶退出，主力吃貨）
        if margin_balance > 0:
            margin_ratio = margin_change / margin_balance if margin_balance > 0 else 0
        else:
            margin_ratio = 0

        if margin_change < 0 and margin_balance < 5000:
            # 融資低水位且繼續減少 → 最佳（主力控盤）
            score += 50
            signals.append(f"融資低水位減少(主力控盤，餘額{margin_balance:,}張)")
        elif margin_change < 0:
            # 融資減少（籌碼清洗）
            score += 30
            signals.append(f"融資減少({margin_change:+,}張)")
        elif margin_change > 0 and margin_ratio > 0.05:
            # 融資大增（散戶追高，危險）
            score += 5
            signals.append(f"融資大增({margin_change:+,}張，注意散戶追高)")
        elif margin_change > 0:
            score += 15
            signals.append(f"融資小增({margin_change:+,}張)")
        else:
            score += 25
            signals.append(f"融資持平(餘額{margin_balance:,}張)")

        # ── 融券動向（佔 30分）──
        if short_balance > 0 and short_change < 0:
            # 融券回補 → 空方退場，看漲
            score += 30
            signals.append(f"融券回補({short_change:+,}張，空方退場)")
        elif short_change > 0 and short_balance > 3000:
            # 融券大增（空方佈局）
            score += 5
            signals.append(f"融券增加({short_change:+,}張)")
        elif short_balance < 500:
            # 融券極低（幾乎沒人放空）→ 偏多
            score += 20
            signals.append(f"融券極低(空方稀少，餘額{short_balance:,}張)")
        else:
            score += 15
            signals.append(f"融券持平(餘額{short_balance:,}張)")

        # ── 最佳組合：融資↓ + 融券↓（主力完全控盤，佔 20分）──
        if margin_change < 0 and short_change < 0:
            score += 20
            signals.append("融資融券雙降(主力控盤最強訊號)")

        return AgentResult(
            agent_name=self.name,
            score=min(score, 100),
            signals=signals,
            weight=self.weight,
            raw={
                "margin_balance": margin_balance,
                "margin_change":  margin_change,
                "short_balance":  short_balance,
                "short_change":   short_change,
            },
        )

    def _empty_result(self, ticker: str) -> AgentResult:
        return AgentResult(
            agent_name=self.name,
            score=50.0,
            signals=["融資融券資料未取得（中性）"],
            weight=self.weight,
        )
