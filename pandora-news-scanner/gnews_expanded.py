# -*- coding: utf-8 -*-
"""
Google News RSS 超大量搜尋：每個任務用 10+ 個拆開/重組的關鍵字。
跟 media list 比對，新結果合併到 combined.json。
"""
import json, os, sys, time, re
from urllib.parse import urlencode, urlparse, quote_plus
from xml.etree import ElementTree
from pathlib import Path

sys.path.insert(0, os.path.expanduser(
    "~/.openclaw/skills/pandora-news/venv/lib/python3.9/site-packages"))
import httpx

if sys.stdout:
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(os.path.expanduser(
    "~/.openclaw/workspace/newscollect/Pandora News IO 0226"))
MEDIA_LIST = BASE_DIR / "1-媒體清單" / "news-media-list.md"
COMBINED_JSON = BASE_DIR / "3-Pandora News io" / "一月" / "全部任務_combined.json"

TASKS_EXPANDED = {
    "全家草莓季": [
        "全家草莓季", "全家 草莓", "全家便利商店 草莓季",
        "FamilyMart 草莓季", "FamilyMart strawberry",
        "全家 ASAMIMICHAN", "全家 草莓甜點",
        "全家 草莓季 2026", "全家 草莓蛋糕",
        "全家 麻佬 草莓", "全家 草莓大福",
        "全家 草莓 新品", "全家 草莓三明治",
        "全家 草莓牛奶", "全家 草莓霜淇淋",
    ],
    "全家UCC咖啡": [
        "全家 UCC咖啡", "全家 UCC", "全家便利商店 UCC",
        "全家 阿里山極選", "全家 阿里山咖啡",
        "FamilyMart UCC", "全家 UCC 聯名",
        "全家 精品咖啡", "全家 UCC COFFEE",
        "全家 咖啡 阿里山", "全家 單品咖啡",
    ],
    "全家開運鮮食": [
        "全家 開運鮮食", "全家便利商店 開運", "全家 鮮食 開運",
        "全家 開運 新年", "全家 開運便當", "全家 開運飯糰",
        "全家 新年鮮食", "全家 春節鮮食", "全家 鮮食 新品",
        "FamilyMart 開運",
    ],
    "全家年菜預購": [
        "全家 年菜預購", "全家便利商店 年菜", "全家 年菜 2026",
        "FamilyMart 年菜", "全家 圍爐", "全家 年菜 預購",
        "全家 春節 年菜", "全家 除夕 年菜",
        "全家 年菜組合", "全家 年菜推薦", "全家 年菜 佛跳牆",
    ],
    "全家蜷川實花": [
        "全家 蜷川實花", "全家 蜷川", "全家便利商店 蜷川實花",
        "FamilyMart 蜷川實花", "FamilyMart Mika Ninagawa",
        "全家 蜷川實花 聯名", "全家 蜷川實花 集點",
        "全家 蜷川 花", "全家 Ninagawa",
    ],
    "全家特力屋": [
        "全家 特力屋", "全家便利商店 特力屋", "全家 特力屋 聯名",
        "FamilyMart 特力屋", "全家 特力屋 合作",
        "全家 特力屋 居家", "全家 特力屋 好物",
    ],
    "全家溏心蛋": [
        "全家 溏心蛋", "全家便利商店 溏心蛋", "全家 溏心蛋 新品",
        "FamilyMart 溏心蛋", "全家 溏心蛋 口味",
        "全家 蛋料理", "全家 溫泉蛋", "全家 半熟蛋",
    ],
    "全家高山茶": [
        "全家 高山茶", "全家便利商店 高山茶", "全家 茶飲 高山",
        "FamilyMart 高山茶", "全家 高山烏龍",
        "全家 茶葉 高山", "全家 FMC 高山茶",
    ],
    "全家超人力霸王": [
        "全家 超人力霸王", "全家便利商店 超人力霸王",
        "FamilyMart 超人力霸王", "全家 奧特曼",
        "全家 超人力霸王 集點", "全家 超人力霸王 聯名",
        "全家 Ultraman", "FamilyMart Ultraman",
    ],
    "全家寒流抗寒": [
        "全家 寒流", "全家 抗寒", "全家便利商店 寒流",
        "全家 熱飲", "全家 暖心", "全家 冬季",
        "全家 熱食 寒流", "全家 暖胃",
    ],
    "全家伴手禮": [
        "全家 陳耀訓", "全家 紅土蛋黃酥", "全家便利商店 伴手禮",
        "全家 伴手禮", "FamilyMart 伴手禮",
        "全家 陳耀訓 蛋黃酥", "全家 年節伴手禮",
        "全家 送禮", "全家 禮盒",
    ],
}


def load_media_list():
    content = MEDIA_LIST.read_text(encoding="utf-8")
    domain_map = {}
    for line in content.split("\n"):
        if "|" not in line or "---" in line or "媒體名稱" in line:
            continue
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) >= 2 and "." in parts[1]:
            domain_map[parts[1]] = parts[0]
    return domain_map


def google_news_rss(keyword):
    """Fetch Google News RSS for a keyword."""
    url = f"https://news.google.com/rss/search?q={quote_plus(keyword)}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    try:
        resp = httpx.get(url, timeout=10, follow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return []
        root = ElementTree.fromstring(resp.content)
        items = []
        for item in root.findall(".//item"):
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pub_date = item.findtext("pubDate", "")
            source = item.find("source")
            source_name = source.text if source is not None else ""
            source_url = ""
            if source is not None:
                source_url = source.get("url", "")
            items.append({
                "title": title, "link": link, "pub_date": pub_date,
                "source_name": source_name, "source_url": source_url,
            })
        return items
    except Exception:
        return []


def match_domain(source_url, domain_map):
    if not source_url:
        return None, None
    host = urlparse(source_url).netloc.replace("www.", "").lower()
    for domain, name in domain_map.items():
        if domain in host or host.endswith("." + domain) or host == domain:
            return domain, name
    for domain, name in domain_map.items():
        d_base = domain.split(".")[-2] if "." in domain else domain
        h_base = host.split(".")[-2] if "." in host else host
        if d_base == h_base and len(d_base) > 3:
            return domain, name
    return None, None


def main():
    domain_map = load_media_list()
    data = json.loads(COMBINED_JSON.read_text(encoding="utf-8"))
    existing = data.get("results", [])
    existing_keys = set(f"{r.get('媒體','')}|{r.get('新聞','')}" for r in existing)
    initial_count = len(existing)

    print(f"現有: {initial_count} 筆")
    total_rss = 0
    total_matched = 0
    total_new = 0

    for task_name, keywords in TASKS_EXPANDED.items():
        print(f"\n[{task_name}] {len(keywords)} 個關鍵字...")
        task_new = 0

        for kw in keywords:
            items = google_news_rss(kw)
            total_rss += len(items)

            for item in items:
                domain, name = match_domain(item["source_url"], domain_map)
                if not name:
                    continue
                total_matched += 1

                key = f"{name}|{task_name}"
                if key in existing_keys:
                    continue
                existing_keys.add(key)

                existing.append({
                    "新聞": task_name,
                    "日期": item.get("pub_date", ""),
                    "媒體": name,
                    "標題": item["title"],
                    "連結": item["link"],
                    "原生/轉載": "原生",
                    "關鍵字": kw,
                    "來源": "GNews-RSS",
                })
                task_new += 1
                total_new += 1

            time.sleep(0.5)

        print(f"  → +{task_new}")

    data["results"] = existing
    data["summary"]["total"] = len(existing)
    COMBINED_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*50}")
    print(f"RSS 條目: {total_rss}, 媒體匹配: {total_matched}")
    print(f"新增: {total_new}, 總計: {len(existing)}")
    print(f"涵蓋媒體: {len(set(r.get('媒體','') for r in existing))}")

    export_sheet(existing)


def export_sheet(results):
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
                 r.get("關鍵字",""), r.get("來源","")] for r in results]
        service.spreadsheets().values().update(
            spreadsheetId=SHEET_ID, range=f"{TAB}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": [header] + rows}).execute()
        print(f"Sheet 已更新: {len(rows)} 筆")
    except Exception as e:
        print(f"[!] Sheet 更新失敗: {e}")


if __name__ == "__main__":
    main()
