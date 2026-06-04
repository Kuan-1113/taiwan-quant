import os
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ──────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ── Discord ──────────────────────────────────────────
DISCORD_WEBHOOK_SIGNAL = os.getenv("DISCORD_WEBHOOK_SIGNAL", "")  # #毛 頻道

# ── 掃描設定 ──────────────────────────────────────────
# 每次掃描的股票池：TWSE上市 + TPEx上櫃
SCAN_MARKET    = os.getenv("SCAN_MARKET", "both")   # twse / tpex / both
MAX_WORKERS    = int(os.getenv("MAX_WORKERS", "20")) # 平行抓取執行緒數
MIN_MARKET_CAP = int(os.getenv("MIN_MARKET_CAP", "3000000000"))   # 市值下限 30億
MIN_AVG_VOLUME = int(os.getenv("MIN_AVG_VOLUME", "1000"))          # 日均量下限 1000張

# ── 排程 ──────────────────────────────────────────────
SCHEDULE_TIME = os.getenv("SCHEDULE_TIME", "17:00")  # 每日發信號時間
TIMEZONE      = os.getenv("TIMEZONE", "Asia/Taipei")

# ── 技術指標門檻 ──────────────────────────────────────
ADX_TREND_THRESHOLD  = float(os.getenv("ADX_TREND_THRESHOLD", "25"))   # ADX > 25 才算趨勢
RSI_OVERSOLD         = float(os.getenv("RSI_OVERSOLD", "40"))
RSI_OVERBOUGHT       = float(os.getenv("RSI_OVERBOUGHT", "75"))
VOLUME_MULT          = float(os.getenv("VOLUME_MULT", "1.5"))           # 量能放大倍數

# ── 評分門檻 ──────────────────────────────────────────
SCORE_THREE_STAR = float(os.getenv("SCORE_THREE_STAR", "80"))  # [***]
SCORE_TWO_STAR   = float(os.getenv("SCORE_TWO_STAR", "60"))    # [**]
SCORE_ONE_STAR   = float(os.getenv("SCORE_ONE_STAR", "40"))    # [*]

# ── 信號追蹤門檻 ──────────────────────────────────────
TRACKER_WIN_THRESHOLD  = float(os.getenv("TRACKER_WIN_THRESHOLD", "3.0"))   # 漲幅 > 3% 算 WIN
TRACKER_LOSS_THRESHOLD = float(os.getenv("TRACKER_LOSS_THRESHOLD", "-3.0")) # 跌幅 < -3% 算 LOSS
TRACKER_MIN_STARS      = int(os.getenv("TRACKER_MIN_STARS", "1"))           # 追蹤最低星級（1=全追蹤）
