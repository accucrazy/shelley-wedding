# -*- coding: utf-8 -*-
"""
直接搜尋媒體網站：用各大媒體自己的搜尋功能搜，不經過搜尋引擎。
繞過 Google/Bing CAPTCHA 限制。
"""
import json, os, sys, time, re
from urllib.parse import urlencode, urlparse, quote_plus
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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}

TASKS = {
    "全家草莓季": "全家草莓季",
    "全家UCC咖啡": "全家 UCC",
    "全家開運鮮食": "全家 開運鮮食",
    "全家年菜預購": "全家 年菜",
    "全家蜷川實花": "全家 蜷川實花",
    "全家特力屋": "全家 特力屋",
    "全家溏心蛋": "全家 溏心蛋",
    "全家高山茶": "全家 高山茶",
    "全家超人力霸王": "全家 超人力霸王",
    "全家寒流抗寒": "全家 寒流",
    "全家伴手禮": "全家 伴手禮",
}

SEARCH_TEMPLATES = {
    "ettoday.net": {
        "url": "https://www.ettoday.net/news_search/doSearch.php?search_term_string={q}",
        "pattern": r'href="(https://www\.ettoday\.net/news/\d+/\d+\.htm)"',
        "title_pattern": r'<h2[^>]*><a[^>]*>(.*?)</a></h2>',
    },
    "ctwant.com": {
        "url": "https://www.ctwant.com/search/{q}",
        "pattern": r'href="(https://www\.ctwant\.com/article/\d+)"',
        "title_pattern": r'<h\d[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</h\d>',
    },
    "ftnn.com.tw": {
        "url": "https://www.ftnn.com.tw/search?q={q}",
        "pattern": r'href="(https://www\.ftnn\.com\.tw/news/[^"]+)"',
    },
    "cool3c.com": {
        "url": "https://www.cool3c.com/search/{q}",
        "pattern": r'href="(https://www\.cool3c\.com/article/\d+)"',
    },
    "digitimes.com.tw": {
        "url": "https://www.digitimes.com.tw/search?q={q}",
        "pattern": r'href="(https://www\.digitimes\.com\.tw/[^"]+)"',
    },
    "gq.com.tw": {
        "url": "https://www.gq.com.tw/search?q={q}",
        "pattern": r'href="(https://www\.gq\.com\.tw/[^"]+article[^"]+)"',
    },
    "chinatimes.com": {
        "url": "https://www.chinatimes.com/search/{q}?chdtv",
        "pattern": r'href="(https://www\.chinatimes\.com/(?:realtimenews|newspapers)/\d+[^"]*)"',
    },
    "tvbs.com.tw": {
        "url": "https://news.tvbs.com.tw/news/searchresult/{q}/news",
        "pattern": r'href="(https://news\.tvbs\.com\.tw/[^"]+/\d+)"',
    },
    "storm.mg": {
        "url": "https://www.storm.mg/search?q={q}",
        "pattern": r'href="(https://www\.storm\.mg/article/\d+)"',
    },
    "nownews.com": {
        "url": "https://www.nownews.com/search?keyword={q}",
        "pattern": r'href="(https://www\.nownews\.com/news/[^"]+)"',
    },
    "setn.com": {
        "url": "https://www.setn.com/search.aspx?q={q}",
        "pattern": r'href="(https://www\.setn\.com/News\.aspx\?NewsID=\d+)"',
    },
    "ltn.com.tw": {
        "url": "https://search.ltn.com.tw/list?keyword={q}",
        "pattern": r'href="(https://[^"]*ltn\.com\.tw/[^"]+/\d+)"',
    },
    "udn.com": {
        "url": "https://udn.com/search/word/2/{q}",
        "pattern": r'href="(https://udn\.com/news/story/[^"]+)"',
    },
    "cnyes.com": {
        "url": "https://www.cnyes.com/search/news?keyword={q}",
        "pattern": r'href="(https://[^"]*cnyes\.com/news/[^"]+)"',
    },
    "businesstoday.com.tw": {
        "url": "https://www.businesstoday.com.tw/search/result/{q}",
        "pattern": r'href="(https://www\.businesstoday\.com\.tw/article/[^"]+)"',
    },
    "inside.com.tw": {
        "url": "https://www.inside.com.tw/?s={q}",
        "pattern": r'href="(https://www\.inside\.com\.tw/article/[^"]+)"',
    },
    "bnext.com.tw": {
        "url": "https://www.bnext.com.tw/search/{q}",
        "pattern": r'href="(https://www\.bnext\.com\.tw/article/[^"]+)"',
    },
    "wealth.com.tw": {
        "url": "https://www.wealth.com.tw/search?q={q}",
        "pattern": r'href="(https://www\.wealth\.com\.tw/articles/[^"]+)"',
    },
    "ctee.com.tw": {
        "url": "https://www.ctee.com.tw/search?q={q}",
        "pattern": r'href="(https://www\.ctee\.com\.tw/news/[^"]+)"',
    },
    "cna.com.tw": {
        "url": "https://www.cna.com.tw/search/hysearchws.aspx?q={q}",
        "pattern": r'href="(https://www\.cna\.com\.tw/news/[^"]+)"',
    },
    "taiwannews.com.tw": {
        "url": "https://www.taiwannews.com.tw/search?keyword={q}",
        "pattern": r'href="(https://www\.taiwannews\.com\.tw/[^"]+/news/[^"]+)"',
    },
    "newtalk.tw": {
        "url": "https://newtalk.tw/search?q={q}&type=news",
        "pattern": r'href="(https://newtalk\.tw/news/view/[^"]+)"',
    },
    "mirrormedia.mg": {
        "url": "https://www.mirrormedia.mg/search/{q}",
        "pattern": r'href="(https://www\.mirrormedia\.mg/story/[^"]+)"',
    },
    "rti.org.tw": {
        "url": "https://www.rti.org.tw/search/news?keyword={q}",
        "pattern": r'href="(https://www\.rti\.org\.tw/news/view/[^"]+)"',
    },
    "merit-times.com": {
        "url": "https://www.merit-times.com/search?q={q}",
        "pattern": r'href="(https://www\.merit-times\.com/NewsPage[^"]+)"',
    },
}


def load_media_list():
    content = MEDIA_LIST.read_text(encoding="utf-8")
    media = {}
    for line in content.split("\n"):
        if "|" not in line or "---" in line or "媒體名稱" in line:
            continue
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) >= 2 and "." in parts[1]:
            media[parts[1]] = parts[0]
    return media


def search_media_site(domain, config, keyword):
    url = config["url"].format(q=quote_plus(keyword))
    pattern = config["pattern"]
    title_pattern = config.get("title_pattern", r"<h[23][^>]*>(.*?)</h[23]>")

    try:
        resp = httpx.get(url, timeout=10, follow_redirects=True, headers=HEADERS)
        if resp.status_code != 200:
            return []

        links = list(set(re.findall(pattern, resp.text)))
        titles_raw = re.findall(title_pattern, resp.text, re.DOTALL)
        titles = [re.sub(r"<[^>]+>", "", t).strip() for t in titles_raw]

        results = []
        for i, link in enumerate(links[:10]):
            title = titles[i] if i < len(titles) else ""
            if not title:
                a_match = re.search(
                    rf'<a[^>]*href="{re.escape(link)}"[^>]*>(.*?)</a>',
                    resp.text, re.DOTALL)
                if a_match:
                    title = re.sub(r"<[^>]+>", "", a_match.group(1)).strip()
            results.append({"title": title or "(no title)", "url": link})
        return results
    except Exception:
        return []


def main():
    domain_map = load_media_list()
    data = json.loads(COMBINED_JSON.read_text(encoding="utf-8"))
    existing = data.get("results", [])
    existing_keys = set(f"{r.get('媒體','')}|{r.get('新聞','')}" for r in existing)
    initial = len(existing)

    total_new = 0

    for task_name, keyword in TASKS.items():
        print(f"\n[{task_name}] keyword: {keyword}")
        task_new = 0

        for domain, config in SEARCH_TEMPLATES.items():
            name = domain_map.get(domain, "")
            if not name:
                continue

            key = f"{name}|{task_name}"
            if key in existing_keys:
                continue

            results = search_media_site(domain, config, keyword)
            if results:
                r = results[0]
                existing_keys.add(key)
                existing.append({
                    "新聞": task_name, "日期": "", "媒體": name,
                    "標題": r["title"], "連結": r["url"],
                    "原生/轉載": "原生", "關鍵字": keyword,
                    "來源": "SiteSearch",
                })
                task_new += 1
                total_new += 1
                print(f"  ✓ {name}: {r['title'][:40]}")

            time.sleep(0.5)

        print(f"  → +{task_new}")

    data["results"] = existing
    data["summary"]["total"] = len(existing)
    COMBINED_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*50}")
    print(f"新增: {total_new}, 總計: {len(existing)}")


if __name__ == "__main__":
    main()
