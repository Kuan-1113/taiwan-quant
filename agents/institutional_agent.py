"""
InstitutionalAgent — 三大法人籌碼分析
外資 / 投信 / 自營商 買賣超，是台股最強領先指標
"""

import pandas as pd
from .base_agent import BaseAgent, AgentResult


class InstitutionalAgent(BaseAgent):
    name   = "InstitutionalAgent"
    weight = 1.0

    def analyze(self, ticker: str, chips: dict) -> AgentResult:
        """
        chips: {foreign_net, trust_net, dealer_net, total_net}
        單位：張
        """
        if not chips:
            return self._empty_result(ticker)

        foreign_net = chips.get("foreign_net", 0)
        trust_net   = chips.get("trust_net",   0)
        dealer_net  = chips.get("dealer_net",  0)
        total_net   = chips.get("total_net",   0)

        score   = 0.0
        signals = []

        # ── 外資（最重要，佔 50分）──
        if foreign_net >= 5000:
            score += 50
            signals.append(f"外資大買({foreign_net:+,}張)")
        elif foreign_net >= 1000:
            score += 35
            signals.append(f"外資買超({foreign_net:+,}張)")
        elif foreign_net >= 200:
            score += 20
            signals.append(f"外資小買({foreign_net:+,}張)")
        elif foreign_net <= -1000:
            score += 0
            signals.append(f"外資賣超({foreign_net:+,}張)")
        elif foreign_net <= -200:
            score += 5
            signals.append(f"外資小賣({foreign_net:+,}張)")
        else:
            score += 12
            signals.append(f"外資持平({foreign_net:+,}張)")

        # ── 投信（台股作帳行情指標，佔 30分）──
        if trust_net >= 500:
            score += 30
            signals.append(f"投信大買({trust_net:+,}張)")
        elif trust_net >= 100:
            score += 20
            signals.append(f"投信買超({trust_net:+,}張)")
        elif trust_net >= 10:
            score += 10
            signals.append(f"投信小買({trust_net:+,}張)")
        elif trust_net <= -100:
            signals.append(f"投信賣超({trust_net:+,}張)")
        else:
            score += 5
            signals.append(f"投信持平({trust_net:+,}張)")

        # ── 外資 + 投信 同向買超（共振加分，佔 20分）──
        if foreign_net > 0 and trust_net > 0:
            score += 20
            signals.append("外資投信同買(雙法人共振)")
        elif foreign_net > 0 and dealer_net > 0:
            score += 10
            signals.append("外資自營同買")

        return AgentResult(
            agent_name=self.name,
            score=min(score, 100),
            signals=signals,
            weight=self.weight,
            raw={
                "foreign_net": foreign_net,
                "trust_net":   trust_net,
                "dealer_net":  dealer_net,
                "total_net":   total_net,
            },
        )

    def _empty_result(self, ticker: str) -> AgentResult:
        return AgentResult(
            agent_name=self.name,
            score=50.0,      # 無籌碼資料時給中性分，不影響評分
            signals=["籌碼資料未取得（中性）"],
            weight=self.weight,
        )
