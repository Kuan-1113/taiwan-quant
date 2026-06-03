"""
FundamentalAgent — 基本面評分
PE / EPS / ROE / 毛利率 / 52週高低位置
"""

from .base_agent import BaseAgent, AgentResult


class FundamentalAgent(BaseAgent):
    name   = "FundamentalAgent"
    weight = 1.0

    def analyze(self, ticker: str, info: dict) -> AgentResult:
        if not info or not any(info.values()):
            return self._empty_result(ticker)

        score   = 0.0
        signals = []

        pe      = info.get("pe")
        eps     = info.get("eps")
        roe     = info.get("roe")        # 0~1
        margin  = info.get("profit_margin")  # 0~1
        growth  = info.get("revenue_growth") # 0~1
        w52_hi  = info.get("52w_high")
        w52_lo  = info.get("52w_low")

        # ── PE 本益比（佔 30分）──
        if pe and pe > 0:
            if pe < 12:
                score += 30
                signals.append(f"PE低估({pe:.1f})")
            elif pe < 20:
                score += 22
                signals.append(f"PE合理({pe:.1f})")
            elif pe < 30:
                score += 12
                signals.append(f"PE偏高({pe:.1f})")
            elif pe < 50:
                score += 5
                signals.append(f"PE高估({pe:.1f})")
            else:
                signals.append(f"PE極高({pe:.1f})")
        else:
            score += 15   # 無 PE 資料給中性
            signals.append("PE無資料(中性)")

        # ── EPS 盈利（佔 20分）──
        if eps is not None:
            if eps > 5:
                score += 20
                signals.append(f"EPS強({eps:.2f})")
            elif eps > 2:
                score += 14
                signals.append(f"EPS正({eps:.2f})")
            elif eps > 0:
                score += 8
                signals.append(f"EPS微正({eps:.2f})")
            else:
                score += 0
                signals.append(f"EPS虧損({eps:.2f})")

        # ── ROE 股東權益報酬率（佔 25分）──
        if roe is not None:
            roe_pct = roe * 100
            if roe_pct >= 20:
                score += 25
                signals.append(f"ROE優異({roe_pct:.1f}%)")
            elif roe_pct >= 12:
                score += 18
                signals.append(f"ROE良好({roe_pct:.1f}%)")
            elif roe_pct >= 5:
                score += 10
                signals.append(f"ROE普通({roe_pct:.1f}%)")
            else:
                signals.append(f"ROE差({roe_pct:.1f}%)")

        # ── 營收成長（佔 15分）──
        if growth is not None:
            if growth > 0.20:
                score += 15
                signals.append(f"營收高成長({growth*100:.0f}%)")
            elif growth > 0.05:
                score += 10
                signals.append(f"營收成長({growth*100:.0f}%)")
            elif growth > 0:
                score += 5
                signals.append(f"營收微增({growth*100:.0f}%)")
            else:
                signals.append(f"營收衰退({growth*100:.0f}%)")

        # ── 52週位置（佔 10分）──
        if w52_hi and w52_lo and w52_hi > w52_lo:
            # 用已有的 close price 估算（從 info 沒有，用 52w 高低判斷趨勢健康度）
            range_ratio = (w52_hi - w52_lo) / w52_lo if w52_lo > 0 else 0
            if range_ratio > 0.3:
                score += 10
                signals.append(f"52週波動大({range_ratio*100:.0f}%，趨勢股特徵)")
            else:
                score += 5

        return AgentResult(
            agent_name=self.name,
            score=min(score, 100),
            signals=signals,
            weight=self.weight,
            raw={"pe": pe, "eps": eps, "roe": roe, "growth": growth},
        )

    def _empty_result(self, ticker: str) -> AgentResult:
        return AgentResult(
            agent_name=self.name,
            score=50.0,
            signals=["基本面資料未取得（中性）"],
            weight=self.weight,
        )
