# -*- coding: utf-8 -*-
"""
Pandora Batch Scanner v3 — 兩階段掃描
  Phase 1 (scan):  DDG 搜尋所有媒體，只做 domain 比對，收集所有候選
  Phase 2 (verify): 一口氣用 Gemini Flash 過濾 + 判斷原生/轉載

用法:
    python pandora_batch_scanner.py scan   --month 一月        # 掃描
    python pandora_batch_scanner.py verify --month 一月        # LLM 過濾
    python pandora_batch_scanner.py run    --month 一月        # 掃描+過濾+報表
    python pandora_batch_scanner.py status                     # 查進度
    python pandora_batch_scanner.py report --month 一月        # 產報表
"""

import json, os, sys, time, argparse, signal
from datetime import datetime
from urllib.parse import urlparse
from pathlib import Path

try:
    import httpx
except ImportError:
    httpx = None

if sys.stdout:
    sys.stdout.reconfigure(encoding='utf-8')

# ── Paths ──────────────────────────────────────────────
BASE_DIR = Path(os.path.expanduser(
    "~/.openclaw/workspace/newscollect/Pandora News IO 0226"))
MEDIA_LIST = BASE_DIR / "1-媒體清單" / "news-media-list.md"
OUTPUT_BASE = BASE_DIR / "3-Pandora News io"
CANVAS_PUBLIC = Path(os.path.expanduser(
    "~/.openclaw/workspace/canvas/public"))
LOG_FILE = Path(os.path.expanduser(
    "~/.openclaw/workspace/pandora_scanner.log"))

SEARCH_DELAY = 1.5
SAVE_EVERY = 5
DDG_MAX_RETRIES = 5

AGGREGATOR_DOMAINS = {
    "today.line.me", "tw.news.yahoo.com", "msn.com", "news.pchome.com.tw"}

# ── Gemini ─────────────────────────────────────────────
def _load_api_key():
    p = Path(os.path.expanduser("~/.openclaw/.env"))
    if p.exists():
        for line in p.read_text().splitlines():
            if line.startswith("GOOGLE_API_KEY="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("GOOGLE_API_KEY", "")

GEMINI_API_KEY = _load_api_key()
GEMINI_URL = ("https://generativelanguage.googleapis.com/v1beta"
              "/models/gemini-2.0-flash:generateContent")

# ── Tasks ──────────────────────────────────────────────
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

# ── Graceful shutdown ──────────────────────────────────
_shutdown = False
def _sig(s, f):
    global _shutdown; _shutdown = True
    log("收到停止信號，安全退出中...")
signal.signal(signal.SIGTERM, _sig)
signal.signal(signal.SIGINT, _sig)

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except Exception:
        pass

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


# ═══════════════════════════════════════════════════════
# PHASE 1: DDG SCAN — collect raw candidates
# ═══════════════════════════════════════════════════════

def ddg_search(query):
    """DuckDuckGo search with TLS retry."""
    from ddgs import DDGS
    for _ in range(DDG_MAX_RETRIES):
        try:
            with DDGS() as d:
                return list(d.text(query, region="tw-tzh", max_results=5))
        except Exception as e:
            err = str(e)
            if "protocol" in err.lower() or "0x304" in err:
                time.sleep(0.3)
                continue
            if "429" in err or "ratelimit" in err.lower():
                time.sleep(10)
                continue
            time.sleep(1)
    return []


def scan_task(task_name, config, media_list, resume=True):
    """Phase 1: search all media, save raw candidates."""
    global _shutdown
    keywords = config["keywords"]
    month = config["month"]

    data, json_path = _load_json(task_name, month, keywords)
    data["progress"]["total"] = len(media_list)

    start = 0
    if resume and data["progress"].get("last_media_index", -1) >= 0:
        start = data["progress"]["last_media_index"] + 1
        if start > 0:
            log(f"  從第 {start+1}/{len(media_list)} 繼續")

    if start >= len(media_list):
        log(f"  [{task_name}] Phase 1 已完成")
        return data

    seen_domains = {urlparse(r.get("連結","")).netloc.replace("www.","")
                    for r in data.get("raw_candidates", [])}

    new_hits = 0
    if "raw_candidates" not in data:
        data["raw_candidates"] = []

    log(f"  [{task_name}] Phase 1: DDG 搜尋 ({start+1}→{len(media_list)})")

    for i in range(start, len(media_list)):
        if _shutdown:
            data["progress"]["status"] = "已中斷"
            _save(data, json_path)
            return data

        m = media_list[i]
        domain, name = m["domain"], m["name"]
        data["progress"]["last_media_index"] = i
        data["progress"]["completed"] = i + 1

        if domain in seen_domains:
            continue

        for kw in keywords:
            q = (f"{kw} {name}" if domain in AGGREGATOR_DOMAINS
                 else f"{kw} site:{domain}")
            results = ddg_search(q)

            for r in results:
                url = r.get("href", "")
                title = r.get("title", "")
                if not url or not title:
                    continue
                rd = urlparse(url).netloc.replace("www.", "")
                if domain not in rd:
                    continue
                data["raw_candidates"].append({
                    "媒體": name, "domain": domain,
                    "標題": title, "連結": url,
                    "snippet": r.get("body", ""),
                    "關鍵字": kw, "verified": False,
                })
                seen_domains.add(domain)
                new_hits += 1
                log(f"    [{i+1}/{len(media_list)}] +{name}: {title[:45]}")
                break
            if domain in seen_domains:
                break
            time.sleep(SEARCH_DELAY)

        if (i+1) % 30 == 0 and domain not in seen_domains:
            log(f"    [{i+1}/{len(media_list)}] ... (候選: {len(data['raw_candidates'])})")
        if (i+1) % SAVE_EVERY == 0:
            _save(data, json_path)

    data["progress"]["status"] = "scan_done"
    _save(data, json_path)
    log(f"  [{task_name}] Phase 1 完成: {len(data['raw_candidates'])} 候選 (+{new_hits})")
    return data


# ═══════════════════════════════════════════════════════
# PHASE 2: LLM VERIFY — batch filter with Gemini
# ═══════════════════════════════════════════════════════

def verify_task(task_name, config):
    """Phase 2: batch-verify raw candidates with LLM."""
    month = config["month"]
    data, json_path = _load_json(task_name, month, config["keywords"])

    candidates = data.get("raw_candidates", [])
    unverified = [c for c in candidates if not c.get("verified")]

    if not unverified:
        log(f"  [{task_name}] 無待驗證候選")
        return data

    log(f"  [{task_name}] Phase 2: LLM 驗證 {len(unverified)} 筆候選")

    BATCH = 15
    verified_results = data.get("results", [])
    passed = 0
    rejected = 0

    for batch_start in range(0, len(unverified), BATCH):
        batch = unverified[batch_start:batch_start+BATCH]

        items_text = ""
        for idx, c in enumerate(batch):
            items_text += (
                f"\n---\n#{idx+1}\n"
                f"標題: {c['標題']}\n"
                f"媒體: {c['媒體']}\n"
                f"摘要: {c['snippet'][:200]}\n"
            )

        prompt = (
            f"你是新聞露出檢核員。以下是搜尋「{task_name}」（全家便利商店活動）的候選結果。\n"
            f"請逐一判斷每則結果是否確實在報導全家便利商店的「{task_name}」活動/產品。\n\n"
            f"判斷標準：\n"
            f"- 必須是在報導全家便利商店（FamilyMart）的「{task_name}」\n"
            f"- 只是提到部分字眼但主題不同→不相關\n"
            f"- 論壇閒聊、股票、其他產業→不相關\n\n"
            f"候選列表：{items_text}\n\n"
            f"請回答 JSON array，每個元素格式：\n"
            f'{{"id": 1, "relevant": true/false, "type": "原生"/"轉載"}}\n'
            f"只回 JSON array，不要其他文字。"
        )

        verdicts = _call_gemini_batch(prompt)

        if verdicts is None:
            log(f"    LLM batch 失敗，跳過此批次")
            for c in batch:
                c["verified"] = True
                c["llm_result"] = "error"
            continue

        verdict_map = {}
        for v in verdicts:
            vid = v.get("id")
            if vid is not None:
                verdict_map[vid] = v

        for idx, c in enumerate(batch):
            c["verified"] = True
            v = verdict_map.get(idx + 1, {})
            if v.get("relevant", False):
                c["llm_result"] = "pass"
                rtype = v.get("type", "原生")
                if "轉載" in str(rtype):
                    rtype = "轉載"
                elif "改寫" in str(rtype):
                    rtype = "改寫"
                else:
                    rtype = "原生"
                verified_results.append({
                    "新聞": task_name,
                    "日期": datetime.now().strftime("%Y-%m-%d"),
                    "關鍵字": c["關鍵字"],
                    "標題": c["標題"],
                    "媒體": c["媒體"],
                    "連結": c["連結"],
                    "原生/轉載": rtype,
                })
                passed += 1
            else:
                c["llm_result"] = "reject"
                rejected += 1

        log(f"    batch {batch_start+1}-{batch_start+len(batch)}: "
            f"+{sum(1 for c in batch if c.get('llm_result')=='pass')} pass, "
            f"{sum(1 for c in batch if c.get('llm_result')=='reject')} reject")

    data["results"] = verified_results
    data["summary"] = {
        "total": len(verified_results),
        "original": sum(1 for r in verified_results if r.get("原生/轉載") == "原生"),
        "repost": sum(1 for r in verified_results if r.get("原生/轉載") == "轉載"),
    }
    data["progress"]["status"] = "verified"
    _save(data, json_path)
    log(f"  [{task_name}] Phase 2 完成: {passed} 通過, {rejected} 過濾")
    return data


def _call_gemini_batch(prompt):
    """Call Gemini and parse JSON array response."""
    if not GEMINI_API_KEY or not httpx:
        return None
    try:
        resp = httpx.post(
            GEMINI_URL,
            params={"key": GEMINI_API_KEY},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0, "maxOutputTokens": 2048},
            },
            timeout=30,
        )
        resp.raise_for_status()
        text = (resp.json()
                .get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", ""))
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
        return json.loads(text)
    except Exception as e:
        log(f"    Gemini error: {e}")
        return None


# ── JSON helpers ───────────────────────────────────────

def _load_json(task_name, month, keywords):
    d = OUTPUT_BASE / month
    d.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    p = d / f"{task_name}_{today}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8")), p
        except Exception:
            pass
    for f in sorted(d.glob(f"{task_name}_*.json"), reverse=True):
        if f != p:
            try:
                return json.loads(f.read_text(encoding="utf-8")), p
            except Exception:
                continue
    return {
        "title": task_name, "date": today, "keywords": keywords,
        "raw_candidates": [], "results": [],
        "summary": {"total": 0, "original": 0, "repost": 0},
        "progress": {"completed": 0, "total": 0,
                      "last_media_index": -1, "status": "進行中"},
    }, p


def _save(data, path):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8")


# ── CLI ────────────────────────────────────────────────

def _get_tasks(args):
    if getattr(args, 'task', None):
        if args.task not in TASKS_CONFIG:
            log(f"找不到 '{args.task}', 可用: {', '.join(TASKS_CONFIG)}")
            return {}
        return {args.task: TASKS_CONFIG[args.task]}
    m = getattr(args, 'month', '一月') or '一月'
    return {k: v for k, v in TASKS_CONFIG.items() if v["month"] == m}


def cmd_scan(args):
    media = load_media_list()
    log(f"載入 {len(media)} 個媒體")
    tasks = _get_tasks(args)
    log(f"Phase 1: 掃描 {len(tasks)} 個任務")
    for name, cfg in tasks.items():
        if _shutdown: break
        log(f"\n{'='*50}")
        scan_task(name, cfg, media, resume=not getattr(args, 'fresh', False))
    log("\nPhase 1 全部完成!")


def cmd_verify(args):
    tasks = _get_tasks(args)
    log(f"Phase 2: LLM 驗證 {len(tasks)} 個任務")
    for name, cfg in tasks.items():
        verify_task(name, cfg)
    log("\nPhase 2 全部完成!")
    generate_html_report(getattr(args, 'month', '一月') or '一月')


def cmd_run(args):
    """Full pipeline: scan → verify → report."""
    cmd_scan(args)
    if not _shutdown:
        cmd_verify(args)


def cmd_status(args):
    month = getattr(args, 'month', '一月') or '一月'
    d = OUTPUT_BASE / month
    print(f"\n{'='*55}")
    print(f" Pandora 掃描進度 — {month}")
    print(f"{'='*55}\n")
    if not d.exists():
        print("  (尚無資料)"); return
    total_raw, total_verified = 0, 0
    for tn in TASKS_CONFIG:
        if TASKS_CONFIG[tn]["month"] != month: continue
        jsons = sorted(d.glob(f"{tn}_*.json"), reverse=True)
        if not jsons:
            print(f"  {tn}: 尚未開始"); continue
        try:
            data = json.loads(jsons[0].read_text(encoding="utf-8"))
            prog = data.get("progress", {})
            raw = len(data.get("raw_candidates", []))
            res = len(data.get("results", []))
            comp = prog.get("completed", 0)
            tot = prog.get("total", 0)
            st = prog.get("status", "?")
            total_raw += raw; total_verified += res
            pct = int(comp/tot*100) if tot else 0
            bar = "█"*int(pct/3.3) + "░"*(30-int(pct/3.3))
            print(f"  {tn}")
            print(f"    [{bar}] {pct}% ({comp}/{tot})")
            print(f"    候選: {raw} | 驗證通過: {res} | 狀態: {st}\n")
        except Exception as e:
            print(f"  {tn}: 錯誤 {e}")
    print(f"  {'─'*40}")
    print(f"  候選總數: {total_raw} | 驗證通過: {total_verified}")


def generate_html_report(month):
    d = OUTPUT_BASE / month
    if not d.exists(): return
    all_r = []
    for tn in TASKS_CONFIG:
        if TASKS_CONFIG[tn]["month"] != month: continue
        jsons = sorted(d.glob(f"{tn}_*.json"), reverse=True)
        if jsons:
            try:
                data = json.loads(jsons[0].read_text(encoding="utf-8"))
                for r in data.get("results", []):
                    r["_t"] = tn; all_r.append(r)
            except Exception: pass

    rows = "".join(
        f"<tr><td>{r.get('_t','')}</td><td>{r.get('媒體','')}</td>"
        f"<td>{r.get('標題','')}</td><td>{r.get('日期','')}</td>"
        f"<td><a href=\"{r.get('連結','')}\" target=_blank>{r.get('連結','')}</a></td>"
        f"<td>{r.get('原生/轉載','')}</td></tr>\n"
        for r in all_r)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    n = len(all_r)
    nm = len(set(r.get('媒體','') for r in all_r))
    nt = len(set(r.get('_t','') for r in all_r))
    html = f"""<!DOCTYPE html><html lang=zh-TW><head><meta charset=UTF-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Pandora 報表 {month}</title><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,sans-serif;background:#f0f2f5;padding:20px;color:#333}}
.c{{max-width:1400px;margin:0 auto}}h1{{font-size:24px;margin-bottom:8px}}
.m{{color:#666;margin-bottom:20px;font-size:14px}}
.s{{display:flex;gap:16px;margin-bottom:20px;flex-wrap:wrap}}
.sc{{background:#fff;border-radius:8px;padding:16px 24px;box-shadow:0 1px 3px rgba(0,0,0,.1)}}
.sc .n{{font-size:28px;font-weight:700;color:#1a73e8}}.sc .l{{font-size:13px;color:#666}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.1)}}
th{{background:#1a73e8;color:#fff;padding:12px 16px;text-align:left;font-size:13px;position:sticky;top:0}}
td{{padding:10px 16px;border-bottom:1px solid #e8eaed;font-size:13px;max-width:300px;word-break:break-all}}
tr:hover{{background:#f8f9fa}}a{{color:#1a73e8;text-decoration:none}}
</style></head><body><div class=c>
<h1>FamilyMart 新聞露出報表 — {month}</h1>
<p class=m>更新: {now} | 共 {n} 筆</p>
<div class=s>
<div class=sc><div class=n>{n}</div><div class=l>總命中</div></div>
<div class=sc><div class=n>{nm}</div><div class=l>命中媒體</div></div>
<div class=sc><div class=n>{nt}</div><div class=l>已掃專案</div></div></div>
<table><thead><tr><th>專案</th><th>媒體</th><th>標題</th><th>日期</th><th>連結</th><th>原生/轉載</th></tr></thead>
<tbody>{rows}</tbody></table></div></body></html>"""
    CANVAS_PUBLIC.mkdir(parents=True, exist_ok=True)
    p = CANVAS_PUBLIC / f"pandora_report_{month}.html"
    p.write_text(html, encoding="utf-8")
    log(f"報表: {p}")


def cmd_report(args):
    generate_html_report(getattr(args, 'month', '一月') or '一月')


def main():
    pa = argparse.ArgumentParser(description="Pandora Batch Scanner v3")
    sp = pa.add_subparsers(dest="command")

    s = sp.add_parser("scan")
    s.add_argument("--task"); s.add_argument("--month", default="一月")
    s.add_argument("--resume", action="store_true", default=True)
    s.add_argument("--fresh", action="store_true")

    v = sp.add_parser("verify")
    v.add_argument("--task"); v.add_argument("--month", default="一月")

    r = sp.add_parser("run")
    r.add_argument("--task"); r.add_argument("--month", default="一月")
    r.add_argument("--fresh", action="store_true")

    st = sp.add_parser("status")
    st.add_argument("--month", default="一月")

    rp = sp.add_parser("report")
    rp.add_argument("--month", default="一月")

    args = pa.parse_args()
    cmds = {"scan": cmd_scan, "verify": cmd_verify, "run": cmd_run,
            "status": cmd_status, "report": cmd_report}
    fn = cmds.get(args.command)
    if fn:
        fn(args)
    else:
        pa.print_help()

if __name__ == "__main__":
    main()
