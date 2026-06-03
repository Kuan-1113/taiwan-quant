"""
Discord Publisher — 完整版（三星個股分析 + 族群細分 + AI 深度總結）
"""

import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from agents.voting_agent import VoteResult
from data.price_data import get_name
from data.sector_map import get_sector, get_sector_emoji, SECTOR_GROUP
from config import DISCORD_WEBHOOK_SIGNAL, TIMEZONE


def _now_str() -> str:
    return datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M")


def _signal_line(v: VoteResult, indent: str = "") -> str:
    code    = v.ticker.replace(".TW", "").replace(".TWO", "")
    name    = get_name(v.ticker)
    price   = f"＄{v.current_price:.0f}" if v.current_price > 0 else ""
    sigs    = " ＋ ".join(v.top_signals[:3])
    adx_str = f"ADX{v.adx:.0f}" if v.adx > 0 else ""
    chips_badge = ""
    if v.has_chips:
        inst = v.agent_scores.get("InstitutionalAgent", 50)
        if inst >= 75:
            chips_badge = " 🏦"
        elif inst <= 30:
            chips_badge = " 🔴"
    return f"{indent}• **{code} {name}**{chips_badge} {price}　`{v.final_score:.0f}分`　{sigs}"


def send_signals(
    three_star:      list[VoteResult],
    two_star:        list[VoteResult],
    one_star:        list[VoteResult],
    adx_market:      float = 0.0,
    sector_ranking:  list[tuple[str, float]] | None = None,
    ai_summary:      str = "",
    three_star_analyses: list[dict] | None = None,
):
    if not DISCORD_WEBHOOK_SIGNAL:
        print("[WARN] 未設定 DISCORD_WEBHOOK_SIGNAL，跳過發送")
        return

    mkt_state = "強趨勢" if adx_market >= 35 else ("趨勢市" if adx_market >= 25 else "盤整市")
    mkt_emoji = "🚀" if adx_market >= 35 else ("📈" if adx_market >= 25 else "↔️")
    total     = len(three_star) + len(two_star) + len(one_star)
    now       = _now_str()
    messages  = []

    # ════════════════════════════════
    # 訊息 1：標題總覽
    # ════════════════════════════════
    m1 = [
        f"# 📊 今日策略明牌　{now}",
        f"> {mkt_emoji} 大盤 **{mkt_state}**（ADX `{adx_market:.0f}`）　|　全市場掃描 **{total} 個信號**",
        f"> ⭐⭐⭐ **{len(three_star)}** 檔　⭐⭐ **{len(two_star)}** 檔　⭐ **{len(one_star)}** 檔",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "## 🏆 ⭐⭐⭐ 頂級信號",
        "> 技術 ＋ 籌碼 ＋ 基本面全面共振，中短期趨勢延續機率最大",
        "",
    ]
    if three_star:
        for v in three_star[:12]:
            m1.append(_signal_line(v))
    else:
        m1.append("今日無三星標的，標準嚴格，品質優先。")
    messages.append("\n".join(m1))

    # ════════════════════════════════
    # 訊息 2：三星個股深度分析
    # ════════════════════════════════
    if three_star_analyses:
        m2 = [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "## 🔍 三星個股深度分析",
            "",
        ]
        for item in three_star_analyses:
            # 標題列
            m2.append(f"### {item['emoji']} {item['code']} {item['name']}　`{item['sector']}`")
            m2.append(f"> ＄{item['price']:.0f}　評分 `{item['score']:.0f}/100`　ADX `{item['adx']:.0f}`")

            # 公司定位
            if item.get("company"):
                m2.append(f"> 📍 {item['company']}")

            # 近期新聞
            if item.get("news"):
                m2.append("> **📰 近期新聞**")
                for n in item["news"][:3]:
                    m2.append(f"> • {n['title']}（{n['publisher']}）")

            m2.append("")
            m2.append(item["analysis"])
            m2.append("")
            m2.append("─────────────────────")
            m2.append("")
        messages.append("\n".join(m2))

    # ════════════════════════════════
    # 訊息 3：雙星（依細分族群分組）
    # ════════════════════════════════
    m3 = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "## ⭐⭐ 多重信號精選",
        "> 同時觸發多個技術＋籌碼指標，中短期動能延續機率高",
        "",
    ]
    # 按細分族群分組
    sector_groups: dict[str, list[VoteResult]] = {}
    for v in two_star:
        s = get_sector(v.ticker)
        sector_groups.setdefault(s, []).append(v)

    # 先排 AI 和低軌衛星，再排其他
    priority = ["AI", "低軌衛星", "半導體"]
    def sort_key(item):
        s, _ = item
        g = SECTOR_GROUP.get(s, "其他")
        idx = priority.index(g) if g in priority else len(priority)
        return (idx, -len(_))

    for sector, items in sorted(sector_groups.items(), key=sort_key):
        emoji = get_sector_emoji(sector)
        m3.append(f"**{emoji} {sector}**（{len(items)} 檔）")
        for v in items[:4]:
            m3.append(_signal_line(v, "  "))
        m3.append("")
    messages.append("\n".join(m3))

    # ════════════════════════════════
    # 訊息 4：單星 + 族群強弱
    # ════════════════════════════════
    m4 = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "## ⭐ 觀察名單",
        "> 單一信號，待第二確認再進場",
        "",
    ]
    for v in one_star[:8]:
        m4.append(_signal_line(v))
    m4.append("")

    if sector_ranking:
        m4.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        m4.append("## 📊 族群強弱排行（細分）")
        m4.append("")
        # 主族群聚合顯示
        group_scores: dict[str, list[float]] = {}
        group_sectors: dict[str, list[str]]  = {}
        for sector, score in sector_ranking:
            group = SECTOR_GROUP.get(sector, sector)
            group_scores.setdefault(group, []).append(score)
            group_sectors.setdefault(group, []).append(f"{sector}({score:.0f})")
        group_avg = sorted(
            [(g, sum(s)/len(s)) for g, s in group_scores.items()],
            key=lambda x: -x[1]
        )
        for rank, (group, avg) in enumerate(group_avg[:8], 1):
            bar    = "🔥" if avg >= 70 else ("📈" if avg >= 60 else "➡️")
            detail = "、".join(group_sectors[group][:3])
            m4.append(f"`{rank}.` {bar} **{group}** `{avg:.0f}分`")
            m4.append(f"     └ {detail}")
    messages.append("\n".join(m4))

    # ════════════════════════════════
    # 訊息 5：AI 深度總結
    # ════════════════════════════════
    if ai_summary:
        m5 = [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "## 🤖 AI 深度市場分析",
            "",
            ai_summary,
        ]
        messages.append("\n".join(m5))

    # 逐一發送
    for msg in messages:
        _send(msg)
    print(f"[OK] Discord 發送完成（{len(messages)} 則，共 {total} 筆信號）")


def _send(text: str):
    if len(text) <= 1900:
        _post(text)
        return
    chunks = []
    while len(text) > 1900:
        cut = text.rfind("\n", 0, 1900)
        if cut == -1:
            cut = 1900
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    chunks.append(text)
    for c in chunks:
        _post(c)


def _post(text: str):
    resp = requests.post(
        DISCORD_WEBHOOK_SIGNAL,
        json={"content": text},
        timeout=10,
    )
    if resp.status_code not in (200, 204):
        print(f"[WARN] Discord 發送失敗：{resp.status_code} {resp.text[:100]}")
