import json, re, time, sys, os
from pathlib import Path
from html.parser import HTMLParser

sys.path.insert(0, os.path.expanduser(
    "~/openclaw/skills/pandora-news/venv/lib/python3.9/site-packages"))
import httpx

COMBINED = Path(os.path.expanduser(
    "~/DEV/openclaw/pandora-news-scanner/v4_test_output/v4_combined_7-11.json"))

SKIP_DOMAINS = {
    "facebook.com", "youtube.com", "line.me", "today.line.me",
    "ptt.cc", "dcard.tw", "711go.7-11.com.tw", "instagram.com",
}

class AuthorExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.author = ""
        self._in_jsonld = False
        self._jsonld_buf = ""

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "meta":
            name = (d.get("name","") or d.get("property","")).lower()
            content = d.get("content","") or ""
            if name in ("author", "article:author", "og:article:author",
                        "dable:author", "sailthru.author", "parsely-author",
                        "dc.creator", "dcterms.creator"):
                if content and not self.author:
                    self.author = content.strip()
        if tag == "script":
            tp = d.get("type","").lower()
            if "ld+json" in tp:
                self._in_jsonld = True
                self._jsonld_buf = ""

    def handle_endtag(self, tag):
        if tag == "script" and self._in_jsonld:
            self._in_jsonld = False
            if not self.author:
                self._parse_jsonld(self._jsonld_buf)

    def handle_data(self, data):
        if self._in_jsonld:
            self._jsonld_buf += data

    def _parse_jsonld(self, text):
        try:
            obj = json.loads(text)
            self._extract_author_from_ld(obj)
        except:
            pass

    def _extract_author_from_ld(self, obj):
        if isinstance(obj, list):
            for item in obj:
                self._extract_author_from_ld(item)
            return
        if not isinstance(obj, dict):
            return
        author = obj.get("author")
        if author:
            if isinstance(author, str) and author:
                self.author = author.strip()
            elif isinstance(author, dict):
                name = author.get("name", "")
                if name and isinstance(name, str):
                    self.author = name.strip()
            elif isinstance(author, list) and author:
                first = author[0]
                if isinstance(first, dict):
                    self.author = first.get("name", "").strip()
                elif isinstance(first, str):
                    self.author = first.strip()

def extract_author(url, client):
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.replace("www.", "")
    if any(skip in domain for skip in SKIP_DOMAINS):
        return ""
    try:
        resp = client.get(url, timeout=10, follow_redirects=True)
        if resp.status_code != 200:
            return ""
        html = resp.text[:50000]
        parser = AuthorExtractor()
        parser.feed(html)
        return parser.author
    except:
        return ""

def main():
    with open(COMBINED) as f:
        data = json.load(f)

    all_articles = []
    for task_name, task_data in data.items():
        for r in task_data.get("results", []):
            all_articles.append((task_name, r))

    total = len(all_articles)
    found = 0
    skipped = 0
    errors = 0

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html",
        "Accept-Language": "zh-TW,zh;q=0.9",
    }

    with httpx.Client(headers=headers, verify=False) as client:
        for i, (task_name, article) in enumerate(all_articles):
            url = article.get("連結", "")
            if not url:
                skipped += 1
                continue

            author = extract_author(url, client)
            if author:
                article["作者"] = author
                found += 1
            
            if (i+1) % 20 == 0:
                print(f"  進度: {i+1}/{total}, 已找到 {found} 位作者", flush=True)
            
            time.sleep(0.3)

    with open(COMBINED, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n完成: {total} 篇文章, 找到 {found} 位作者 ({found/total*100:.0f}%)")

if __name__ == "__main__":
    main()
