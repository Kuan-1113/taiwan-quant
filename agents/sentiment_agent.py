"""
SentimentAgent — 市場情緒（批次 Claude 分析）
針對三星/雙星候選股，用 Claude 快速判斷近期新聞情緒
"""

import os
import anthropic
from dotenv import load_dotenv
load_dotenv(override=True)

from .base_agent import BaseAgent, AgentResult
from data.price_data import get_name


def batch_sentiment_analysis(
    candidates: list[str],   # ticker list
    sector_ranking: list[tuple[str, float]],
    adx: float,
) -> dict[str, float]:
    """
    用 Claude 批次評估候選股的市場情緒分數
    回傳 {ticker: sentiment_score (0~100)}
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or not candidates:
        return {}

    client = anthropic.Anthropic(api_key=api_key)

    # 組候選股資料給 Claude
    stock_list = []
    for t in candidates[:30]:   # 最多 30 支
        code = t.replace(".TW", "").replace(".TWO", "")
        name = get_name(t)
        stock_list.append(f"{code} {name}")

    sector_str = "、".join([f"{s}({sc:.0f}分)" for s, sc in sector_ranking[:4]])

    prompt = f"""你是台股資深分析師，根據目前市場情境評估以下股票的市場情緒分數。

【市場背景】
- 大盤 ADX：{adx:.0f}（{"強趨勢" if adx >= 25 else "盤整"}）
- 領漲族群：{sector_str}

【待評估股票】
{chr(10).join(stock_list)}

請根據你對這些股票的認知（產業地位、近期題材、市場關注度），
為每支股票給出情緒分數 0~100（0=極度悲觀，50=中性，100=極度樂觀）。

只輸出 JSON 格式，格式如下（用代碼當 key）：
{{"2330": 75, "2454": 60, ...}}

不要有任何說明文字，只輸出 JSON。"""

    try:
        msg = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        # 清理可能的 markdown
        raw = raw.replace("```json", "").replace("```", "").strip()
        import json
        scores = json.loads(raw)
        # 轉回 ticker 格式
        result = {}
        for t in candidates:
            code = t.replace(".TW", "").replace(".TWO", "")
            if code in scores:
                result[t] = float(scores[code])
        return result
    except Exception as e:
        print(f"[WARN] SentimentAgent 失敗：{e}")
        return {}


class SentimentAgent(BaseAgent):
    name   = "SentimentAgent"
    weight = 1.0

    def analyze(self, ticker: str, sentiment_score: float | None) -> AgentResult:
        """sentiment_score: 由 batch_sentiment_analysis 預先算好"""
        if sentiment_score is None:
            return AgentResult(
                agent_name=self.name,
                score=50.0,
                signals=["情緒資料未取得（中性）"],
                weight=self.weight,
            )

        score = float(sentiment_score)
        if score >= 75:
            signals = [f"市場情緒正向({score:.0f}分)"]
        elif score >= 55:
            signals = [f"市場情緒偏多({score:.0f}分)"]
        elif score >= 45:
            signals = [f"市場情緒中性({score:.0f}分)"]
        else:
            signals = [f"市場情緒偏空({score:.0f}分)"]

        return AgentResult(
            agent_name=self.name,
            score=score,
            signals=signals,
            weight=self.weight,
            raw={"sentiment": score},
        )
