"""
AnnouncementAgent — 重大公告過濾
有利多公告加分，有利空公告扣分
"""

from .base_agent import BaseAgent, AgentResult
from data.announcement_data import classify_announcement


class AnnouncementAgent(BaseAgent):
    name   = "AnnouncementAgent"
    weight = 1.0

    def analyze(self, ticker: str, titles: list[str]) -> AgentResult:
        """titles: 今日該股的重大公告標題清單"""
        if not titles:
            # 無公告 → 中性，不加不扣
            return AgentResult(
                agent_name=self.name,
                score=50.0,
                signals=["無重大公告（中性）"],
                weight=self.weight,
            )

        delta, signals = classify_announcement(titles)
        score = max(0.0, min(100.0, 50.0 + delta * 2.5))

        return AgentResult(
            agent_name=self.name,
            score=score,
            signals=signals,
            weight=self.weight,
            raw={"titles": titles, "delta": delta},
        )
