# -*- coding: utf-8 -*-
"""
從 Pandora Batch Scanner 的 JSON 結果檔匯出到 Google Sheet。
用法：
    cd ~/.openclaw/skills/google-sheets
    ./venv/bin/python /Users/accucrazy/DEV/openclaw/pandora-news-scanner/export_to_sheet.py
"""

import json, glob, os, sys

sys.path.insert(0, os.path.expanduser("~/.openclaw/skills/google-sheets/scripts"))
from sheets_tools import get_sheets_service

SHEET_ID = "1hh6wOIny3CwPB4bIVUPV7mtXNijijE2jN-p8zVK9qcU"
TAB_NAME = "Pandora掃描結果"

JSON_DIR = os.path.expanduser(
    "~/.openclaw/workspace/newscollect/Pandora News IO 0226/3-Pandora News io/一月"
)

HEADER = ["任務", "日期", "媒體", "標題", "連結", "原生/轉載", "關鍵字"]


def collect_results():
    """讀取所有 JSON 結果（每個任務取最新檔案），回傳 list of rows"""
    rows = []
    seen_urls = set()

    task_files = {}
    pattern = os.path.join(JSON_DIR, "*_2026-*.json")
    for fpath in sorted(glob.glob(pattern)):
        task = os.path.basename(fpath).split("_2026")[0]
        task_files[task] = fpath

    for task, fpath in sorted(task_files.items()):
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)

        results = data.get("results", [])
        for r in results:
            url = r.get("連結", "")
            if url in seen_urls:
                continue
            seen_urls.add(url)
            rows.append([
                r.get("新聞", task),
                r.get("日期", ""),
                r.get("媒體", ""),
                r.get("標題", ""),
                r.get("連結", ""),
                r.get("原生/轉載", ""),
                r.get("關鍵字", ""),
            ])

    return rows


def ensure_tab(service):
    """如果 tab 不存在就建立，如果已存在就清空"""
    meta = service.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    existing = [s["properties"]["title"] for s in meta.get("sheets", [])]

    if TAB_NAME in existing:
        service.spreadsheets().values().clear(
            spreadsheetId=SHEET_ID, range=f"{TAB_NAME}!A:Z"
        ).execute()
        print(f"已清空現有工作表 [{TAB_NAME}]")
    else:
        service.spreadsheets().batchUpdate(
            spreadsheetId=SHEET_ID,
            body={"requests": [{"addSheet": {"properties": {"title": TAB_NAME}}}]}
        ).execute()
        print(f"已建立新工作表 [{TAB_NAME}]")


def write_to_sheet(rows):
    service = get_sheets_service()
    ensure_tab(service)

    all_values = [HEADER] + rows

    service.spreadsheets().values().update(
        spreadsheetId=SHEET_ID,
        range=f"{TAB_NAME}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": all_values},
    ).execute()

    print(f"已寫入 {len(rows)} 筆資料到 [{TAB_NAME}]")
    print(f"Google Sheet 連結: https://docs.google.com/spreadsheets/d/{SHEET_ID}")


def main():
    rows = collect_results()
    if not rows:
        print("沒有找到任何已驗證的結果。")
        return

    task_counts = {}
    for r in rows:
        t = r[0]
        task_counts[t] = task_counts.get(t, 0) + 1

    print("=== 收集到的結果 ===")
    for t, c in task_counts.items():
        print(f"  {t}: {c} 筆")
    print(f"  合計: {len(rows)} 筆")
    print()

    write_to_sheet(rows)


if __name__ == "__main__":
    main()
