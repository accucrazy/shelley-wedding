# -*- coding: utf-8 -*-
"""
日期修復：三階段補上所有 pass 結果的發布日期。
1) 標準化已有 RSS 日期
2) 從 URL 提取日期
3) LLM 從標題+URL 推斷日期
"""
import json, os, sys, time, re, signal
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from pathlib import Path

sys.path.insert(0, os.path.expanduser(
    "~/.openclaw/skills/pandora-news/venv/lib/python3.9/site-packages"))
import httpx

if sys.stdout:
    sys.stdout.reconfigure(encoding='utf-8')

BASE = Path(os.path.expanduser(
    "~/.openclaw/workspace/newscollect/Pandora News IO 0226/3-Pandora News io"))

GEMINI_KEY = ""
GEMINI_URL = ""

_shutdown = False
def _sig(s, f):
    global _shutdown; _shutdown = True
signal.signal(signal.SIGTERM, _sig)
signal.signal(signal.SIGINT, _sig)


def init_gemini():
    global GEMINI_KEY, GEMINI_URL
    for loc in [os.path.expanduser("~/.openclaw/skills/pandora-news/.env")]:
        if os.path.exists(loc):
            for line in open(loc):
                if line.startswith("GOOGLE_API_KEY="):
                    GEMINI_KEY = line.strip().split("=", 1)[1]
                    break
        if GEMINI_KEY:
            break
    if not GEMINI_KEY:
        GEMINI_KEY = os.environ.get("GOOGLE_API_KEY", "")
    GEMINI_URL = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={GEMINI_KEY}")


def call_gemini(prompt, retries=3):
    for attempt in range(retries):
        try:
            resp = httpx.post(GEMINI_URL,
                json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
            if resp.status_code == 200:
                return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            elif resp.status_code == 429:
                time.sleep(5 * (attempt + 1))
        except Exception:
            time.sleep(2)
    return None


# ─── Step 1: Parse RSS date to YYYY-MM-DD ───

def parse_rss_date(raw):
    """Convert RSS/various date formats to YYYY-MM-DD."""
    if not raw or not raw.strip():
        return ""
    raw = raw.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw
    try:
        dt = parsedate_to_datetime(raw)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                "%Y/%m/%d", "%Y年%m月%d日"]:
        try:
            dt = datetime.strptime(raw[:len(fmt)+5], fmt)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            pass
    m = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return ""


# ─── Step 2: Extract date from URL ───

URL_DATE_PATTERNS = [
    r"/(\d{4})(\d{2})(\d{2})/",          # /20260107/
    r"/(\d{4})/(\d{2})/(\d{2})/",        # /2026/01/07/
    r"/(\d{4})-(\d{2})-(\d{2})",         # /2026-01-07
    r"/(\d{4})(\d{2})(\d{2})\d+",        # /20260107123456
    r"[?&]date=(\d{4})(\d{2})(\d{2})",   # ?date=20260107
    r"/news/(\d{4})(\d{2})(\d{2})",      # /news/20260107
    r"/article/(\d{4})(\d{2})(\d{2})",   # /article/20260107
]

def extract_date_from_url(url):
    if not url:
        return ""
    for pattern in URL_DATE_PATTERNS:
        m = re.search(pattern, url)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 2020 <= y <= 2030 and 1 <= mo <= 12 and 1 <= d <= 31:
                return f"{y}-{mo:02d}-{d:02d}"
    return ""


# ─── Step 3: LLM batch date extraction ───

def llm_extract_dates(items_batch):
    """Use LLM to extract dates from title + URL."""
    items_text = ""
    for pos, item in enumerate(items_batch, 1):
        items_text += (
            f"{pos}. 媒體={item.get('媒體','')}, "
            f"標題={item.get('標題','')}, "
            f"連結={item.get('連結','')}\n")

    prompt = (
        f"以下是新聞搜尋結果，請從標題、連結中推斷每則新聞的發布日期。\n\n"
        f"提示：\n"
        f"- URL 中常包含日期，如 /20260107/ 表示 2026-01-07\n"
        f"- 標題中可能有月份、季節、節日等時間線索\n"
        f"- 如果完全無法判斷，填 \"unknown\"\n\n"
        f"列表：\n{items_text}\n"
        f"請回覆 JSON array：\n"
        f'[{{"id": 1, "date": "YYYY-MM-DD"}}]\n'
        f"只回 JSON array。"
    )

    response = call_gemini(prompt)
    if not response:
        return {}
    try:
        clean = response.strip()
        if clean.startswith("```"):
            clean = re.sub(r"^```\w*\n?", "", clean)
            clean = re.sub(r"\n?```$", "", clean)
        arr = json.loads(clean)
        return {item["id"]: item.get("date", "unknown") for item in arr}
    except Exception:
        return {}


# ─── Main processing ───

def process_month(month):
    json_path = BASE / month / "全部任務_combined.json"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    results = data.get("results", [])
    passed_indices = [i for i, r in enumerate(results)
                      if r.get("llm_verified", "pass") == "pass"]

    print(f"\n{'='*60}")
    print(f"處理 {month}: {len(passed_indices)} 筆 pass")

    # Step 1: Normalize existing dates
    step1_fixed = 0
    for i in passed_indices:
        raw = results[i].get("日期", "")
        if raw and not re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
            normalized = parse_rss_date(raw)
            if normalized:
                results[i]["日期"] = normalized
                step1_fixed += 1
    print(f"Step 1 (標準化 RSS 日期): {step1_fixed} 筆修正")

    # Step 2: Extract from URL for items still missing dates
    step2_fixed = 0
    for i in passed_indices:
        if results[i].get("日期", "").strip():
            continue
        url_date = extract_date_from_url(results[i].get("連結", ""))
        if url_date:
            results[i]["日期"] = url_date
            step2_fixed += 1
    print(f"Step 2 (URL 日期提取): {step2_fixed} 筆修正")

    # Step 3: LLM for remaining
    still_missing = [(i, results[i]) for i in passed_indices
                     if not results[i].get("日期", "").strip()]
    print(f"Step 3 (LLM 推斷): {len(still_missing)} 筆待處理")

    BATCH = 30
    step3_fixed = 0
    for batch_start in range(0, len(still_missing), BATCH):
        if _shutdown:
            break
        batch = still_missing[batch_start:batch_start + BATCH]
        batch_items = [r for _, r in batch]

        verdicts = llm_extract_dates(batch_items)

        for pos, (orig_idx, _) in enumerate(batch, 1):
            date_val = verdicts.get(pos, "unknown")
            if date_val and date_val != "unknown":
                parsed = parse_rss_date(date_val)
                if parsed:
                    results[orig_idx]["日期"] = parsed
                    step3_fixed += 1

        time.sleep(1)

    print(f"Step 3 (LLM 推斷): {step3_fixed} 筆修正")

    # Summary
    final_has = sum(1 for i in passed_indices if results[i].get("日期", "").strip())
    final_missing = len(passed_indices) - final_has
    print(f"\n{month} 結果: 有日期 {final_has}, 仍缺 {final_missing}")

    data["results"] = results
    json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return results, passed_indices


def main():
    init_gemini()
    all_month_data = {}

    for month in ["一月", "二月"]:
        results, passed_idx = process_month(month)
        passed = [results[i] for i in passed_idx]
        all_month_data[month] = passed

    # Export to Sheet
    print(f"\n{'='*60}")
    print("匯出到 Google Sheet...")
    export_to_sheet(all_month_data)


def export_to_sheet(all_month_data):
    sys.path.insert(0, os.path.expanduser(
        "~/.openclaw/skills/google-sheets/scripts"))
    try:
        from sheets_tools import get_sheets_service
        SHEET_ID = "1hh6wOIny3CwPB4bIVUPV7mtXNijijE2jN-p8zVK9qcU"
        service = get_sheets_service()

        meta = service.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
        existing_tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]

        header = ["任務", "日期", "媒體", "標題", "連結", "原生/轉載", "關鍵字", "來源"]

        tab_map = {
            "一月": "一月掃描結果(含日期)",
            "二月": "二月掃描結果(含日期)",
        }

        for month, tab_name in tab_map.items():
            passed = all_month_data[month]

            if tab_name not in existing_tabs:
                service.spreadsheets().batchUpdate(
                    spreadsheetId=SHEET_ID,
                    body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]}
                ).execute()
                existing_tabs.append(tab_name)
            else:
                service.spreadsheets().values().clear(
                    spreadsheetId=SHEET_ID, range=f"{tab_name}!A:Z").execute()

            rows = [[
                r.get("新聞", ""), r.get("日期", ""), r.get("媒體", ""),
                r.get("標題", ""), r.get("連結", ""), r.get("原生/轉載", ""),
                r.get("關鍵字", ""), r.get("來源", ""),
            ] for r in passed]

            rows.sort(key=lambda x: (x[0], x[1] or "9999"))

            service.spreadsheets().values().update(
                spreadsheetId=SHEET_ID, range=f"{tab_name}!A1",
                valueInputOption="USER_ENTERED",
                body={"values": [header] + rows}).execute()

            has_date = sum(1 for r in rows if r[1])
            print(f"  {tab_name}: {len(rows)} 筆 (有日期: {has_date})")

        print(f"\nhttps://docs.google.com/spreadsheets/d/{SHEET_ID}")
    except Exception as e:
        print(f"[!] Sheet 更新失敗: {e}")


if __name__ == "__main__":
    main()
