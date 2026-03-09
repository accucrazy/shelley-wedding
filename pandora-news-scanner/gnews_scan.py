# -*- coding: utf-8 -*-
"""
Google News RSS 快速全掃：搜所有任務關鍵字 → 比對 345 媒體清單 → 合併 DDG 結果 → LLM 驗證 → 輸出
"""
import json, os, sys, time, re, glob
from datetime import datetime
from urllib.parse import urlparse, quote
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.expanduser(
    "~/.openclaw/skills/pandora-news/venv/lib/python3.9/site-packages"))
import httpx

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
        "keywords": ["全家草莓季", "全家 ASAMIMICHAN", "全家 草莓霜淇淋"],
        "month": "一月"},
    "全家UCC咖啡": {
        "keywords": ["全家 UCC咖啡", "全家 阿里山極選", "全家 Let's Café 阿里山"],
        "month": "一月"},
    "全家開運鮮食": {
        "keywords": ["全家 開運鮮食", "全家 紅運烏魚子", "全家 蘭州拉麵"],
        "month": "一月"},
    "全家年菜預購": {
        "keywords": ["全家 年菜預購", "全家 2026金馬年菜"],
        "month": "一月"},
    "全家蜷川實花": {
        "keywords": ["全家 蜷川實花", "全家 蜷川實花展"],
        "month": "一月"},
    "全家特力屋": {
        "keywords": ["全家 特力屋", "全家 居家微整型"],
        "month": "一月"},
    "全家溏心蛋": {
        "keywords": ["全家 溏心蛋", "全家 日式溏心蛋"],
        "month": "一月"},
    "全家高山茶": {
        "keywords": ["全家 高山茶", "全家 蘭韻梨山烏龍"],
        "month": "一月"},
    "全家超人力霸王": {
        "keywords": ["全家 超人力霸王", "全家 高雄冬日遊樂園"],
        "month": "一月"},
    "全家寒流抗寒": {
        "keywords": ["全家 寒流", "全家 抗寒"],
        "month": "一月"},
    "全家伴手禮": {
        "keywords": ["全家 陳耀訓", "全家 紅土蛋黃酥"],
        "month": "一月"},
}

# ── Load media list ──────────────────────────────────
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
    """Build domain -> media name mapping for fast lookup."""
    dmap = {}
    for m in media_list:
        d = m["domain"].replace("www.", "")
        dmap[d] = m["name"]
        parts = d.split(".")
        if len(parts) >= 2:
            dmap[".".join(parts[-2:])] = m["name"]
    return dmap

def match_domain(url, domain_map):
    """Check if URL belongs to any media in our list."""
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
    """Search Google News RSS, return list of articles."""
    q = quote(keyword)
    url = (f"https://news.google.com/rss/search?"
           f"q={q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant")
    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True,
                        headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except Exception as e:
        print(f"  [!] RSS error for '{keyword}': {e}")
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
    except Exception as e:
        print(f"  [!] XML parse error: {e}")

    return results

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
    """Batch LLM verify for relevance only (no date filtering)."""
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
                if "轉載" in rtype:
                    c["原生/轉載"] = "轉載"
                else:
                    c["原生/轉載"] = "原生"
                verified.append(c)

        kept = sum(1 for c_ in batch
                   if verdict_map.get(batch.index(c_) + 1 if c_ in batch else -1, {}).get("relevant", True))
        print(f"    batch {batch_start+1}-{batch_start+len(batch)}: "
              f"{len([v for v in verdicts or [] if v.get('relevant')])} pass")

    return verified

# ── Load existing DDG results ────────────────────────
def load_existing_ddg(month):
    """Load all raw_candidates that passed LLM from existing DDG scan JSON files."""
    d = OUTPUT_BASE / month
    existing = []
    seen_urls = set()

    for fpath in sorted(d.glob("*_2026-*.json")):
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
        except Exception:
            continue

        task_name = fpath.name.split("_2026")[0]

        for c in data.get("raw_candidates", []):
            url = c.get("連結", "")
            media = c.get("媒體", "")
            domain = c.get("domain", "")
            dedup_key = f"{domain}|{task_name}"
            if dedup_key in seen_urls:
                continue
            if c.get("llm_result") == "pass":
                seen_urls.add(dedup_key)
                existing.append({
                    "新聞": task_name,
                    "日期": "",
                    "媒體": media,
                    "標題": c.get("標題", ""),
                    "連結": url,
                    "原生/轉載": "原生",
                    "關鍵字": c.get("關鍵字", ""),
                    "來源": "DDG",
                })

    return existing, seen_urls

# ── Main ─────────────────────────────────────────────
def main():
    media_list = load_media_list()
    domain_map = build_domain_map(media_list)
    print(f"載入 {len(media_list)} 個媒體, domain map 大小: {len(domain_map)}")

    month = "一月"

    # Step 1: Load existing DDG results
    print(f"\n{'='*60}")
    print(f"載入現有 DDG 結果...")
    ddg_results, seen_urls = load_existing_ddg(month)
    print(f"  DDG 已有: {len(ddg_results)} 筆")

    # Step 2: Google News RSS scan
    print(f"\n{'='*60}")
    print(f"Google News RSS 掃描 {len(TASKS_CONFIG)} 個任務...")

    gnews_candidates = []
    for task_name, cfg in TASKS_CONFIG.items():
        print(f"\n  [{task_name}]")
        task_hits = 0
        for kw in cfg["keywords"]:
            articles = google_news_rss(kw)
            print(f"    '{kw}' → {len(articles)} 篇")

            for a in articles:
                real_url = a.get("source_url", "") or a["link"]
                media_name, matched_domain = match_domain(real_url, domain_map)
                if not media_name:
                    continue

                dedup_key = f"{matched_domain}|{task_name}"
                if dedup_key in seen_urls:
                    continue
                seen_urls.add(dedup_key)

                gnews_candidates.append({
                    "新聞": task_name,
                    "日期": a["date"],
                    "媒體": media_name,
                    "標題": a["title"].rsplit(" - ", 1)[0].strip(),
                    "連結": a["link"],
                    "原生/轉載": "原生",
                    "關鍵字": kw,
                    "來源": "GNews",
                })
                task_hits += 1

            time.sleep(0.5)

        print(f"    → 新增 {task_hits} 筆（命中媒體清單）")

    print(f"\n  Google News 總新增: {len(gnews_candidates)} 筆")

    # Step 3: Merge all
    print(f"\n{'='*60}")
    all_candidates = ddg_results + gnews_candidates
    print(f"合併後總計: {len(all_candidates)} 筆")

    # Step 4: LLM verify (relevance only, no date filter)
    print(f"\n{'='*60}")
    print(f"LLM 驗證相關性...")

    by_task = {}
    for c in all_candidates:
        t = c.get("新聞", "unknown")
        by_task.setdefault(t, []).append(c)

    final_results = []
    for task_name, candidates in sorted(by_task.items()):
        print(f"\n  [{task_name}] {len(candidates)} 筆待驗證")
        verified = verify_candidates(task_name, candidates)
        final_results.extend(verified)
        print(f"    → 通過: {len(verified)} 筆")

    # Step 5: Save combined JSON
    print(f"\n{'='*60}")
    output_path = OUTPUT_BASE / month / "全部任務_combined.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_data = {
        "title": "全部任務合併",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "results": final_results,
        "summary": {
            "total": len(final_results),
            "tasks": len(by_task),
            "sources": {"DDG": len(ddg_results), "GNews": len(gnews_candidates)},
        },
    }
    output_path.write_text(json.dumps(output_data, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"已儲存: {output_path}")
    print(f"總結果: {len(final_results)} 筆")

    # Step 6: Export to Google Sheet
    print(f"\n{'='*60}")
    print(f"匯出到 Google Sheet...")
    export_to_sheet(final_results)

    # Summary
    print(f"\n{'='*60}")
    print(f"完成！")
    task_summary = {}
    for r in final_results:
        t = r.get("新聞", "?")
        task_summary[t] = task_summary.get(t, 0) + 1
    for t, c in sorted(task_summary.items()):
        print(f"  {t}: {c} 筆")
    print(f"  合計: {len(final_results)} 筆")


def export_to_sheet(results):
    sys.path.insert(0, os.path.expanduser(
        "~/.openclaw/skills/google-sheets/scripts"))
    try:
        from sheets_tools import get_sheets_service
    except ImportError:
        print("  [!] Google Sheets 模組載入失敗")
        return

    SHEET_ID = "1hh6wOIny3CwPB4bIVUPV7mtXNijijE2jN-p8zVK9qcU"
    TAB_NAME = "Pandora掃描結果"

    service = get_sheets_service()

    meta = service.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    existing = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if TAB_NAME in existing:
        service.spreadsheets().values().clear(
            spreadsheetId=SHEET_ID, range=f"{TAB_NAME}!A:Z").execute()
    else:
        service.spreadsheets().batchUpdate(
            spreadsheetId=SHEET_ID,
            body={"requests": [{"addSheet": {"properties": {"title": TAB_NAME}}}]}
        ).execute()

    header = ["任務", "日期", "媒體", "標題", "連結", "原生/轉載", "關鍵字", "來源"]
    rows = []
    for r in results:
        rows.append([
            r.get("新聞", ""), r.get("日期", ""), r.get("媒體", ""),
            r.get("標題", ""), r.get("連結", ""), r.get("原生/轉載", ""),
            r.get("關鍵字", ""), r.get("來源", ""),
        ])

    service.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range=f"{TAB_NAME}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [header] + rows},
    ).execute()

    print(f"  已寫入 {len(rows)} 筆到 [{TAB_NAME}]")
    print(f"  https://docs.google.com/spreadsheets/d/{SHEET_ID}")


if __name__ == "__main__":
    main()
