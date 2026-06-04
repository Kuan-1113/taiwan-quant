"""
signal_tracker.py — 台股量化信號結果追蹤機制

功能：
  1. save_signals()     — 每日掃描完成後，將信號存入 SQLite
  2. backfill_results() — 自動回補 5/10 天前信號的漲跌結果
  3. export_report()    — 匯出分析報告（供 NotebookLM 使用）

資料庫：taiwan_signals.db（存放於專案根目錄）

執行方式（獨立測試）：
  python signal_tracker.py --init      # 初始化資料庫
  python signal_tracker.py --backfill  # 手動回補結果
  python signal_tracker.py --report    # 匯出報告
"""

import sqlite3
import argparse
import json
import csv
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import yfinance as yf

from config import (
    TIMEZONE,
    TRACKER_WIN_THRESHOLD,
    TRACKER_LOSS_THRESHOLD,
    TRACKER_MIN_STARS,
)

# ── 設定 ──
DB_PATH       = Path(__file__).parent / "taiwan_signals.db"
BACKFILL_DAYS = [5, 10]  # 追蹤 5天 和 10天後結果


# ════════════════════════════════════════════
# 工具函式
# ════════════════════════════════════════════

def _business_days_offset(start_date: str, n: int) -> str:
    """
    從 start_date 往前（n<0）或往後（n>0）算 abs(n) 個交易日。
    交易日 = 週一到週五（未排除台灣國定假日，足夠精確）
    """
    dt   = datetime.strptime(start_date, "%Y-%m-%d")
    step = 1 if n > 0 else -1
    left = abs(n)
    while left > 0:
        dt += timedelta(days=step)
        if dt.weekday() < 5:  # Mon~Fri
            left -= 1
    return dt.strftime("%Y-%m-%d")


def _get_close_price(ticker: str, date: str) -> float | None:
    """
    取得指定日期（或最近交易日）的收盤價。
    使用 yfinance 下載前後各 4 天的區間，取最接近目標日的收盤。
    """
    try:
        target_dt = datetime.strptime(date, "%Y-%m-%d")
        start     = (target_dt - timedelta(days=5)).strftime("%Y-%m-%d")
        end       = (target_dt + timedelta(days=4)).strftime("%Y-%m-%d")

        df = yf.download(ticker, start=start, end=end,
                         progress=False, auto_adjust=True)
        if df.empty:
            return None

        # 統一 index 為 naive datetime
        df.index = df.index.tz_localize(None) if df.index.tzinfo else df.index

        # 取最接近目標日的交易日收盤
        diffs = abs(df.index - target_dt)
        closest_idx = diffs.argmin()
        row = df.iloc[closest_idx]

        # 相容 MultiIndex（yfinance >= 0.2.x）與一般 Index
        close_val = row["Close"]
        if hasattr(close_val, "__len__"):   # Series / array
            close_val = float(close_val.iloc[0])
        else:
            close_val = float(close_val)

        return round(close_val, 2)
    except Exception as e:
        print(f"[TRACKER] 抓價格失敗 {ticker} {date}：{e}")
        return None


# ════════════════════════════════════════════
# 1. 資料庫初始化
# ════════════════════════════════════════════

def init_db():
    """建立資料表（若不存在）"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 信號表
    c.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            date                 TEXT NOT NULL,
            ticker               TEXT NOT NULL,
            stars                INTEGER NOT NULL,
            final_score          REAL NOT NULL,
            current_price        REAL NOT NULL,
            adx                  REAL DEFAULT 0,
            atr                  REAL DEFAULT 0,
            has_chips            INTEGER DEFAULT 0,
            has_fund             INTEGER DEFAULT 0,
            has_news             INTEGER DEFAULT 0,
            score_trend          REAL DEFAULT NULL,
            score_momentum       REAL DEFAULT NULL,
            score_volatility     REAL DEFAULT NULL,
            score_institutional  REAL DEFAULT NULL,
            score_margin         REAL DEFAULT NULL,
            score_fundamental    REAL DEFAULT NULL,
            score_announcement   REAL DEFAULT NULL,
            score_sentiment      REAL DEFAULT NULL,
            top_signals          TEXT DEFAULT NULL,
            created_at           TEXT DEFAULT (datetime('now')),
            UNIQUE(date, ticker)
        )
    """)

    # 結果表
    c.execute("""
        CREATE TABLE IF NOT EXISTS results (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id     INTEGER NOT NULL,
            days_passed   INTEGER NOT NULL,
            result_date   TEXT NOT NULL,
            entry_price   REAL NOT NULL,
            exit_price    REAL NOT NULL,
            pnl_percent   REAL NOT NULL,
            result_label  TEXT NOT NULL,
            created_at    TEXT DEFAULT (datetime('now')),
            UNIQUE(signal_id, days_passed),
            FOREIGN KEY(signal_id) REFERENCES signals(id)
        )
    """)

    conn.commit()
    conn.close()
    print(f"[DB] 資料庫就緒：{DB_PATH}")


# ════════════════════════════════════════════
# 2. 儲存當日信號
# ════════════════════════════════════════════

def save_signals(vote_results: list, scan_date: str = None) -> int:
    """
    將 VoteResult 列表存入資料庫。

    參數：
        vote_results — list[VoteResult]
        scan_date    — YYYY-MM-DD，預設今日（台北時間）

    回傳：成功儲存筆數
    """
    init_db()
    if not scan_date:
        scan_date = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")

    # 依設定過濾最低星級
    filtered = [v for v in vote_results if v.stars >= TRACKER_MIN_STARS]

    conn   = sqlite3.connect(DB_PATH)
    c      = conn.cursor()
    saved  = 0

    for v in filtered:
        try:
            agent_scores = getattr(v, "agent_scores", {})
            top_signals  = json.dumps(
                getattr(v, "top_signals", []), ensure_ascii=False
            )
            c.execute("""
                INSERT OR IGNORE INTO signals (
                    date, ticker, stars, final_score, current_price,
                    adx, atr, has_chips, has_fund, has_news,
                    score_trend, score_momentum, score_volatility,
                    score_institutional, score_margin,
                    score_fundamental, score_announcement, score_sentiment,
                    top_signals
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                scan_date, v.ticker, v.stars, v.final_score, v.current_price,
                getattr(v, "adx", 0.0), getattr(v, "atr", 0.0),
                int(getattr(v, "has_chips", False)),
                int(getattr(v, "has_fund",  False)),
                int(getattr(v, "has_news",  False)),
                agent_scores.get("TrendAgent"),
                agent_scores.get("MomentumAgent"),
                agent_scores.get("VolatilityAgent"),
                agent_scores.get("InstitutionalAgent"),
                agent_scores.get("MarginAgent"),
                agent_scores.get("FundamentalAgent"),
                agent_scores.get("AnnouncementAgent"),
                agent_scores.get("SentimentAgent"),
                top_signals,
            ))
            if conn.execute("SELECT changes()").fetchone()[0]:
                saved += 1
        except Exception as e:
            print(f"[TRACKER] 儲存 {v.ticker} 失敗：{e}")

    conn.commit()
    conn.close()
    print(f"[TRACKER] 儲存 {saved}/{len(filtered)} 筆信號（{scan_date}）")
    return saved


# ════════════════════════════════════════════
# 3. 自動回補結果
# ════════════════════════════════════════════

def backfill_results(target_days: list[int] = None) -> int:
    """
    回補 N 個交易日前的信號結果。

    邏輯：
      今日 17:05 執行 → 找出 5/10 個交易日前的信號
      → 抓今日收盤價 → 計算漲跌幅 → 寫入 results 表

    回傳：回補筆數
    """
    if target_days is None:
        target_days = BACKFILL_DAYS

    init_db()
    today  = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")
    conn   = sqlite3.connect(DB_PATH)
    c      = conn.cursor()
    filled = 0

    for days in target_days:
        # N 個交易日前的日期
        signal_date = _business_days_offset(today, -days)

        # 找出那天尚未回補的信號（依 TRACKER_MIN_STARS 設定）
        c.execute("""
            SELECT s.id, s.ticker, s.stars, s.current_price
            FROM signals s
            WHERE s.date = ?
              AND s.stars >= ?
              AND s.id NOT IN (
                  SELECT signal_id FROM results WHERE days_passed = ?
              )
        """, (signal_date, TRACKER_MIN_STARS, days))
        pending = c.fetchall()

        if not pending:
            print(f"[TRACKER] {days}天前（{signal_date}）：無待回補信號")
            continue

        print(f"[TRACKER] 回補 {days}天前（{signal_date}）：{len(pending)} 筆...")

        for signal_id, ticker, stars, entry_price in pending:
            if not entry_price or entry_price <= 0:
                continue

            exit_price = _get_close_price(ticker, today)
            if exit_price is None:
                continue

            pnl   = round((exit_price - entry_price) / entry_price * 100, 2)
            label = (
                "WIN"     if pnl >= TRACKER_WIN_THRESHOLD  else
                "LOSS"    if pnl <= TRACKER_LOSS_THRESHOLD else
                "NEUTRAL"
            )

            try:
                c.execute("""
                    INSERT OR IGNORE INTO results
                    (signal_id, days_passed, result_date,
                     entry_price, exit_price, pnl_percent, result_label)
                    VALUES (?,?,?,?,?,?,?)
                """, (signal_id, days, today,
                      entry_price, exit_price, pnl, label))
                if conn.execute("SELECT changes()").fetchone()[0]:
                    filled += 1
                    print(
                        f"   {'⭐'*stars} {ticker}　"
                        f"進場 {entry_price} → {days}天後 {exit_price}　"
                        f"{pnl:+.2f}% [{label}]"
                    )
            except Exception as e:
                print(f"[TRACKER] 寫入失敗 {ticker}：{e}")

    conn.commit()
    conn.close()
    print(f"[TRACKER] 回補完成：{filled} 筆")
    return filled


# ════════════════════════════════════════════
# 4. 匯出報告（供 NotebookLM 使用）
# ════════════════════════════════════════════

def export_report(output_path: str = None) -> str:
    """
    匯出分析報告 TXT + CSV。

    TXT：人類可讀摘要，直接上傳 NotebookLM
    CSV：完整原始數據，供進階分析

    回傳：TXT 報告路徑
    """
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    # 總覽
    c.execute("SELECT COUNT(*) FROM signals")
    total_signals = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM results")
    total_results = c.fetchone()[0]
    c.execute("SELECT MIN(date), MAX(date) FROM signals")
    date_range = c.fetchone()

    # 各星級 × 追蹤天數 勝率
    c.execute("""
        SELECT s.stars, r.days_passed,
               COUNT(*)  AS total,
               SUM(CASE WHEN r.result_label='WIN'  THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN r.result_label='LOSS' THEN 1 ELSE 0 END) AS losses,
               AVG(r.pnl_percent) AS avg_pnl
        FROM results r
        JOIN signals s ON r.signal_id = s.id
        GROUP BY s.stars, r.days_passed
        ORDER BY s.stars DESC, r.days_passed
    """)
    star_stats = c.fetchall()

    # 各 Agent 平均分（WIN vs LOSS，以 5 天結果為主）
    c.execute("""
        SELECT r.result_label,
               AVG(s.score_trend)         AS trend,
               AVG(s.score_momentum)      AS momentum,
               AVG(s.score_volatility)    AS volatility,
               AVG(s.score_institutional) AS institutional,
               AVG(s.score_margin)        AS margin,
               AVG(s.score_fundamental)   AS fundamental,
               AVG(s.score_announcement)  AS announcement,
               AVG(s.score_sentiment)     AS sentiment
        FROM results r
        JOIN signals s ON r.signal_id = s.id
        WHERE r.days_passed = 5
        GROUP BY r.result_label
    """)
    agent_breakdown = c.fetchall()

    # 最近 30 筆三星結果
    c.execute("""
        SELECT s.date, s.ticker, s.final_score,
               r.days_passed, r.pnl_percent, r.result_label
        FROM results r
        JOIN signals s ON r.signal_id = s.id
        WHERE s.stars = 3
        ORDER BY s.date DESC, r.days_passed
        LIMIT 30
    """)
    recent_three_star = c.fetchall()

    conn.close()

    # ── 建立報告目錄 ──
    today      = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")
    report_dir = Path(__file__).parent / "reports"
    report_dir.mkdir(exist_ok=True)

    if output_path is None:
        output_path = str(report_dir / f"signal_report_{today}.txt")

    # ── TXT 報告 ──
    agent_names = [
        "Trend", "Momentum", "Volatility",
        "Institutional", "Margin",
        "Fundamental", "Announcement", "Sentiment",
    ]
    lines = [
        "台股量化信號追蹤報告",
        f"產生時間：{today}",
        f"資料期間：{date_range[0]} ～ {date_range[1]}",
        "=" * 50,
        "",
        "【總覽】",
        f"  累積信號記錄：{total_signals} 筆",
        f"  已回補結果：  {total_results} 筆",
        "",
        f"【勝率統計（WIN = 漲幅 > {TRACKER_WIN_THRESHOLD}%，LOSS = 跌幅 < {TRACKER_LOSS_THRESHOLD}%）】",
    ]
    for stars, days, total, wins, losses, avg_pnl in star_stats:
        win_rate  = wins   / total * 100 if total > 0 else 0
        loss_rate = losses / total * 100 if total > 0 else 0
        lines.append(
            f"  {'⭐'*stars} {days:>2}天後 │ "
            f"WIN {win_rate:4.1f}% ({wins}/{total}) │ "
            f"LOSS {loss_rate:4.1f}% │ "
            f"平均 {avg_pnl:+.2f}%"
        )

    lines += ["", "【Agent 平均分對照（5天後 WIN vs LOSS）】"]
    for row in agent_breakdown:
        label  = row[0]
        scores = row[1:]
        parts  = []
        for name, score in zip(agent_names, scores):
            parts.append(f"{name}: {f'{score:.0f}' if score is not None else 'N/A'}")
        lines.append(f"  [{label:<7}] " + " | ".join(parts))

    lines += ["", "【最近三星信號結果（最新 30 筆）】"]
    for date, ticker, score, days, pnl, label in recent_three_star:
        lines.append(
            f"  {date}  {ticker:<12} 評分{score:>4.0f}分  "
            f"{days}天後 {pnl:+6.2f}%  [{label}]"
        )

    lines += [
        "",
        "=" * 50,
        "此報告可上傳至 NotebookLM 進行策略研究。",
        "",
        "建議分析問題：",
        "  1. 哪個星級的 5 天後勝率最高？有何規律？",
        "  2. WIN 組 vs LOSS 組的 Agent 分數差異在哪？",
        "  3. 籌碼面（Institutional/Margin）對勝率影響有多大？",
        "  4. 哪些信號特徵（top_signals）出現在勝率高的標的中？",
    ]

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # ── CSV 完整數據 ──
    csv_path = output_path.replace(".txt", ".csv")
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        SELECT s.date, s.ticker, s.stars, s.final_score, s.current_price,
               s.has_chips, s.has_fund, s.has_news,
               s.score_trend, s.score_momentum, s.score_volatility,
               s.score_institutional, s.score_margin,
               s.score_fundamental, s.score_announcement, s.score_sentiment,
               r.days_passed, r.exit_price, r.pnl_percent, r.result_label
        FROM signals s
        LEFT JOIN results r ON r.signal_id = s.id
        ORDER BY s.date DESC, s.stars DESC
    """)
    rows = c.fetchall()
    conn.close()

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "日期", "股票", "星級", "評分", "進場價",
            "有籌碼", "有基本面", "有消息",
            "趨勢分", "動能分", "波動分",
            "外資分", "融資分",
            "基本面分", "公告分", "情緒分",
            "追蹤天數", "出場價", "漲跌幅%", "結果",
        ])
        writer.writerows(rows)

    print(f"[TRACKER] 報告匯出完成：")
    print(f"   TXT → {output_path}")
    print(f"   CSV → {csv_path}")
    return output_path


# ════════════════════════════════════════════
# 5. CLI 入口
# ════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="台股量化信號追蹤工具")
    parser.add_argument("--init",     action="store_true", help="初始化資料庫")
    parser.add_argument("--backfill", action="store_true", help="手動回補 5/10 天前的信號結果")
    parser.add_argument("--report",   action="store_true", help="匯出分析報告（TXT + CSV）")
    args = parser.parse_args()

    if args.init:
        init_db()
    elif args.backfill:
        backfill_results()
    elif args.report:
        export_report()
    else:
        print("用法：")
        print("  python signal_tracker.py --init      # 初始化資料庫")
        print("  python signal_tracker.py --backfill  # 回補結果")
        print("  python signal_tracker.py --report    # 匯出報告（TXT + CSV）")
