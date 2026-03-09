# -*- coding: utf-8 -*-
"""
v2: 多策略搜尋 — Google News RSS + DDG 廣域 + 新聞稿標題搜尋
盡可能撈最多命中。
"""
import json, os, sys, time, re, glob
from datetime import datetime
from urllib.parse import urlparse, quote
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.expanduser(
    "~/.openclaw/skills/pandora-news/venv/lib/python3.9/site-packages"))
import httpx

try:
    from ddgs import DDGS
except ImportError:
    DDGS = None

if sys.stdout:
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(os.path.expanduser(
    "~/.openclaw/workspace/newscollect/Pandora News IO 0226"))
MEDIA_LIST = BASE_DIR / "1-媒體清單" / "news-media-list.md"
OUTPUT_BASE = BASE_DIR / "3-Pandora News io"

def _load_api_key():
    p = Path(os.path.expanduser("~/.openclaw/.env"))
    if p.exists():
        for line in p.read_text().splitlines():
            if line.startswith("GOOGLE_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""

GEMINI_API_KEY = _load_api_key()
GEMINI_URL = ("https://generativelanguage.googleapis.com/v1beta"
              "/models/gemini-2.0-flash:generateContent")

TASKS_CONFIG = {
    "全家草莓季": {
        "keywords": ["全家草莓季", "全家 ASAMIMICHAN", "全家 草莓霜淇淋",
                     "全家 莓好運輸中", "全家 草莓優格霜淇淋", "FamilyMart 草莓季"],
        "press_title_fragments": [
            "草莓季17粉嫩登場",
            "ASAMIMICHAN萌翻全台",
            "草莓優格霜淇淋 草莓厚奶雲餡泡芙",
        ],
        "month": "一月"},
    "全家UCC咖啡": {
        "keywords": ["全家 UCC咖啡", "全家 阿里山極選", "全家 Let's Café 阿里山",
                     "全家 雙冠軍監製", "全家 阿里山極選綜合咖啡"],
        "press_title_fragments": [
            "再攜UCC推雙冠軍監製",
            "阿里山極選綜合咖啡65元",
        ],
        "month": "一月"},
    "全家開運鮮食": {
        "keywords": ["全家 開運鮮食", "全家 紅運烏魚子", "全家 蘭州拉麵",
                     "全家 開運鮮食祭"],
        "press_title_fragments": ["開運鮮食祭", "紅運烏魚子"],
        "month": "一月"},
    "全家年菜預購": {
        "keywords": ["全家 年菜預購", "全家 2026金馬年菜", "全家 FamiPort 年菜",
                     "全家 星級年菜", "全家 富錦樹 年菜"],
        "press_title_fragments": [
            "搶攻圍爐商機 2026金馬年菜",
            "FamiPort一站購足 星級名店",
        ],
        "month": "一月"},
    "全家蜷川實花": {
        "keywords": ["全家 蜷川實花", "全家 蜷川實花展", "全家 蜷川實花 杯身"],
        "press_title_fragments": [
            "攜手蜷川實花展推獨家限定杯身",
            "全家 蜷川實花 杯套",
        ],
        "month": "一月"},
    "全家特力屋": {
        "keywords": ["全家 特力屋", "全家 居家微整型", "全家 免治馬桶 特力屋",
                     "全家行動購 特力屋"],
        "press_title_fragments": [
            "攜特力屋齊推居家微整型",
            "免治馬桶 電子鎖8990元含安裝",
        ],
        "month": "一月"},
    "全家溏心蛋": {
        "keywords": ["全家 溏心蛋", "全家 日式溏心蛋", "全家 用撈的 溏心蛋",
                     "全家 溏心蛋 25元"],
        "press_title_fragments": [
            "首推用撈的日式溏心蛋",
            "熟食區新蛋報到 溏心蛋25元",
        ],
        "month": "一月"},
    "全家高山茶": {
        "keywords": ["全家 高山茶", "全家 蘭韻梨山烏龍", "全家 Let's Tea 高山茶",
                     "全家 現煮精品茶"],
        "press_title_fragments": [
            "寒流飄茶香 高山茶進駐全家",
            "蘭韻梨山烏龍49元",
        ],
        "month": "一月"},
    "全家超人力霸王": {
        "keywords": ["全家 超人力霸王", "全家 高雄冬日遊樂園", "全家 超人力霸王 聯名",
                     "全家 超人力霸王 杯塞"],
        "press_title_fragments": [
            "超人力霸王60周年降臨高雄",
            "全家 超人力霸王 聯名杯塞 拍拍燈",
        ],
        "month": "一月"},
    "全家寒流抗寒": {
        "keywords": ["全家 寒流", "全家 抗寒", "全家 寒流 熱食", "全家 暖暖包"],
        "press_title_fragments": [],
        "month": "一月"},
    "全家伴手禮": {
        "keywords": ["全家 陳耀訓", "全家 紅土蛋黃酥", "全家 伴手禮 過年",
                     "全家 春節伴手禮"],
        "press_title_fragments": [
            "陳耀訓 紅土蛋黃酥",
        ],
        "month": "一月"},
}

# ── Media list ───────────────────────────────────────
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

def build_domain_map(media_list):
    dmap = {}
    for m in media_list:
        d = m["domain"].replace("www.", "")
        dmap[d] = m["name"]
        parts = d.split(".")
        if len(parts) >= 2:
            dmap[".".join(parts[-2:])] = m["name"]
    return dmap

def match_domain(url, domain_map):
    try:
        host = urlparse(url).netloc.replace("www.", "").lower()
    except Exception:
        return None, None
    if host in domain_map:
        return domain_map[host], host
    parts = host.split(".")
    for i in range(len(parts)):
        sub = ".".join(parts[i:])
        if sub in domain_map:
            return domain_map[sub], sub
    return None, None

# ── Google News RSS ──────────────────────────────────
def google_news_rss(keyword):
    q = quote(keyword)
    url = (f"https://news.google.com/rss/search?"
           f"q={q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant")
    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True,
                        headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except Exception as e:
        print(f"  [!] RSS error: {e}")
        return []

    results = []
    try:
        root = ET.fromstring(resp.text)
        for item in root.iter("item"):
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pub_date = item.findtext("pubDate", "")
            source_name = item.findtext("source", "")
            source_el = item.find("source")
            source_url = source_el.get("url", "") if source_el is not None else ""

            date_str = ""
            if pub_date:
                try:
                    from email.utils import parsedate_to_datetime
                    dt = parsedate_to_datetime(pub_date)
                    date_str = dt.strftime("%Y-%m-%d")
                except Exception:
                    pass

            results.append({
                "title": title,
                "link": link,
                "source_url": source_url,
                "date": date_str,
                "source": source_name,
            })
    except Exception:
        pass
    return results

# ── DuckDuckGo broad search ─────────────────────────
def ddg_broad_search(keyword, max_results=30):
    if not DDGS:
        return []
    for attempt in range(3):
        try:
            with DDGS() as d:
                return list(d.text(keyword, region="tw-tzh", max_results=max_results))
        except Exception as e:
            if "0x304" in str(e) or "protocol" in str(e).lower():
                time.sleep(0.5)
                continue
            time.sleep(1)
    return []

# ── LLM verify ───────────────────────────────────────
def call_gemini_batch(prompt):
    if not GEMINI_API_KEY:
        return None
    try:
        resp = httpx.post(
            GEMINI_URL, params={"key": GEMINI_API_KEY},
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"temperature": 0, "maxOutputTokens": 8192}},
            timeout=60)
        resp.raise_for_status()
        text = (resp.json().get("candidates", [{}])[0]
                .get("content", {}).get("parts", [{}])[0].get("text", ""))
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
        return json.loads(text)
    except Exception as e:
        print(f"  [!] Gemini error: {e}")
        return None

def verify_candidates(task_name, candidates):
    BATCH = 20
    verified = []
    for batch_start in range(0, len(candidates), BATCH):
        batch = candidates[batch_start:batch_start + BATCH]
        items_text = ""
        for idx, c in enumerate(batch):
            items_text += (
                f"\n---\n#{idx+1}\n"
                f"標題: {c.get('標題', '')}\n"
                f"媒體: {c.get('媒體', '')}\n"
            )
        prompt = (
            f"你是新聞露出檢核員。以下是搜尋「{task_name}」（全家便利商店活動）的候選結果。\n"
            f"請判斷每則結果是否確實在報導全家便利商店的「{task_name}」。\n\n"
            f"判斷標準：\n"
            f"- 必須是在報導全家便利商店（FamilyMart）的「{task_name}」\n"
            f"- 只是提到部分字眼但主題不同→不相關\n"
            f"- 論壇閒聊、股票、其他產業→不相關\n"
            f"- 非新聞報導（如純關鍵字頁、搜尋頁）→不相關\n\n"
            f"候選列表：{items_text}\n\n"
            f"請回答 JSON array：\n"
            f'{{"id": 1, "relevant": true/false, "type": "原生"/"轉載"}}\n'
            f"只回 JSON array。"
        )
        verdicts = call_gemini_batch(prompt)
        time.sleep(0.3)
        if verdicts is None:
            for c in batch:
                verified.append(c)
            continue
        verdict_map = {v.get("id"): v for v in verdicts if v.get("id") is not None}
        for idx, c in enumerate(batch):
            v = verdict_map.get(idx + 1, {})
            if v.get("relevant", True):
                rtype = str(v.get("type", "原生"))
                c["原生/轉載"] = "轉載" if "轉載" in rtype else "原生"
                verified.append(c)
        p = sum(1 for v in (verdicts or []) if v.get("relevant"))
        print(f"    batch {batch_start+1}-{batch_start+len(batch)}: {p} pass")
    return verified

# ── Main ─────────────────────────────────────────────
def main():
    media_list = load_media_list()
    domain_map = build_domain_map(media_list)
    print(f"載入 {len(media_list)} 個媒體")

    month = "一月"
    seen_keys = set()
    all_candidates = []

    # ── Source 1: Load existing results ────────────────
    print(f"\n{'='*60}")
    print("Source 1: 載入現有結果...")
    existing_path = OUTPUT_BASE / month / "全部任務_combined.json"
    if existing_path.exists():
        data = json.loads(existing_path.read_text(encoding="utf-8"))
        for r in data.get("results", []):
            media = r.get("媒體", "")
            task = r.get("新聞", "")
            key = f"{media}|{task}"
            if key not in seen_keys:
                seen_keys.add(key)
                all_candidates.append(r)
    print(f"  已有: {len(all_candidates)} 筆")

    # ── Source 2: Google News RSS (expanded keywords) ──
    print(f"\n{'='*60}")
    print("Source 2: Google News RSS 擴充搜尋...")
    gnews_new = 0
    for task_name, cfg in TASKS_CONFIG.items():
        task_new = 0
        all_queries = list(cfg["keywords"])
        for frag in cfg.get("press_title_fragments", []):
            all_queries.append(frag)

        for kw in all_queries:
            articles = google_news_rss(kw)
            for a in articles:
                real_url = a.get("source_url", "") or a["link"]
                media_name, matched_domain = match_domain(real_url, domain_map)
                if not media_name:
                    continue
                key = f"{media_name}|{task_name}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                all_candidates.append({
                    "新聞": task_name,
                    "日期": a["date"],
                    "媒體": media_name,
                    "標題": a["title"].rsplit(" - ", 1)[0].strip(),
                    "連結": a["link"],
                    "原生/轉載": "原生",
                    "關鍵字": kw,
                    "來源": "GNews",
                })
                task_new += 1
            time.sleep(0.3)

        if task_new > 0:
            print(f"  [{task_name}] +{task_new}")
            gnews_new += task_new
    print(f"  Google News 新增: {gnews_new}")

    # ── Source 3: DDG broad search ─────────────────────
    print(f"\n{'='*60}")
    print("Source 3: DuckDuckGo 廣域搜尋...")
    ddg_new = 0
    for task_name, cfg in TASKS_CONFIG.items():
        task_new = 0
        for kw in cfg["keywords"][:3]:
            results = ddg_broad_search(kw, max_results=50)
            for r in results:
                url = r.get("href", "")
                title = r.get("title", "")
                if not url:
                    continue
                media_name, matched_domain = match_domain(url, domain_map)
                if not media_name:
                    continue
                key = f"{media_name}|{task_name}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                all_candidates.append({
                    "新聞": task_name,
                    "日期": "",
                    "媒體": media_name,
                    "標題": title,
                    "連結": url,
                    "原生/轉載": "原生",
                    "關鍵字": kw,
                    "來源": "DDG-broad",
                })
                task_new += 1
            time.sleep(1)

        if task_new > 0:
            print(f"  [{task_name}] +{task_new}")
            ddg_new += task_new
    print(f"  DDG 廣域新增: {ddg_new}")

    # ── Source 4: DDG press title search ───────────────
    print(f"\n{'='*60}")
    print("Source 4: DuckDuckGo 新聞稿標題搜尋...")
    title_new = 0
    for task_name, cfg in TASKS_CONFIG.items():
        task_new = 0
        for frag in cfg.get("press_title_fragments", []):
            results = ddg_broad_search(f'"{frag}"', max_results=30)
            for r in results:
                url = r.get("href", "")
                title = r.get("title", "")
                if not url:
                    continue
                media_name, matched_domain = match_domain(url, domain_map)
                if not media_name:
                    continue
                key = f"{media_name}|{task_name}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                all_candidates.append({
                    "新聞": task_name,
                    "日期": "",
                    "媒體": media_name,
                    "標題": title,
                    "連結": url,
                    "原生/轉載": "轉載",
                    "關鍵字": frag,
                    "來源": "DDG-title",
                })
                task_new += 1
            time.sleep(1)

        if task_new > 0:
            print(f"  [{task_name}] +{task_new}")
            title_new += task_new
    print(f"  標題搜尋新增: {title_new}")

    print(f"\n{'='*60}")
    print(f"合併後總計: {len(all_candidates)} 筆")

    # ── LLM verify new candidates only ─────────────────
    existing_count = len(data.get("results", [])) if existing_path.exists() else 0
    new_candidates = all_candidates[existing_count:]

    if new_candidates:
        print(f"\nLLM 驗證 {len(new_candidates)} 筆新候選...")
        by_task = {}
        for c in new_candidates:
            by_task.setdefault(c.get("新聞", "?"), []).append(c)

        verified_new = []
        for task_name, candidates in sorted(by_task.items()):
            print(f"\n  [{task_name}] {len(candidates)} 筆")
            v = verify_candidates(task_name, candidates)
            verified_new.extend(v)
            print(f"    → 通過: {len(v)}")

        final_results = all_candidates[:existing_count] + verified_new
    else:
        final_results = all_candidates
        print("\n沒有新候選需要驗證")

    # ── Save ───────────────────────────────────────────
    print(f"\n{'='*60}")
    output_data = {
        "title": "全部任務合併 v2",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "results": final_results,
        "summary": {
            "total": len(final_results),
            "tasks": len(TASKS_CONFIG),
        },
    }
    output_path = OUTPUT_BASE / month / "全部任務_combined.json"
    output_path.write_text(json.dumps(output_data, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"已儲存: {len(final_results)} 筆")

    # ── Export to Sheet ────────────────────────────────
    print(f"\n匯出到 Google Sheet...")
    export_to_sheet(final_results)

    # ── Summary ────────────────────────────────────────
    print(f"\n{'='*60}")
    from collections import Counter
    tc = Counter(r.get("新聞", "?") for r in final_results)
    media_set = set(r.get("媒體", "") for r in final_results)
    source_c = Counter(r.get("來源", "?") for r in final_results)
    print(f"最終結果: {len(final_results)} 筆, 命中 {len(media_set)} 個媒體")
    print(f"\n來源分佈:")
    for s, c in source_c.most_common():
        print(f"  {s}: {c}")
    print(f"\n各任務:")
    for t, c in sorted(tc.items()):
        print(f"  {t}: {c}")


def export_to_sheet(results):
    sys.path.insert(0, os.path.expanduser(
        "~/.openclaw/skills/google-sheets/scripts"))
    try:
        from sheets_tools import get_sheets_service
    except ImportError:
        print("  [!] Google Sheets 載入失敗")
        return

    SHEET_ID = "1hh6wOIny3CwPB4bIVUPV7mtXNijijE2jN-p8zVK9qcU"
    TAB = "Pandora掃描結果"

    service = get_sheets_service()
    meta = service.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    existing = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if TAB in existing:
        service.spreadsheets().values().clear(
            spreadsheetId=SHEET_ID, range=f"{TAB}!A:Z").execute()
    else:
        service.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID,
            body={"requests": [{"addSheet": {"properties": {"title": TAB}}}]}).execute()

    header = ["任務", "日期", "媒體", "標題", "連結", "原生/轉載", "關鍵字", "來源"]
    rows = [[r.get("新聞", ""), r.get("日期", ""), r.get("媒體", ""),
             r.get("標題", ""), r.get("連結", ""), r.get("原生/轉載", ""),
             r.get("關鍵字", ""), r.get("來源", "")] for r in results]

    service.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range=f"{TAB}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [header] + rows}).execute()

    print(f"  已寫入 {len(rows)} 筆到 [{TAB}]")
    print(f"  https://docs.google.com/spreadsheets/d/{SHEET_ID}")


if __name__ == "__main__":
    main()
