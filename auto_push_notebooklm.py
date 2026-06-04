"""
auto_push_notebooklm.py — 自動將月報上傳至 NotebookLM

功能：
  1. 產生當月信號追蹤報告（TXT）
  2. 上傳到 NotebookLM 固定筆記本「台股量化月報」
  3. 完成後 Discord 通知

執行方式：
  python auto_push_notebooklm.py          # 手動執行
  python auto_push_notebooklm.py --dry    # 只產生報告，不上傳（測試用）

排程（main.py 每月 1 號自動觸發）
"""

import asyncio
import argparse
import requests
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import os

load_dotenv(override=True)

from signal_tracker import export_report
from config import DISCORD_WEBHOOK_SIGNAL, TIMEZONE

NOTEBOOK_NAME = "台股量化月報"


# ════════════════════════════════════════════
# 上傳到 NotebookLM
# ════════════════════════════════════════════

async def push_to_notebooklm(report_path: str) -> bool:
    """
    上傳報告到 NotebookLM。
    若筆記本「台股量化月報」不存在則自動建立。

    回傳：成功 True / 失敗 False
    """
    try:
        from notebooklm import NotebookLMClient
    except ImportError:
        print("[LM] notebooklm-py 未安裝，跳過上傳")
        print("[LM] 本機安裝：pip install \"notebooklm-py[browser]\"")
        return False

    print(f"[LM] 連線 NotebookLM...")

    try:
        async with NotebookLMClient.from_storage() as client:

            # 找或建立固定筆記本
            notebook_id = await _get_or_create_notebook(client)
            if not notebook_id:
                return False

            # 上傳報告（以文字形式，避免 Windows cp950 編碼問題）
            print(f"[LM] 上傳報告：{report_path}")
            content = Path(report_path).read_text(encoding="utf-8")
            today   = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m")
            title   = f"台股量化月報 {today}"

            await client.sources.add_text(
                notebook_id,
                title=title,
                content=content,
                wait=True,
            )
            print(f"[LM] 上傳完成")
            return True

    except Exception as e:
        print(f"[LM] 上傳失敗：{e}")
        return False


async def _get_or_create_notebook(client) -> str | None:
    """找到「台股量化月報」筆記本 ID，若不存在則建立。"""
    try:
        notebooks = await client.notebooks.list()
        for nb in notebooks:
            title = getattr(nb, "title", "") or getattr(nb, "name", "")
            if title == NOTEBOOK_NAME:
                print(f"[LM] 使用現有筆記本：{NOTEBOOK_NAME}（{nb.id}）")
                return nb.id

        # 不存在 → 建立新的
        print(f"[LM] 建立新筆記本：{NOTEBOOK_NAME}")
        nb = await client.notebooks.create(NOTEBOOK_NAME)
        print(f"[LM] 筆記本建立完成（{nb.id}）")
        return nb.id

    except Exception as e:
        print(f"[LM] 筆記本操作失敗：{e}")
        return None


# ════════════════════════════════════════════
# Discord 通知
# ════════════════════════════════════════════

def notify_discord(success: bool, report_path: str):
    if not DISCORD_WEBHOOK_SIGNAL:
        return

    today = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")

    if success:
        msg = (
            f"📚 **NotebookLM 月報已更新** `{today}`\n"
            f"> 台股量化信號追蹤報告已上傳至「{NOTEBOOK_NAME}」\n"
            f"> 可至 [notebooklm.google.com](https://notebooklm.google.com) 查詢分析\n"
            f"> 建議問：**哪個 Agent 組合的三星信號勝率最高？**"
        )
    else:
        msg = (
            f"⚠️ **NotebookLM 月報上傳失敗** `{today}`\n"
            f"> 報告已生成於本機：`{report_path}`\n"
            f"> 請手動上傳或檢查 notebooklm-py 設定"
        )

    try:
        requests.post(
            DISCORD_WEBHOOK_SIGNAL,
            json={"content": msg},
            timeout=10,
        )
        print(f"[DISCORD] 通知已發送")
    except Exception as e:
        print(f"[DISCORD] 通知失敗：{e}")


# ════════════════════════════════════════════
# 主流程
# ════════════════════════════════════════════

async def run(dry_run: bool = False):
    today = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")
    print(f"\n{'='*50}")
    print(f"[START] NotebookLM 月報推送 [{today}]")
    print(f"{'='*50}")

    # 1. 產生報告
    print("[REPORT] 產生信號追蹤報告...")
    report_path = export_report()
    if not report_path or not Path(report_path).exists():
        print("[ERROR] 報告產生失敗，終止")
        return

    if dry_run:
        print(f"[DRY] 報告已產生：{report_path}")
        print("[DRY] --dry 模式，跳過上傳")
        return

    # 2. 上傳到 NotebookLM
    success = await push_to_notebooklm(report_path)

    # 3. Discord 通知
    notify_discord(success, report_path)

    print(f"[DONE] 完成")


# ════════════════════════════════════════════
# CLI 入口
# ════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="自動推送月報到 NotebookLM")
    parser.add_argument("--dry", action="store_true", help="只產生報告，不上傳（測試）")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry))
