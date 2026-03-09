# -*- coding: utf-8 -*-
"""
Step 4: 直接 HTTP GET 抓取網頁，從 HTML meta tags 提取發布日期。
針對仍缺日期的 pass 結果。
"""
import json, os, sys, time, re, signal
from pathlib import Path

sys.path.insert(0, os.path.expanduser(
    "~/.openclaw/skills/pandora-news/venv/lib/python3.9/site-packages"))
import httpx

if sys.stdout:
    sys.stdout.reconfigure(encoding='utf-8')

BASE = Path(os.path.expanduser(
    "~/.openclaw/workspace/newscollect/Pandora News IO 0226/3-Pandora News io"))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html",
}

_shutdown = False
def _sig(s, f):
    global _shutdown; _shutdown = True
signal.signal(signal.SIGTERM, _sig)
signal.signal(signal.SIGINT, _sig)


DATE_META_PATTERNS = [
    r'<meta[^>]+(?:property|name)=["\'](?:article:published_time|datePublished|pubdate|date|sailthru\.date|DC\.date\.issued|publish-date|og:article:published_time)["\'][^>]+content=["\']([^"\']+)["\']',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:article:published_time|datePublished|pubdate|date)["\']',
    r'"datePublished"\s*:\s*"([^"]+)"',
    r'"publishedDate"\s*:\s*"([^"]+)"',
    r'"dateCreated"\s*:\s*"([^"]+)"',
    r'<time[^>]+datetime=["\']([^"\']+)["\']',
]


def extract_date_from_html(html):
    for pattern in DATE_META_PATTERNS:
        m = re.search(pattern, html, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            return normalize_date(raw)
    return ""


def normalize_date(raw):
    if not raw:
        return ""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"(\d{4})/(\d{2})/(\d{2})", raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return ""


def fetch_date(url):
    try:
        # Follow redirects (Google News links redirect)
        resp = httpx.get(url, timeout=8, follow_redirects=True, headers=HEADERS)
        if resp.status_code == 200:
            # Only check first 50KB for meta tags
            html = resp.text[:50000]
            return extract_date_from_html(html)
    except Exception:
        pass
    return ""


def process_month(month):
    json_path = BASE / month / "全部任務_combined.json"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    results = data.get("results", [])

    missing = [(i, results[i]) for i in range(len(results))
               if results[i].get("llm_verified", "pass") == "pass"
               and not results[i].get("日期", "").strip()]

    print(f"\n[{month}] {len(missing)} 筆缺日期，開始 HTTP 抓取...")

    fixed = 0
    errors = 0
    for idx, (i, r) in enumerate(missing):
        if _shutdown:
            break
        url = r.get("連結", "")
        if not url:
            continue

        date = fetch_date(url)
        if date:
            results[i]["日期"] = date
            fixed += 1

        if (idx + 1) % 50 == 0:
            print(f"  [{idx+1}/{len(missing)}] fixed: {fixed}")
            data["results"] = results
            json_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        time.sleep(0.3)

    data["results"] = results
    json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    total_pass = [r for r in results if r.get("llm_verified", "pass") == "pass"]
    has_date = sum(1 for r in total_pass if r.get("日期", "").strip())
    still_missing = len(total_pass) - has_date

    print(f"  HTTP 補日期: +{fixed}")
    print(f"  {month} 最終: 有日期 {has_date}, 仍缺 {still_missing}")

    return results


def main():
    all_results = {}
    for month in ["一月", "二月"]:
        results = process_month(month)
        passed = [r for r in results if r.get("llm_verified", "pass") == "pass"]
        all_results[month] = passed

    # Export
    print(f"\n{'='*50}")
    print("匯出到 Google Sheet...")
    export(all_results)


def export(all_results):
    sys.path.insert(0, os.path.expanduser(
        "~/.openclaw/skills/google-sheets/scripts"))
    try:
        from sheets_tools import get_sheets_service
        SHEET_ID = "1hh6wOIny3CwPB4bIVUPV7mtXNijijE2jN-p8zVK9qcU"
        service = get_sheets_service()

        meta = service.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
        existing_tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]

        header = ["任務", "日期", "媒體", "標題", "連結", "原生/轉載", "關鍵字", "來源"]

        for month, tab_name in [("一月", "一月掃描結果(含日期)"), ("二月", "二月掃描結果(含日期)")]:
            passed = all_results[month]

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
            no_date = sum(1 for r in rows if not r[1])
            print(f"  {tab_name}: {len(rows)} 筆 (有日期: {has_date}, 缺日期: {no_date})")

        print(f"\nhttps://docs.google.com/spreadsheets/d/{SHEET_ID}")
    except Exception as e:
        print(f"[!] Sheet 更新失敗: {e}")


if __name__ == "__main__":
    main()
