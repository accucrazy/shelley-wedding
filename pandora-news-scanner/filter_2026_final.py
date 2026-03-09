# -*- coding: utf-8 -*-
"""
最終篩選：只留 2026 當月份的文章。
對缺日期的用 LLM + HTTP 再做一次判定。
"""
import json, os, sys, time, re
from pathlib import Path
from collections import Counter

sys.path.insert(0, os.path.expanduser(
    "~/.openclaw/skills/pandora-news/venv/lib/python3.9/site-packages"))
import httpx

if sys.stdout:
    sys.stdout.reconfigure(encoding='utf-8')

BASE = Path(os.path.expanduser(
    "~/.openclaw/workspace/newscollect/Pandora News IO 0226/3-Pandora News io"))

GEMINI_KEY = ""
GEMINI_URL = ""

JAN_PR_DATES = {
    "全家草莓季": "2026-01-05",
    "全家特力屋": "2026-01-06",
    "全家高山茶": "2026-01-08",
    "全家蜷川實花": "2026-01-12",
    "全家年菜預購": "2026-01-14",
    "全家超人力霸王": "2026-01-19",
    "全家寒流抗寒": "2026-01-19",
    "全家開運鮮食": "2026-01-20",
    "全家UCC咖啡": "2026-01-21",
    "全家溏心蛋": "2026-01-28",
    "全家伴手禮": "2026-01-30",
}

FEB_PR_DATES = {
    "全家助你擺脫收假症候群": "2026-02-01",
    "Fami!ce x 哆啦A夢": "2026-02-03",
    "全家草莓季": "2026-02-04",
    "年後甩油動起來": "2026-02-05",
    "抗寒三寶優惠出爐": "2026-02-06",
    "全家迎開學": "2026-02-10",
    "情人節空運玫瑰": "2026-02-11",
    "全家應援中華隊": "2026-02-13",
    "化身不打烊寵物店": "2026-02-17",
    "春遊賞櫻趣": "2026-02-18",
    "就一起挺中華隊": "2026-02-19",
    "世界番薯日": "2026-02-20",
    "228優惠": "2026-02-24",
    "日落優惠": "2026-02-25",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
}

DATE_META_PATTERNS = [
    r'<meta[^>]+(?:property|name)=["\'](?:article:published_time|datePublished|pubdate|date|og:article:published_time)["\'][^>]+content=["\']([^"\']+)["\']',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:article:published_time|datePublished|pubdate)["\']',
    r'"datePublished"\s*:\s*"([^"]+)"',
    r'<time[^>]+datetime=["\']([^"\']+)["\']',
]


def init_gemini():
    global GEMINI_KEY, GEMINI_URL
    env_file = os.path.expanduser("~/.openclaw/skills/pandora-news/.env")
    if os.path.exists(env_file):
        for line in open(env_file):
            if line.startswith("GOOGLE_API_KEY="):
                GEMINI_KEY = line.strip().split("=", 1)[1]
                break
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


def fetch_date_from_url(url):
    try:
        resp = httpx.get(url, timeout=8, follow_redirects=True, headers=HEADERS)
        if resp.status_code == 200:
            html = resp.text[:50000]
            for pattern in DATE_META_PATTERNS:
                m = re.search(pattern, html, re.IGNORECASE)
                if m:
                    raw = m.group(1).strip()
                    dm = re.match(r"(\d{4})-(\d{2})-(\d{2})", raw)
                    if dm:
                        return f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)}"
    except Exception:
        pass
    return ""


def llm_check_dates(items, target_prefix, pr_dates):
    """Use LLM to determine if no-date articles are from target month."""
    items_text = ""
    for pos, r in enumerate(items, 1):
        task = r.get("新聞", "")
        pr_date = pr_dates.get(task, "")
        items_text += (
            f"{pos}. 任務={task}, 發稿日={pr_date}, "
            f"媒體={r.get('媒體','')}, "
            f"標題={r.get('標題','')}, "
            f"連結={r.get('連結','')}\n")

    prompt = (
        f"以下新聞搜尋結果缺少發布日期。\n"
        f"每則的「發稿日」是全家便利商店新聞稿的發布日期。\n"
        f"通常媒體報導會在發稿日後 1-7 天內刊出。\n\n"
        f"請根據標題和連結中的線索（如 URL 中的日期、文章編號等），\n"
        f"判斷每篇是否可能是 {target_prefix} 的報導。\n\n"
        f"列表：\n{items_text}\n"
        f"請回覆 JSON array：\n"
        f'[{{"id": 1, "likely_2026": true/false, "estimated_date": "YYYY-MM-DD 或 unknown"}}]\n'
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
        return {item["id"]: item for item in arr}
    except Exception:
        return {}


def process_month(month, target_prefix, pr_dates):
    json_path = BASE / month / "全部任務_combined.json"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    results = data.get("results", [])
    passed = [r for r in results if r.get("llm_verified", "pass") == "pass"]

    already_ok = [r for r in passed if r.get("日期", "").startswith(target_prefix)]
    no_date = [r for r in passed if not r.get("日期", "").strip()]

    print(f"\n{'='*50}")
    print(f"{month} ({target_prefix})")
    print(f"  已確認當月: {len(already_ok)}")
    print(f"  無日期待救: {len(no_date)}")

    rescued = []

    # Step 1: HTTP fetch for no-date items
    print(f"\n  HTTP 抓取缺日期的 {len(no_date)} 筆...")
    http_fixed = 0
    for i, r in enumerate(no_date):
        url = r.get("連結", "")
        if url:
            date = fetch_date_from_url(url)
            if date and date.startswith(target_prefix):
                r["日期"] = date
                rescued.append(r)
                http_fixed += 1
            elif date:
                r["日期"] = date
        if (i + 1) % 30 == 0:
            print(f"    [{i+1}/{len(no_date)}] rescued: {http_fixed}")
        time.sleep(0.3)
    print(f"  HTTP 救回: {http_fixed}")

    # Step 2: LLM for remaining no-date
    still_no_date = [r for r in no_date if not r.get("日期", "").strip()]
    if still_no_date:
        print(f"\n  LLM 判定剩餘 {len(still_no_date)} 筆...")
        BATCH = 25
        llm_rescued = 0
        for batch_start in range(0, len(still_no_date), BATCH):
            batch = still_no_date[batch_start:batch_start + BATCH]
            verdicts = llm_check_dates(batch, target_prefix, pr_dates)

            for pos, r in enumerate(batch, 1):
                v = verdicts.get(pos, {})
                if v.get("likely_2026", False):
                    est = v.get("estimated_date", "")
                    if est and est != "unknown":
                        dm = re.match(r"\d{4}-\d{2}-\d{2}", est)
                        if dm and dm.group(0).startswith(target_prefix):
                            r["日期"] = dm.group(0)
                            rescued.append(r)
                            llm_rescued += 1

            time.sleep(1)
        print(f"  LLM 救回: {llm_rescued}")

    final = already_ok + rescued
    final.sort(key=lambda r: (r.get("新聞", ""), r.get("日期", "")))

    tc = Counter(r.get("新聞", "") for r in final)
    mc = len(set(r.get("媒體", "") for r in final))
    print(f"\n  最終: {len(final)} 筆, {mc} 個媒體")
    for t, c in sorted(tc.items()):
        print(f"    {t}: {c}")

    return final


def main():
    init_gemini()
    all_data = {}

    all_data["一月"] = process_month("一月", "2026-01", JAN_PR_DATES)
    all_data["二月"] = process_month("二月", "2026-02", FEB_PR_DATES)

    # Export
    print(f"\n{'='*50}")
    print("匯出到 Google Sheet...")
    export(all_data)


def export(all_data):
    sys.path.insert(0, os.path.expanduser(
        "~/.openclaw/skills/google-sheets/scripts"))
    try:
        from sheets_tools import get_sheets_service
        SHEET_ID = "1hh6wOIny3CwPB4bIVUPV7mtXNijijE2jN-p8zVK9qcU"
        service = get_sheets_service()
        meta = service.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
        existing_tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]

        header = ["任務", "日期", "媒體", "標題", "連結", "原生/轉載", "關鍵字", "來源"]

        for month, tab_name in [("一月", "一月(2026-01)"), ("二月", "二月(2026-02)")]:
            data = all_data[month]

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
            ] for r in data]

            service.spreadsheets().values().update(
                spreadsheetId=SHEET_ID, range=f"{tab_name}!A1",
                valueInputOption="USER_ENTERED",
                body={"values": [header] + rows}).execute()

            print(f"  {tab_name}: {len(rows)} 筆")

        print(f"\nhttps://docs.google.com/spreadsheets/d/{SHEET_ID}")
    except Exception as e:
        print(f"[!] Sheet 更新失敗: {e}")


if __name__ == "__main__":
    main()
