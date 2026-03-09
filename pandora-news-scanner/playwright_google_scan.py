# -*- coding: utf-8 -*-
"""
Playwright Google Search: 用瀏覽器搜 Google，對未命中的媒體做 site: 搜尋。
每 5 個 domain 打包成一次 OR 搜尋，加速掃描。

用法：
    ~/.openclaw/skills/pandora-news/venv/bin/python playwright_google_scan.py

背景執行：
    nohup ~/.openclaw/skills/pandora-news/venv/bin/python playwright_google_scan.py > /tmp/pw_scan.log 2>&1 &
"""
import json, os, sys, time, re, signal
from datetime import datetime
from urllib.parse import urlparse, quote_plus, urlencode
from pathlib import Path

sys.path.insert(0, os.path.expanduser(
    "~/.openclaw/skills/pandora-news/venv/lib/python3.9/site-packages"))

if sys.stdout:
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(os.path.expanduser(
    "~/.openclaw/workspace/newscollect/Pandora News IO 0226"))
MEDIA_LIST = BASE_DIR / "1-媒體清單" / "news-media-list.md"
OUTPUT_BASE = BASE_DIR / "3-Pandora News io"
COMBINED_JSON = OUTPUT_BASE / "一月" / "全部任務_combined.json"
PROGRESS_FILE = OUTPUT_BASE / "一月" / "pw_scan_progress.json"

SEARCH_DELAY = 6
BATCH_SIZE = 5

_shutdown = False
def _sig(s, f):
    global _shutdown; _shutdown = True
    print("\n[!] 收到停止信號，安全退出中...", flush=True)
signal.signal(signal.SIGTERM, _sig)
signal.signal(signal.SIGINT, _sig)

TASKS_CONFIG = {
    "全家草莓季": ["全家草莓季", "全家 ASAMIMICHAN"],
    "全家UCC咖啡": ["全家 UCC咖啡", "全家 阿里山極選"],
    "全家開運鮮食": ["全家 開運鮮食"],
    "全家年菜預購": ["全家 年菜預購"],
    "全家蜷川實花": ["全家 蜷川實花"],
    "全家特力屋": ["全家 特力屋"],
    "全家溏心蛋": ["全家 溏心蛋"],
    "全家高山茶": ["全家 高山茶"],
    "全家超人力霸王": ["全家 超人力霸王"],
    "全家寒流抗寒": ["全家 寒流 抗寒"],
    "全家伴手禮": ["全家 陳耀訓 紅土蛋黃酥"],
}


def load_media_list():
    content = MEDIA_LIST.read_text(encoding="utf-8")
    media = []
    for line in content.split("\n"):
        if "|" not in line or "---" in line or "媒體名稱" in line:
            continue
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) >= 2 and "." in parts[1]:
            media.append({"name": parts[0], "domain": parts[1]})
    return media


def get_hit_media():
    if not COMBINED_JSON.exists():
        return set()
    data = json.loads(COMBINED_JSON.read_text(encoding="utf-8"))
    return set(r.get("媒體", "") for r in data.get("results", []))


def load_progress():
    if PROGRESS_FILE.exists():
        try:
            return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"completed_batches": [], "results": []}


def save_progress(progress):
    PROGRESS_FILE.write_text(
        json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_google_results(page):
    """Extract search results from Google SERP."""
    results = []
    try:
        items = page.query_selector_all("div.g, div[data-hveid] a[href^='http']")
        for item in items:
            link_el = item.query_selector("a[href^='http']")
            title_el = item.query_selector("h3")
            if not link_el:
                continue
            href = link_el.get_attribute("href") or ""
            if not href or "google.com" in href:
                continue
            title = title_el.inner_text() if title_el else ""
            if not title:
                title = link_el.inner_text() or ""
            if title and href:
                results.append({"title": title.strip(), "url": href.strip()})
    except Exception:
        pass

    if not results:
        try:
            all_links = page.query_selector_all("a[href]")
            for a in all_links:
                href = a.get_attribute("href") or ""
                if href.startswith("http") and "google" not in href:
                    text = a.inner_text().strip()
                    if text and len(text) > 5:
                        results.append({"title": text, "url": href})
        except Exception:
            pass

    seen = set()
    unique = []
    for r in results:
        if r["url"] not in seen:
            seen.add(r["url"])
            unique.append(r)
    return unique


def check_captcha(page):
    try:
        content = page.content()
        if "unusual traffic" in content.lower() or "captcha" in content.lower():
            return True
        if page.query_selector("#captcha-form"):
            return True
    except Exception:
        pass
    return False


def google_search_batch(page, keyword, domains):
    """Search Google for keyword across multiple domains using OR syntax."""
    site_parts = " OR ".join(f"site:{d}" for d in domains)
    query = f"{keyword} ({site_parts})"

    params = urlencode({"q": query, "hl": "zh-TW", "gl": "tw", "num": "20"})
    url = f"https://www.google.com/search?{params}"

    try:
        page.goto(url, timeout=15000, wait_until="domcontentloaded")
        time.sleep(2)

        if check_captcha(page):
            print("    [!] CAPTCHA detected, waiting 30s...")
            time.sleep(30)
            page.goto(url, timeout=15000, wait_until="domcontentloaded")
            time.sleep(2)
            if check_captcha(page):
                print("    [!] Still CAPTCHA, skipping batch")
                return None

        return parse_google_results(page)
    except Exception as e:
        print(f"    [!] Error: {str(e)[:60]}")
        return []


def main():
    from playwright.sync_api import sync_playwright

    media_list = load_media_list()
    hit_media = get_hit_media()
    missing = [m for m in media_list if m["name"] not in hit_media]

    print(f"已命中: {len(hit_media)}, 未命中: {len(missing)}")

    progress = load_progress()
    completed = set(tuple(b) if isinstance(b, list) else b
                    for b in progress.get("completed_batches", []))
    new_results = progress.get("results", [])
    seen_keys = set(f"{r['媒體']}|{r['新聞']}" for r in new_results)

    domain_to_name = {m["domain"]: m["name"] for m in missing}

    batches = []
    for i in range(0, len(missing), BATCH_SIZE):
        batch_domains = [m["domain"] for m in missing[i:i+BATCH_SIZE]]
        batches.append(batch_domains)

    total_searches = len(batches) * len(TASKS_CONFIG)
    print(f"批次: {len(batches)} (每批 {BATCH_SIZE} 個 domain)")
    print(f"任務: {len(TASKS_CONFIG)}")
    print(f"預計搜尋: {total_searches} 次")
    print(f"已完成: {len(completed)}")
    print()

    captcha_count = 0
    search_count = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36",
            locale="zh-TW",
            viewport={"width": 1280, "height": 720},
        )
        page = context.new_page()

        page.goto("https://www.google.com/?hl=zh-TW", wait_until="domcontentloaded")
        time.sleep(2)
        try:
            accept_btn = page.query_selector("button:has-text('Accept'), button:has-text('同意')")
            if accept_btn:
                accept_btn.click()
                time.sleep(1)
        except Exception:
            pass

        for task_name, keywords in TASKS_CONFIG.items():
            if _shutdown:
                break

            kw = keywords[0]
            print(f"\n{'='*50}")
            print(f"[{task_name}] keyword: '{kw}'")

            task_hits = 0
            for batch_idx, batch_domains in enumerate(batches):
                if _shutdown:
                    break

                batch_key = f"{task_name}|{batch_idx}"
                if batch_key in completed:
                    continue

                results = google_search_batch(page, kw, batch_domains)
                search_count += 1

                if results is None:
                    captcha_count += 1
                    if captcha_count >= 3:
                        print("  [!] 太多 CAPTCHA，停止搜尋")
                        _shutdown = True
                        break
                    continue

                for r in results:
                    url = r["url"]
                    host = urlparse(url).netloc.replace("www.", "").lower()
                    matched_domain = None
                    matched_name = None
                    for d in batch_domains:
                        if d in host or host.endswith("." + d):
                            matched_domain = d
                            matched_name = domain_to_name.get(d, "")
                            break
                    if not matched_name:
                        continue

                    key = f"{matched_name}|{task_name}"
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)

                    new_results.append({
                        "新聞": task_name,
                        "日期": "",
                        "媒體": matched_name,
                        "標題": r["title"],
                        "連結": url,
                        "原生/轉載": "原生",
                        "關鍵字": kw,
                        "來源": "Google",
                    })
                    task_hits += 1

                completed.add(batch_key)

                if (batch_idx + 1) % 10 == 0:
                    print(f"  [{batch_idx+1}/{len(batches)}] "
                          f"hits: {task_hits}, total new: {len(new_results)}")
                    progress["completed_batches"] = list(completed)
                    progress["results"] = new_results
                    save_progress(progress)

                time.sleep(SEARCH_DELAY)

            print(f"  [{task_name}] 新增: {task_hits}")
            progress["completed_batches"] = list(completed)
            progress["results"] = new_results
            save_progress(progress)

        browser.close()

    print(f"\n{'='*50}")
    print(f"搜尋次數: {search_count}, CAPTCHA: {captcha_count}")
    print(f"新增結果: {len(new_results)} 筆")

    if new_results:
        print(f"\n合併到 combined.json...")
        merge_results(new_results)


def merge_results(new_results):
    if not COMBINED_JSON.exists():
        return
    data = json.loads(COMBINED_JSON.read_text(encoding="utf-8"))
    existing = data.get("results", [])
    existing_keys = set(f"{r.get('媒體','')}|{r.get('新聞','')}" for r in existing)

    added = 0
    for r in new_results:
        key = f"{r['媒體']}|{r['新聞']}"
        if key not in existing_keys:
            existing.append(r)
            existing_keys.add(key)
            added += 1

    data["results"] = existing
    data["summary"]["total"] = len(existing)
    COMBINED_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  合併: +{added} 筆, 總計: {len(existing)} 筆")

    sys.path.insert(0, os.path.expanduser(
        "~/.openclaw/skills/google-sheets/scripts"))
    try:
        from sheets_tools import get_sheets_service
        SHEET_ID = "1hh6wOIny3CwPB4bIVUPV7mtXNijijE2jN-p8zVK9qcU"
        TAB = "Pandora掃描結果"
        service = get_sheets_service()
        service.spreadsheets().values().clear(
            spreadsheetId=SHEET_ID, range=f"{TAB}!A:Z").execute()
        header = ["任務", "日期", "媒體", "標題", "連結", "原生/轉載", "關鍵字", "來源"]
        rows = [[r.get("新聞", ""), r.get("日期", ""), r.get("媒體", ""),
                 r.get("標題", ""), r.get("連結", ""), r.get("原生/轉載", ""),
                 r.get("關鍵字", ""), r.get("來源", "")] for r in existing]
        service.spreadsheets().values().update(
            spreadsheetId=SHEET_ID, range=f"{TAB}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": [header] + rows}).execute()
        print(f"  Sheet 已更新: {len(rows)} 筆")
    except Exception as e:
        print(f"  [!] Sheet 更新失敗: {e}")


if __name__ == "__main__":
    main()
