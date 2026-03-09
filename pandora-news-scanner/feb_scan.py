# -*- coding: utf-8 -*-
"""
二月全家新聞掃描：Google News RSS + DDG per-domain + LLM 驗證
14 個任務，345 個媒體，三階段 pipeline。
"""
import json, os, sys, time, re, signal
from datetime import datetime
from urllib.parse import urlparse, quote_plus, urlencode
from xml.etree import ElementTree
from pathlib import Path
from collections import Counter

sys.path.insert(0, os.path.expanduser(
    "~/.openclaw/skills/pandora-news/venv/lib/python3.9/site-packages"))
import httpx
from ddgs import DDGS

if sys.stdout:
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(os.path.expanduser(
    "~/.openclaw/workspace/newscollect/Pandora News IO 0226"))
MEDIA_LIST = BASE_DIR / "1-媒體清單" / "news-media-list.md"
OUTPUT_DIR = BASE_DIR / "3-Pandora News io" / "二月"
COMBINED_JSON = OUTPUT_DIR / "全部任務_combined.json"

GEMINI_KEY = ""
GEMINI_URL = ""

_shutdown = False
def _sig(s, f):
    global _shutdown; _shutdown = True
    print("\n[!] 收到停止信號，安全退出中...", flush=True)
signal.signal(signal.SIGTERM, _sig)
signal.signal(signal.SIGINT, _sig)

# ─── 14 個二月任務 & 關鍵字 ───

TASKS = {
    "全家助你擺脫收假症候群": {
        "keywords": [
            "全家 收假症候群", "全家 開工優惠", "全家 Let's Café 優惠",
            "全家 好神刮刮卡", "全家 開工 補元氣", "全家 茶葉蛋優惠",
            "全家便利商店 收假", "全家 開工日",
        ],
    },
    "Fami!ce x 哆啦A夢": {
        "keywords": [
            "全家 哆啦A夢", "全家 Fami!ce 哆啦A夢", "全家 紅豆牛奶霜淇淋",
            "全家 哆啦A夢 霜淇淋", "FamilyMart 哆啦A夢", "全家 Doraemon",
            "全家 FamiPets", "全家 寵物", "全家 貓之日",
            "全家 哆啦A夢 寵物頭套", "全家 萌寵",
        ],
    },
    "全家草莓季": {
        "keywords": [
            "全家草莓季", "全家 草莓", "全家便利商店 草莓季",
            "FamilyMart 草莓季", "全家 minimore 草莓",
            "全家 Cona's 草莓", "全家 草莓花束", "全家 草莓千層",
            "全家 草莓 情人節", "全家 Let's Café 草莓",
        ],
    },
    "年後甩油動起來": {
        "keywords": [
            "全家 甩油", "全家 健康志向鮮食", "全家 年後甩油",
            "全家 蛋白質", "全家 履歷地瓜沙拉", "全家 蔬滿盒",
            "全家便利商店 健康鮮食", "全家 雞胸肉",
        ],
    },
    "抗寒三寶優惠出爐": {
        "keywords": [
            "全家 抗寒三寶", "全家 寒流 優惠", "全家 熱飲 熱食",
            "全家 補班 咖啡", "全家 抗寒", "全家 暖心織品",
            "全家便利商店 寒流", "全家 茶葉蛋 99元",
        ],
    },
    "全家迎開學": {
        "keywords": [
            "全家 開學", "全家 迎開學", "全家 沈早 三明治",
            "全家 海鹽花生可可", "全家 湯圓", "全家 元宵",
            "全家便利商店 開學", "全家 金飯糰",
        ],
    },
    "情人節空運玫瑰": {
        "keywords": [
            "全家 情人節", "全家 空運玫瑰", "全家 情人節 玫瑰",
            "全家 卡布奇諾 19元", "全家 情人節 霜淇淋",
            "全家便利商店 情人節", "FamilyMart 情人節",
            "全家 暖心飲品 情人節",
        ],
    },
    "全家應援中華隊": {
        "keywords": [
            "全家 中華隊", "全家 應援 中華隊", "全家 WBC",
            "全家 世界棒球經典賽", "全家 棒球 經典賽",
            "全家 應援 棒球", "FamilyMart 中華隊",
            "全家 FamiNow 棒球",
        ],
    },
    "化身不打烊寵物店": {
        "keywords": [
            "全家 FamiPets", "全家 寵物店", "全家 不打烊寵物店",
            "全家 寵物品牌", "全家 貓砂", "全家 寵物商品",
            "全家便利商店 寵物", "FamilyMart 寵物",
            "全家 毛孩", "全家 寵物用品",
        ],
    },
    "春遊賞櫻趣": {
        "keywords": [
            "全家 賞櫻", "全家 春遊賞櫻", "全家 櫻花",
            "全家便利商店 賞櫻", "全家 粉色霜淇淋",
            "全家 賞櫻 出遊", "FamilyMart 櫻花",
            "全家 八德 櫻花",
        ],
    },
    "就一起挺中華隊": {
        "keywords": [
            "全家 挺中華隊", "全家 917元 應援", "全家 中華隊 簽名球",
            "全家 經典賽 資格賽", "全家 棒球 周邊",
            "全家便利商店 中華隊", "全家 WBC 2025",
        ],
    },
    "世界番薯日": {
        "keywords": [
            "全家 番薯日", "全家 世界番薯日", "全家 夯番薯",
            "全家便利商店 番薯", "全家 番薯 優惠",
            "全家 米其林 請客樓", "全家 開學 茶葉蛋",
        ],
    },
    "228優惠": {
        "keywords": [
            "全家 228", "全家 228連假", "全家 228優惠",
            "全家 深夜食堂", "全家 霜淇淋 188",
            "全家 康康五 買一送一", "全家便利商店 228",
            "全家 連假 優惠",
        ],
    },
    "日落優惠": {
        "keywords": [
            "全家 日落優惠", "全家 齋戒月", "全家 清真",
            "全家 穆斯林", "全家 椰棗", "全家 椰棗蜜拿鐵",
            "全家便利商店 齋戒月", "FamilyMart 清真",
            "全家 清真友善",
        ],
    },
}

AGGREGATOR_DOMAINS = {
    "today.line.me", "tw.news.yahoo.com", "msn.com", "news.pchome.com.tw"}


def load_media_list():
    content = MEDIA_LIST.read_text(encoding="utf-8")
    media = []
    domain_map = {}
    for line in content.split("\n"):
        if "|" not in line or "---" in line or "媒體名稱" in line:
            continue
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) >= 2 and "." in parts[1]:
            media.append({"name": parts[0], "domain": parts[1]})
            domain_map[parts[1]] = parts[0]
    return media, domain_map


def init_gemini():
    global GEMINI_KEY, GEMINI_URL
    env_file = os.path.expanduser("~/.openclaw/skills/pandora-news/.env")
    if os.path.exists(env_file):
        for line in open(env_file):
            if line.startswith("GOOGLE_API_KEY="):
                GEMINI_KEY = line.strip().split("=", 1)[1]
                GEMINI_URL = (
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"gemini-2.0-flash:generateContent?key={GEMINI_KEY}")
                return
    GEMINI_KEY = os.environ.get("GOOGLE_API_KEY", "")
    if GEMINI_KEY:
        GEMINI_URL = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={GEMINI_KEY}")


def call_gemini(prompt, retries=3):
    for attempt in range(retries):
        try:
            resp = httpx.post(
                GEMINI_URL,
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=30)
            if resp.status_code == 200:
                body = resp.json()
                return body["candidates"][0]["content"]["parts"][0]["text"].strip()
            elif resp.status_code == 429:
                time.sleep(5 * (attempt + 1))
        except Exception:
            time.sleep(2)
    return None


# ─── Phase 1: Google News RSS ───

def google_news_rss(keyword):
    url = (f"https://news.google.com/rss/search?"
           f"q={quote_plus(keyword)}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant")
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
            source_url = source.get("url", "") if source is not None else ""
            items.append({
                "title": title, "link": link,
                "pub_date": pub_date, "source_url": source_url,
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


def phase1_gnews(domain_map, existing_keys, results):
    """Google News RSS 多關鍵字搜尋"""
    print("\n" + "=" * 60)
    print("Phase 1: Google News RSS 多關鍵字搜尋")
    print("=" * 60)
    total_new = 0

    for task_name, config in TASKS.items():
        if _shutdown:
            break
        keywords = config["keywords"]
        print(f"\n[{task_name}] {len(keywords)} 個關鍵字...")
        task_new = 0

        for kw in keywords:
            items = google_news_rss(kw)
            for item in items:
                domain, name = match_domain(item["source_url"], domain_map)
                if not name:
                    continue
                key = f"{name}|{task_name}"
                if key in existing_keys:
                    continue
                existing_keys.add(key)
                results.append({
                    "新聞": task_name, "日期": item.get("pub_date", ""),
                    "媒體": name, "標題": item["title"],
                    "連結": item["link"], "原生/轉載": "原生",
                    "關鍵字": kw, "來源": "GNews-RSS",
                })
                task_new += 1
                total_new += 1
            time.sleep(0.5)

        print(f"  → +{task_new}")

    print(f"\nPhase 1 完成: +{total_new} 筆")
    return total_new


# ─── Phase 2: DDG per-domain ───

def ddg_search(q, max_results=3):
    for _ in range(2):
        try:
            with DDGS() as d:
                return list(d.text(q, region="tw-tzh", max_results=max_results))
        except Exception:
            time.sleep(1)
    return []


def phase2_ddg_domain(media_list, existing_keys, results):
    """DDG per-domain site: 搜尋"""
    print("\n" + "=" * 60)
    print("Phase 2: DDG per-domain 搜尋")
    print("=" * 60)
    total_new = 0

    for task_name, config in TASKS.items():
        if _shutdown:
            break
        keywords = config["keywords"]
        kw_main = keywords[0]
        print(f"\n[{task_name}] keyword: {kw_main}")
        task_new = 0

        for i, m in enumerate(media_list):
            if _shutdown:
                break
            domain = m["domain"]
            name = m["name"]
            key = f"{name}|{task_name}"
            if key in existing_keys:
                continue

            if domain in AGGREGATOR_DOMAINS:
                q = f"{kw_main} {name}"
            else:
                q = f"{kw_main} site:{domain}"

            search_results = ddg_search(q, max_results=3)
            for r in search_results:
                url = r.get("href", "")
                title = r.get("title", "")
                if not url:
                    continue
                rd = urlparse(url).netloc.replace("www.", "")
                if domain not in rd and domain not in AGGREGATOR_DOMAINS:
                    continue
                existing_keys.add(key)
                results.append({
                    "新聞": task_name, "日期": "", "媒體": name,
                    "標題": title, "連結": url,
                    "原生/轉載": "原生", "關鍵字": kw_main,
                    "來源": "DDG-domain",
                })
                task_new += 1
                total_new += 1
                break

            if (i + 1) % 50 == 0:
                print(f"  [{i+1}/{len(media_list)}] +{task_new}")

            time.sleep(0.8)

        print(f"  → {task_name}: +{task_new}")
        save_combined(results)

    print(f"\nPhase 2 完成: +{total_new} 筆")
    return total_new


# ─── Phase 3: LLM 驗證 ───

def phase3_llm_verify(results):
    """LLM 批次驗證，篩除不相關結果"""
    print("\n" + "=" * 60)
    print("Phase 3: LLM 驗證")
    print("=" * 60)

    unverified = [(i, r) for i, r in enumerate(results)
                  if "llm_verified" not in r]
    print(f"未驗證: {len(unverified)} / {len(results)}")

    if not unverified:
        return

    by_task = {}
    for idx, r in unverified:
        by_task.setdefault(r.get("新聞", ""), []).append((idx, r))

    BATCH = 25
    total_pass = 0
    total_fail = 0

    for task_name, items in by_task.items():
        if _shutdown:
            break
        print(f"\n[{task_name}] 驗證 {len(items)} 筆...")
        task_pass = 0

        for batch_start in range(0, len(items), BATCH):
            if _shutdown:
                break
            batch = items[batch_start:batch_start + BATCH]
            items_text = ""
            for pos, (_, r) in enumerate(batch, 1):
                items_text += (
                    f"{pos}. 媒體={r.get('媒體','')}, "
                    f"標題={r.get('標題','')}, "
                    f"連結={r.get('連結','')}\n")

            prompt = (
                f"以下是搜尋「{task_name}」（全家便利商店活動）的結果。\n"
                f"請判斷每一條是否真的與全家便利商店的「{task_name}」相關。\n\n"
                f"判斷標準：\n"
                f"- 必須是與全家便利商店的「{task_name}」活動直接相關 → pass\n"
                f"- 與全家無關（其他通路、一般資訊）→ fail\n"
                f"- 網站首頁、目錄頁、404 → fail\n\n"
                f"候選列表：\n{items_text}\n"
                f"請只回覆 JSON array：\n"
                f'[{{"id": 1, "result": "pass"}}, {{"id": 2, "result": "fail"}}]\n'
                f"只回 JSON array。"
            )

            response = call_gemini(prompt)
            verdicts = {}
            if response:
                try:
                    clean = response.strip()
                    if clean.startswith("```"):
                        clean = re.sub(r"^```\w*\n?", "", clean)
                        clean = re.sub(r"\n?```$", "", clean)
                    arr = json.loads(clean)
                    verdicts = {item["id"]: item["result"] for item in arr}
                except Exception:
                    pass

            for pos, (orig_idx, r) in enumerate(batch, 1):
                v = verdicts.get(pos, "pass")
                results[orig_idx]["llm_verified"] = v
                if v == "pass":
                    task_pass += 1
                    total_pass += 1
                else:
                    total_fail += 1

            time.sleep(1)

        print(f"  → {task_name}: {task_pass} pass / {len(items)-task_pass} fail")

    print(f"\nPhase 3 完成: {total_pass} pass, {total_fail} fail")


# ─── 存檔 & 匯出 ───

def save_combined(results):
    data = {
        "summary": {
            "month": "二月",
            "total": len(results),
            "tasks": len(TASKS),
            "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        },
        "results": results,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    COMBINED_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def export_sheet(results, only_pass=False):
    if only_pass:
        results = [r for r in results if r.get("llm_verified", "pass") == "pass"]

    sys.path.insert(0, os.path.expanduser(
        "~/.openclaw/skills/google-sheets/scripts"))
    try:
        from sheets_tools import get_sheets_service
        SHEET_ID = "1hh6wOIny3CwPB4bIVUPV7mtXNijijE2jN-p8zVK9qcU"
        TAB = "二月掃描結果"
        service = get_sheets_service()

        meta = service.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
        existing_tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]
        if TAB not in existing_tabs:
            service.spreadsheets().batchUpdate(
                spreadsheetId=SHEET_ID,
                body={"requests": [{"addSheet": {"properties": {"title": TAB}}}]}
            ).execute()
        else:
            service.spreadsheets().values().clear(
                spreadsheetId=SHEET_ID, range=f"{TAB}!A:Z").execute()

        header = ["任務", "日期", "媒體", "標題", "連結", "原生/轉載", "關鍵字", "來源", "LLM"]
        rows = [[
            r.get("新聞", ""), r.get("日期", ""), r.get("媒體", ""),
            r.get("標題", ""), r.get("連結", ""), r.get("原生/轉載", ""),
            r.get("關鍵字", ""), r.get("來源", ""),
            r.get("llm_verified", ""),
        ] for r in results]

        service.spreadsheets().values().update(
            spreadsheetId=SHEET_ID, range=f"{TAB}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": [header] + rows}).execute()
        print(f"Sheet '{TAB}' 已更新: {len(rows)} 筆")
        print(f"https://docs.google.com/spreadsheets/d/{SHEET_ID}")
    except Exception as e:
        print(f"[!] Sheet 更新失敗: {e}")


# ─── Main ───

def main():
    init_gemini()
    media_list, domain_map = load_media_list()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if COMBINED_JSON.exists():
        data = json.loads(COMBINED_JSON.read_text(encoding="utf-8"))
        results = data.get("results", [])
        print(f"載入既有結果: {len(results)} 筆")
    else:
        results = []

    existing_keys = set(f"{r.get('媒體','')}|{r.get('新聞','')}" for r in results)

    # Phase 1: Google News RSS
    phase1_gnews(domain_map, existing_keys, results)
    save_combined(results)
    print(f"\n目前總計: {len(results)} 筆")

    # Phase 2: DDG per-domain
    phase2_ddg_domain(media_list, existing_keys, results)
    save_combined(results)
    print(f"\n目前總計: {len(results)} 筆")

    # Phase 3: LLM 驗證
    if GEMINI_URL:
        phase3_llm_verify(results)
        save_combined(results)

    # 統計
    passed = [r for r in results if r.get("llm_verified", "pass") == "pass"]
    failed = [r for r in results if r.get("llm_verified") == "fail"]
    tc = Counter(r.get("新聞", "") for r in passed)
    mc = len(set(r.get("媒體", "") for r in passed))

    print(f"\n{'='*60}")
    print(f"最終結果: {len(passed)} 筆 pass, {len(failed)} 筆 fail")
    print(f"涵蓋: {mc} 個媒體")
    print(f"\n各任務:")
    for t, c in sorted(tc.items()):
        print(f"  {t}: {c}")

    # 匯出
    export_sheet(results, only_pass=False)


if __name__ == "__main__":
    main()
