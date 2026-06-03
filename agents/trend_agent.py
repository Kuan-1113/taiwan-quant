"""
TrendAgent — 趨勢判斷
指標：ADX、EMA多頭排列（EMA5 > EMA20 > EMA60）、大盤相對強弱
"""

import pandas as pd
import numpy as np
from .base_agent import BaseAgent, AgentResult
from config import ADX_TREND_THRESHOLD


def _calc_ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _calc_adx(df: pd.DataFrame, period: int = 14) -> float:
    """計算 ADX"""
    high  = df["high"]
    low   = df["low"]
    close = df["close"]

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)

    plus_dm  = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)
    # 當 +DM < -DM 時歸零，反之亦然
    plus_dm  = plus_dm.where(plus_dm > minus_dm, 0)
    minus_dm = minus_dm.where(minus_dm > plus_dm, 0)

    atr      = tr.ewm(span=period, adjust=False).mean()
    plus_di  = 100 * plus_dm.ewm(span=period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(span=period, adjust=False).mean() / atr

    dx  = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)).fillna(0)
    adx = dx.ewm(span=period, adjust=False).mean()
    return round(float(adx.iloc[-1]), 1)


class TrendAgent(BaseAgent):
    name   = "TrendAgent"
    weight = 1.0   # 在技術面總分中的比重（與 Momentum/Volatility 平均後再乘 0.30）

    def analyze(self, ticker: str, df: pd.DataFrame) -> AgentResult:
        if len(df) < 60:
            return self._empty_result(ticker)

        close = df["close"]

        # ── 均線 ──
        ema5  = _calc_ema(close, 5)
        ema10 = _calc_ema(close, 10)
        ema20 = _calc_ema(close, 20)

        e5  = float(ema5.iloc[-1])
        e10 = float(ema10.iloc[-1])
        e20 = float(ema20.iloc[-1])

        # ── ADX ──
        adx = _calc_adx(df)

        # ── 評分邏輯 ──
        score   = 0.0
        signals = []

        # 1. 多頭排列（EMA5 > EMA10 > EMA20）→ 滿分 40
        if e5 > e10 > e20:
            score += 40
            signals.append("EMA多頭排列(5>10>20)")
        elif e5 > e10:
            score += 25
            signals.append("EMA短線偏多(5>10)")
        elif e5 > e20:
            score += 15
            signals.append("EMA5站上EMA20")

        # 2. 股價站上 EMA10 → 20分（改用更靈敏的 EMA10）
        current_price = float(close.iloc[-1])
        if current_price > e10:
            score += 20
            signals.append("站上EMA20")

        # 3. ADX 趨勢強度 → 最高 40
        if adx >= 40:
            score += 40
            signals.append(f"ADX強趨勢({adx})")
        elif adx >= ADX_TREND_THRESHOLD:   # 預設25
            score += 25
            signals.append(f"ADX趨勢確認({adx})")
        elif adx >= 18:
            score += 10
            signals.append(f"ADX趨勢偏弱({adx})")
        else:
            signals.append(f"ADX盤整({adx}，<{ADX_TREND_THRESHOLD})")

        return AgentResult(
            agent_name=self.name,
            score=min(score, 100),
            signals=signals,
            weight=self.weight,
            raw={"ema5": round(e5,2), "ema10": round(e10,2), "ema20": round(e20,2), "adx": adx},
        )
