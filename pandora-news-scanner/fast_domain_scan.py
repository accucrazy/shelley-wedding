# -*- coding: utf-8 -*-
"""
快速 per-domain 掃描：只跑還沒完成的任務，最快速度收集 candidates。
不做 LLM 驗證，之後統一批次處理。
"""
import json, os, sys, time
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
COMBINED = BASE_DIR / "3-Pandora News io" / "一月" / "全部任務_combined.json"

TASKS = {
    "全家蜷川實花": ["全家 蜷川實花", "全家 蜷川"],
    "全家特力屋": ["全家 特力屋"],
    "全家溏心蛋": ["全家 溏心蛋"],
    "全家高山茶": ["全家 高山茶"],
    "全家超人力霸王": ["全家 超人力霸王", "全家 奧特曼"],
    "全家寒流抗寒": ["全家 寒流", "全家 抗寒"],
    "全家伴手禮": ["全家 陳耀訓", "全家 伴手禮"],
}

AGGREGATOR_DOMAINS = {"today.line.me", "tw.news.yahoo.com", "msn.com", "news.pchome.com.tw"}


def load_media():
    content = (BASE_DIR / "1-媒體清單" / "news-media-list.md").read_text(encoding="utf-8")
    media = []
    for line in content.split("\n"):
        if "|" not in line or "---" in line or "媒體名稱" in line:
            continue
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) >= 2 and "." in parts[1]:
            media.append({"name": parts[0], "domain": parts[1]})
    return media


def ddg(q, max_results=3):
    for _ in range(2):
        try:
            with DDGS() as d:
                return list(d.text(q, region="tw-tzh", max_results=max_results))
        except Exception:
            time.sleep(1)
    return []


def main():
    media = load_media()
    data = json.loads(COMBINED.read_text(encoding="utf-8"))
    existing = data.get("results", [])
    existing_keys = set(f"{r.get('媒體','')}|{r.get('新聞','')}" for r in existing)

    print(f"現有: {len(existing)}, 開始快速掃描")
    total_new = 0

    for task_name, keywords in TASKS.items():
        print(f"\n[{task_name}]")
        task_new = 0

        for i, m in enumerate(media):
            domain = m["domain"]
            name = m["name"]
            key = f"{name}|{task_name}"
            if key in existing_keys:
                continue

            for kw in keywords:
                if domain in AGGREGATOR_DOMAINS:
                    q = f"{kw} {name}"
                else:
                    q = f"{kw} site:{domain}"

                results = ddg(q, max_results=3)
                found = False
                for r in results:
                    url = r.get("href", "")
                    title = r.get("title", "")
                    if not url:
                        continue
                    rd = urlparse(url).netloc.replace("www.", "")
                    if domain not in rd and domain not in AGGREGATOR_DOMAINS:
                        continue
                    existing.append({
                        "新聞": task_name, "日期": "", "媒體": name,
                        "標題": title, "連結": url,
                        "原生/轉載": "原生", "關鍵字": kw, "來源": "DDG-fast",
                    })
                    existing_keys.add(key)
                    task_new += 1
                    total_new += 1
                    found = True
                    break
                if found:
                    break

                time.sleep(0.8)

            if (i + 1) % 50 == 0:
                print(f"  [{i+1}/{len(media)}] +{task_new}")
                data["results"] = existing
                data["summary"]["total"] = len(existing)
                COMBINED.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"  → {task_name}: +{task_new}")
        data["results"] = existing
        data["summary"]["total"] = len(existing)
        COMBINED.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*50}")
    print(f"新增: {total_new}, 總計: {len(existing)}")


if __name__ == "__main__":
    main()
