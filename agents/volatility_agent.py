"""
VolatilityAgent — 波動/突破判斷
指標：布林通道位置、ATR突破、量能放大
"""

import pandas as pd
import numpy as np
from .base_agent import BaseAgent, AgentResult
from config import VOLUME_MULT


def _calc_bollinger(close: pd.Series, period: int = 20) -> dict:
    ma    = close.rolling(period).mean()
    std   = close.rolling(period).std()
    upper = ma + 2 * std
    lower = ma - 2 * std
    price = float(close.iloc[-1])
    mid   = float(ma.iloc[-1])
    up    = float(upper.iloc[-1])
    lo    = float(lower.iloc[-1])
    bw    = (up - lo) / mid if mid > 0 else 0

    # 位置 0~1（0=下軌, 1=上軌）
    position = (price - lo) / (up - lo) if (up - lo) > 0 else 0.5

    return {
        "upper":    round(up, 2),
        "middle":   round(mid, 2),
        "lower":    round(lo, 2),
        "bandwidth": round(bw, 3),
        "position": round(position, 3),
    }


def _calc_atr(df: pd.DataFrame, period: int = 14) -> float:
    high  = df["high"]
    low   = df["low"]
    close = df["close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return round(float(tr.rolling(period).mean().iloc[-1]), 2)


def _volume_signal(df: pd.DataFrame, mult: float = 1.5) -> dict:
    vol    = df["volume"]
    ma20   = vol.rolling(20).mean()
    ratio  = float(vol.iloc[-1]) / float(ma20.iloc[-1]) if float(ma20.iloc[-1]) > 0 else 1.0
    # 量能是否持續放大（連續2日）
    consec = bool(vol.iloc[-1] > ma20.iloc[-1] * mult and vol.iloc[-2] > ma20.iloc[-2])
    return {"ratio": round(ratio, 2), "consecutive": consec}


class VolatilityAgent(BaseAgent):
    name   = "VolatilityAgent"
    weight = 1.0

    def analyze(self, ticker: str, df: pd.DataFrame) -> AgentResult:
        if len(df) < 25:
            return self._empty_result(ticker)

        close   = df["close"]
        boll    = _calc_bollinger(close)
        atr     = _calc_atr(df)
        vol_sig = _volume_signal(df, VOLUME_MULT)

        score   = 0.0
        signals = []

        # ── 布林通道（最高 40分）──
        pos = boll["position"]
        if pos > 0.8:
            # 接近或突破上軌，強勢但注意過熱
            score += 30
            signals.append(f"突破布林上軌({pos:.0%})")
        elif 0.55 <= pos <= 0.8:
            score += 40
            signals.append(f"布林中軌以上強勢區({pos:.0%})")
        elif 0.4 <= pos < 0.55:
            score += 20
            signals.append(f"布林中軌附近({pos:.0%})")
        elif pos < 0.2:
            # 靠近下軌，可能超賣反彈
            score += 15
            signals.append(f"布林下軌反彈機會({pos:.0%})")
        else:
            score += 5
            signals.append(f"布林下半區({pos:.0%})")

        # 布林通道收窄後放量突破（爆發信號）
        if boll["bandwidth"] < 0.08 and vol_sig["ratio"] > VOLUME_MULT:
            score += 10
            signals.append("布林收窄放量突破")

        # ── 量能（最高 40分）──
        if vol_sig["consecutive"]:
            score += 40
            signals.append(f"連續放量({vol_sig['ratio']:.1f}倍)")
        elif vol_sig["ratio"] >= VOLUME_MULT:
            score += 25
            signals.append(f"單日放量({vol_sig['ratio']:.1f}倍)")
        elif vol_sig["ratio"] >= 1.2:
            score += 10
            signals.append(f"量能偏大({vol_sig['ratio']:.1f}倍)")
        else:
            signals.append(f"量能普通({vol_sig['ratio']:.1f}倍)")

        # ── ATR（趨勢波動參考，不直接加分，但記錄）──
        signals.append(f"ATR={atr}")

        return AgentResult(
            agent_name=self.name,
            score=min(score, 100),
            signals=signals,
            weight=self.weight,
            raw={"bollinger": boll, "atr": atr, "volume": vol_sig},
        )
