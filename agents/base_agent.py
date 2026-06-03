"""所有 Agent 的基底類別"""

from dataclasses import dataclass, field
import pandas as pd


@dataclass
class AgentResult:
    """單一 Agent 的評分結果"""
    agent_name: str
    score: float          # 0~100
    signals: list[str]    # 觸發的信號說明（例如 ["MACD金叉", "RSI動能強"]）
    weight: float = 1.0   # 在 VotingAgent 中的權重
    raw: dict = field(default_factory=dict)  # 原始數值（debug用）

    def __repr__(self):
        return f"[{self.agent_name}] score={self.score:.1f} signals={self.signals}"


class BaseAgent:
    """
    子類別需實作：
        analyze(ticker: str, df: pd.DataFrame) -> AgentResult
    """
    name: str = "BaseAgent"
    weight: float = 1.0

    def analyze(self, ticker: str, df: pd.DataFrame) -> AgentResult:
        raise NotImplementedError

    def _empty_result(self, ticker: str) -> AgentResult:
        return AgentResult(
            agent_name=self.name,
            score=0.0,
            signals=["資料不足"],
            weight=self.weight,
        )
