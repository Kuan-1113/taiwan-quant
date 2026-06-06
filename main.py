"""
台股趨勢信號系統 — 主程式（全 9 Agent）
每日 17:00 掃描全市場，整合技術/籌碼/基本/消息四維度

執行：
  python main.py        # 啟動排程
  python main.py --now  # 立即執行（測試）
"""

import argparse
import numpy as np
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
load_dotenv(override=True)

from apscheduler.schedulers.blocking import BlockingScheduler

from config import (
    SCAN_MARKET, MAX_WORKERS, MIN_AVG_VOLUME,
    SCHEDULE_TIME, TIMEZONE,
)
from data.price_data        import get_all_tickers, fetch_market_data, filter_by_liquidity
from data.sector_map        import get_sector
from data.chips_data        import fetch_latest_chips
from data.fundamental_data  import fetch_fundamentals
from data.announcement_data import fetch_announcements
from agents import (
    TrendAgent, MomentumAgent, VolatilityAgent,
    InstitutionalAgent, MarginAgent,
    FundamentalAgent, AnnouncementAgent, SentimentAgent,
    batch_sentiment_analysis, aggregate, VoteResult,
)
from discord.publisher      import send_signals
from agents.summary_agent   import generate_summary, analyze_three_star_stocks
from signal_tracker         import save_signals, backfill_results
from auto_push_notebooklm   import run as push_notebooklm


# ── Agent 單例 ──
_trend         = TrendAgent()
_momentum      = MomentumAgent()
_volatility    = VolatilityAgent()
_institutional = InstitutionalAgent()
_margin        = MarginAgent()
_fundamental   = FundamentalAgent()
_announcement  = AnnouncementAgent()
_sentiment     = SentimentAgent()


def analyze_one(
    ticker:        str,
    df:            pd.DataFrame,
    inst_chips:    dict,
    margin_chips:  dict,
    fundamentals:  dict,
    announcements: dict,
    sentiments:    dict,
) -> VoteResult | None:
    try:
        code          = ticker.replace(".TW", "").replace(".TWO", "")
        inst_data     = inst_chips.get(code, {})
        margin_data   = margin_chips.get(code, {})
        fund_data     = fundamentals.get(ticker, {})
        ann_titles    = announcements.get(code, [])
        sent_score    = sentiments.get(ticker)

        results = [
            _trend.analyze(ticker, df),
            _momentum.analyze(ticker, df),
            _volatility.analyze(ticker, df),
            _institutional.analyze(ticker, inst_data),
            _margin.analyze(ticker, margin_data),
            _fundamental.analyze(ticker, fund_data),
            _announcement.analyze(ticker, ann_titles),
            _sentiment.analyze(ticker, sent_score),
        ]
        return aggregate(ticker, results, float(df["close"].iloc[-1]))
    except Exception:
        return None


def calc_market_adx(market_data: dict[str, pd.DataFrame]) -> float:
    from agents.trend_agent import _calc_adx
    for key in ["0050.TW", "0050.TWO"]:
        if key in market_data:
            return _calc_adx(market_data[key])
    adxs = []
    for _, df in list(market_data.items())[:20]:
        try:
            adxs.append(_calc_adx(df))
        except Exception:
            pass
    return round(float(np.mean(adxs)), 1) if adxs else 0.0


def calc_sector_ranking(results: list[VoteResult]) -> list[tuple[str, float]]:
    sector_scores: dict[str, list[float]] = {}
    for v in results:
        s = get_sector(v.ticker)
        if s != "其他":
            sector_scores.setdefault(s, []).append(v.final_score)
    ranking = [
        (s, round(float(np.mean(sc)), 1))
        for s, sc in sector_scores.items() if len(sc) >= 2
    ]
    return sorted(ranking, key=lambda x: -x[1])


def run_scan():
    tz  = ZoneInfo(TIMEZONE)
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M")
    print(f"\n{'='*50}")
    print(f"[START] 開始掃描 [{now}]（全 9 Agent）")
    print(f"{'='*50}")

    # 1. 股票清單
    tickers = get_all_tickers(SCAN_MARKET)
    if not tickers:
        print("[ERROR] 無法取得股票清單，終止")
        return

    # 2. 下載行情
    market_data = fetch_market_data(tickers, period="3mo", max_workers=MAX_WORKERS)

    # 3. 流動性過濾
    market_data = filter_by_liquidity(market_data, min_avg_volume=MIN_AVG_VOLUME)
    filtered_tickers = list(market_data.keys())

    # 4. 籌碼資料
    print("[CHIPS] 抓取籌碼資料...")
    inst_chips, margin_chips = fetch_latest_chips()
    print(f"[CHIPS] 三大法人 {len(inst_chips)} 支，融資融券 {len(margin_chips)} 支")

    # 5. 基本面（只抓過濾後的股票，限速避免過多請求）
    print("[FUND] 抓取基本面資料（限速）...")
    fundamentals = fetch_fundamentals(filtered_tickers, max_workers=5)

    # 6. 重大公告
    print("[ANN] 抓取重大公告...")
    announcements = fetch_announcements()

    # 7. 大盤 ADX
    market_adx = calc_market_adx(market_data)
    print(f"[ADX] 大盤 ADX ~= {market_adx}")

    # 8. 初步技術面掃描（找出候選股，再跑 Sentiment）
    print(f"[SCAN] 第一輪技術面快篩 {len(market_data)} 支...")
    first_pass: list[VoteResult] = []
    for ticker, df in market_data.items():
        try:
            r = aggregate(ticker, [
                _trend.analyze(ticker, df),
                _momentum.analyze(ticker, df),
                _volatility.analyze(ticker, df),
            ], float(df["close"].iloc[-1]))
            if r and r.stars >= 1:
                first_pass.append(r)
        except Exception:
            pass
    print(f"[SCAN] 快篩候選：{len(first_pass)} 支 → 進行 SentimentAgent 批次分析")

    # 9. SentimentAgent 批次（只針對候選股）
    sector_ranking_tmp = calc_sector_ranking(first_pass)
    candidate_tickers  = [v.ticker for v in first_pass]
    sentiments = batch_sentiment_analysis(candidate_tickers, sector_ranking_tmp, market_adx)
    print(f"[SENTIMENT] 完成 {len(sentiments)} 支情緒分析")

    # 10. 全 Agent 完整分析
    print(f"[SCAN] 完整 9 Agent 分析...")
    all_results: list[VoteResult] = []
    for i, (ticker, df) in enumerate(market_data.items()):
        v = analyze_one(ticker, df, inst_chips, margin_chips,
                        fundamentals, announcements, sentiments)
        if v:
            all_results.append(v)
        if (i + 1) % 200 == 0:
            print(f"   進度 {i+1}/{len(market_data)}，信號 {len(all_results)} 個")

    print(f"[OK] 分析完成：{len(all_results)} 個信號")
    print(f"   籌碼:{sum(1 for v in all_results if v.has_chips)} 基本面:{sum(1 for v in all_results if v.has_fund)} 消息:{sum(1 for v in all_results if v.has_news)}")

    # 11. 分級
    three_star = sorted([v for v in all_results if v.stars == 3], key=lambda x: -x.final_score)
    two_star   = sorted([v for v in all_results if v.stars == 2], key=lambda x: -x.final_score)
    one_star   = sorted([v for v in all_results if v.stars == 1], key=lambda x: -x.final_score)
    print(f"[***] {len(three_star)} 檔 | [**] {len(two_star)} 檔 | [*] {len(one_star)} 檔")

    # 12. 族群排行
    sector_ranking = calc_sector_ranking(all_results)

    # 13. 三星個股深度分析（含公司資訊 + 新聞）
    print(f"[AI] 三星個股深度分析（{len(three_star)} 支，含新聞抓取）...")
    three_star_analyses = analyze_three_star_stocks(three_star, market_adx, fundamentals)

    # 14. AI 市場總結
    print("[AI] 產生市場深度總結...")
    ai_summary = generate_summary(three_star, two_star, market_adx, sector_ranking)

    # 15. 發送 Discord
    send_signals(
        three_star=three_star,
        two_star=two_star,
        one_star=one_star,
        adx_market=market_adx,
        sector_ranking=sector_ranking,
        ai_summary=ai_summary,
        three_star_analyses=three_star_analyses,
    )

    # 16. 儲存信號到資料庫（依 TRACKER_MIN_STARS 設定，預設全星級）
    print("[TRACKER] 儲存信號記錄...")
    scan_date = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")
    save_signals(three_star + two_star + one_star, scan_date=scan_date)

    # 17. 回補 5/10 天前的信號結果
    print("[TRACKER] 回補歷史信號結果...")
    backfill_results()

    # 18. 每月 1 號自動推送月報到 NotebookLM（失敗不影響主流程）
    if datetime.now(ZoneInfo(TIMEZONE)).day == 1:
        print("[LM] 每月月報推送...")
        try:
            import asyncio
            asyncio.run(push_notebooklm())
        except Exception as e:
            print(f"[LM] 月報推送失敗（不影響主流程）：{e}")

    print(f"[DONE] 完成 [{datetime.now(ZoneInfo(TIMEZONE)).strftime('%H:%M:%S')}]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--now", action="store_true", help="立即執行一次")
    args = parser.parse_args()

    if args.now:
        run_scan()
    else:
        h, m = SCHEDULE_TIME.split(":")
        print(f"[SCHED] 排程啟動，每日 {SCHEDULE_TIME}（{TIMEZONE}）")
        print("   使用 --now 可立即測試")
        scheduler = BlockingScheduler(timezone=TIMEZONE)
        scheduler.add_job(run_scan, "cron", hour=int(h), minute=int(m), id="daily_scan")
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            print("[STOP] 排程已停止")
