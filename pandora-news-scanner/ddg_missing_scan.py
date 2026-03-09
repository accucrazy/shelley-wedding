# -*- coding: utf-8 -*-
"""
DuckDuckGo 掃未命中媒體：對 234 個還沒找到的媒體，逐個用 site: 搜尋。
每個任務 × 每個域名 = 1 次搜尋，快速全掃。
"""
import json, os, sys, time
from datetime import datetime
from urllib.parse import urlparse
from pathlib import Path

sys.path.insert(0, os.path.expanduser(
    "~/.openclaw/skills/pandora-news/venv/lib/python3.9/site-packages"))
from ddgs import DDGS

if sys.stdout:
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(os.path.expanduser(
    "~/.openclaw/workspace/newscollect/Pandora News IO 0226"))
MEDIA_LIST = BASE_DIR / "1-媒體清單" / "news-media-list.md"
OUTPUT_BASE = BASE_DIR / "3-Pandora News io"
COMBINED_JSON = OUTPUT_BASE / "一月" / "全部任務_combined.json"

AGGREGATOR_DOMAINS = {
    "today.line.me", "tw.news.yahoo.com", "msn.com", "news.pchome.com.tw"}

TASKS_CONFIG = {
    "全家草莓季": "全家草莓季",
    "全家UCC咖啡": "全家 UCC咖啡",
    "全家開運鮮食": "全家 開運鮮食",
    "全家年菜預購": "全家 年菜預購",
    "全家蜷川實花": "全家 蜷川實花",
    "全家特力屋": "全家 特力屋",
    "全家溏心蛋": "全家 溏心蛋",
    "全家高山茶": "全家 高山茶",
    "全家超人力霸王": "全家 超人力霸王",
    "全家寒流抗寒": "全家 寒流",
    "全家伴手禮": "全家 陳耀訓",
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

def get_hit_media_per_task():
    if not COMBINED_JSON.exists():
        return {}
    data = json.loads(COMBINED_JSON.read_text(encoding="utf-8"))
    hits = {}
    for r in data.get("results", []):
        task = r.get("新聞", "")
        media = r.get("媒體", "")
        hits.setdefault(task, set()).add(media)
    return hits

def ddg_search(query, max_results=5):
    for attempt in range(3):
        try:
            with DDGS() as d:
                return list(d.text(query, region="tw-tzh", max_results=max_results))
        except Exception as e:
            err = str(e)
            if "0x304" in err or "protocol" in err.lower():
                time.sleep(0.5)
                continue
            if "429" in err or "ratelimit" in err.lower():
                time.sleep(5)
                continue
            time.sleep(0.5)
    return []

def main():
    media_list = load_media_list()
    hits_per_task = get_hit_media_per_task()

    total_existing = sum(len(v) for v in hits_per_task.values())
    print(f"現有結果: {total_existing} 筆 (媒體×任務)")

    new_results = []
    total_searches = 0
    total_hits = 0

    for task_name, keyword in TASKS_CONFIG.items():
        task_hits = hits_per_task.get(task_name, set())
        missing = [m for m in media_list if m["name"] not in task_hits]

        if not missing:
            print(f"[{task_name}] 全部已命中")
            continue

        print(f"\n[{task_name}] 搜尋 {len(missing)} 個未命中媒體...")
        task_new = 0

        for i, m in enumerate(missing):
            domain = m["domain"]
            name = m["name"]

            if domain in AGGREGATOR_DOMAINS:
                q = f"{keyword} {name}"
            else:
                q = f"{keyword} site:{domain}"

            results = ddg_search(q, max_results=3)
            total_searches += 1

            for r in results:
                url = r.get("href", "")
                title = r.get("title", "")
                if not url or not title:
                    continue
                rd = urlparse(url).netloc.replace("www.", "")
                if domain not in rd and domain not in AGGREGATOR_DOMAINS:
                    continue

                new_results.append({
                    "新聞": task_name,
                    "日期": "",
                    "媒體": name,
                    "標題": title,
                    "連結": url,
                    "原生/轉載": "原生",
                    "關鍵字": keyword,
                    "來源": "DDG-site",
                })
                task_new += 1
                total_hits += 1
                break

            if (i + 1) % 50 == 0:
                print(f"  [{i+1}/{len(missing)}] hits: {task_new}")

            time.sleep(1.2)

        print(f"  → {task_name}: +{task_new}")

    print(f"\n{'='*50}")
    print(f"搜尋次數: {total_searches}")
    print(f"新增: {total_hits} 筆")

    if new_results:
        merge_and_export(new_results)

def merge_and_export(new_results):
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
    print(f"合併: +{added} 筆, 總計: {len(existing)} 筆")

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
        rows = [[r.get("新聞",""), r.get("日期",""), r.get("媒體",""),
                 r.get("標題",""), r.get("連結",""), r.get("原生/轉載",""),
                 r.get("關鍵字",""), r.get("來源","")] for r in existing]
        service.spreadsheets().values().update(
            spreadsheetId=SHEET_ID, range=f"{TAB}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": [header] + rows}).execute()
        print(f"Sheet 已更新: {len(rows)} 筆")
        print(f"https://docs.google.com/spreadsheets/d/{SHEET_ID}")
    except Exception as e:
        print(f"[!] Sheet 更新失敗: {e}")


if __name__ == "__main__":
    main()
