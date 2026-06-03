"""
MomentumAgent — 動能判斷
指標：MACD（金叉/死叉/柱狀體方向）、RSI、KD
"""

import pandas as pd
from .base_agent import BaseAgent, AgentResult
from config import RSI_OVERSOLD, RSI_OVERBOUGHT


def _calc_macd(close: pd.Series, fast=12, slow=26, signal=9) -> dict:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    dif      = ema_fast - ema_slow
    dea      = dif.ewm(span=signal, adjust=False).mean()
    hist     = dif - dea
    return {
        "dif":          float(dif.iloc[-1]),
        "dea":          float(dea.iloc[-1]),
        "hist":         float(hist.iloc[-1]),
        "hist_prev":    float(hist.iloc[-2]),
        "golden_cross": bool(dif.iloc[-1] > dea.iloc[-1]),
    }


def _calc_rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, float("nan"))
    rsi   = 100 - 100 / (1 + rs)
    return round(float(rsi.iloc[-1]), 1)


def _calc_kd(df: pd.DataFrame, period: int = 9) -> dict:
    low_min  = df["low"].rolling(period).min()
    high_max = df["high"].rolling(period).max()
    rsv      = 100 * (df["close"] - low_min) / (high_max - low_min).replace(0, float("nan"))
    k        = rsv.ewm(com=2, adjust=False).mean()
    d        = k.ewm(com=2, adjust=False).mean()
    return {
        "k":            round(float(k.iloc[-1]), 1),
        "d":            round(float(d.iloc[-1]), 1),
        "golden_cross": bool(k.iloc[-1] > d.iloc[-1]),
        "oversold":     bool(k.iloc[-1] < 20 and d.iloc[-1] < 20),
    }


class MomentumAgent(BaseAgent):
    name   = "MomentumAgent"
    weight = 1.0

    def analyze(self, ticker: str, df: pd.DataFrame) -> AgentResult:
        if len(df) < 30:
            return self._empty_result(ticker)

        close = df["close"]
        macd  = _calc_macd(close)
        rsi   = _calc_rsi(close)
        kd    = _calc_kd(df)

        score   = 0.0
        signals = []

        # ── MACD（最高 40分）──
        if macd["golden_cross"]:
            score += 20
            signals.append("MACD金叉")
            # 柱狀體放大（動能加速）
            if macd["hist"] > 0 and macd["hist"] > macd["hist_prev"]:
                score += 20
                signals.append("MACD柱狀放大")
            elif macd["hist"] > 0:
                score += 10
                signals.append("MACD柱狀轉正")
        else:
            # 死叉但柱狀體縮小（可能轉折）
            if macd["hist"] < 0 and macd["hist"] > macd["hist_prev"]:
                score += 5
                signals.append("MACD底背離跡象")

        # ── RSI（最高 35分）──
        if 50 <= rsi <= RSI_OVERBOUGHT:
            score += 35
            signals.append(f"RSI動能強({rsi})")
        elif 45 <= rsi < 50:
            score += 20
            signals.append(f"RSI偏多({rsi})")
        elif RSI_OVERSOLD <= rsi < 45:
            score += 10
            signals.append(f"RSI弱勢({rsi})")
        elif rsi < RSI_OVERSOLD:
            score += 15
            signals.append(f"RSI超賣反彈機會({rsi})")
        else:  # > RSI_OVERBOUGHT
            score += 10
            signals.append(f"RSI過熱注意({rsi})")

        # ── KD（最高 25分）──
        if kd["golden_cross"] and not kd["oversold"]:
            score += 25
            signals.append(f"KD金叉(K={kd['k']})")
        elif kd["golden_cross"]:
            score += 20
            signals.append(f"KD低檔金叉(K={kd['k']})")
        elif kd["oversold"]:
            score += 10
            signals.append(f"KD超賣區({kd['k']}/{kd['d']})")

        return AgentResult(
            agent_name=self.name,
            score=min(score, 100),
            signals=signals,
            weight=self.weight,
            raw={"macd": macd, "rsi": rsi, "kd": kd},
        )
