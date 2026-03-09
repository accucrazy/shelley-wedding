# -*- coding: utf-8 -*-
"""
Re-verify：針對已完成的 JSON 結果，用 LLM 重新提取日期並過濾月份。
只處理 status=verified 且 results 裡日期不正確的任務。

用法：
    ~/.openclaw/skills/pandora-news/venv/bin/python reverify_dates.py
"""

import json, glob, os, sys, time, re
from datetime import datetime
from pathlib import Path

try:
    import httpx
except ImportError:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/skills/pandora-news/venv/lib/python3.9/site-packages"))
    import httpx

JSON_DIR = os.path.expanduser(
    "~/.openclaw/workspace/newscollect/Pandora News IO 0226/3-Pandora News io/一月"
)
TARGET_MONTH = "2026-01"

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


def call_gemini(prompt):
    try:
        resp = httpx.post(
            GEMINI_URL,
            params={"key": GEMINI_API_KEY},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0, "maxOutputTokens": 4096},
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
        print(f"  Gemini error: {e}")
        return None


def extract_date_from_snippet(snippet):
    m = re.search(r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})', snippet)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    month_map = {"Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
                 "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
                 "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"}
    m = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s*(\d{4})', snippet)
    if m:
        return f"{m.group(3)}-{month_map[m.group(1)]}-{int(m.group(2)):02d}"
    return "unknown"


def reverify_file(fpath):
    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)

    task_name = data.get("title", "")
    results = data.get("results", [])
    raw_candidates = data.get("raw_candidates", [])

    if not results:
        print(f"  [{task_name}] 無結果，跳過")
        return

    rc_map = {}
    for rc in raw_candidates:
        key = rc.get("連結", "")
        if key:
            rc_map[key] = rc

    needs_date_fix = [r for r in results if not r.get("日期", "").startswith(TARGET_MONTH)]
    if not needs_date_fix:
        print(f"  [{task_name}] 日期都正確，跳過")
        return

    print(f"  [{task_name}] 需修復日期: {len(needs_date_fix)}/{len(results)} 筆")

    BATCH = 15
    fixed = []
    removed = 0

    for batch_start in range(0, len(needs_date_fix), BATCH):
        batch = needs_date_fix[batch_start:batch_start + BATCH]

        items_text = ""
        for idx, r in enumerate(batch):
            rc = rc_map.get(r.get("連結", ""), {})
            snippet = rc.get("snippet", "")[:300]
            items_text += (
                f"\n---\n#{idx+1}\n"
                f"標題: {r.get('標題', '')}\n"
                f"媒體: {r.get('媒體', '')}\n"
                f"連結: {r.get('連結', '')}\n"
                f"摘要: {snippet}\n"
            )

        prompt = (
            f"以下是關於「{task_name}」（全家便利商店活動）的新聞搜尋結果。\n"
            f"請從標題、摘要、連結中提取每則新聞的實際發布日期。\n\n"
            f"候選列表：{items_text}\n\n"
            f"請回答 JSON array，每個元素格式：\n"
            f'{{"id": 1, "date": "YYYY-MM-DD"}}\n'
            f"date：新聞的實際發布日期。如果找不到明確日期，填 \"unknown\"。\n"
            f"只回 JSON array，不要其他文字。"
        )

        verdicts = call_gemini(prompt)
        time.sleep(0.5)

        if verdicts is None:
            for r in batch:
                rc = rc_map.get(r.get("連結", ""), {})
                fallback = extract_date_from_snippet(rc.get("snippet", ""))
                r["日期"] = fallback
                fixed.append(r)
            continue

        verdict_map = {}
        for v in verdicts:
            vid = v.get("id")
            if vid is not None:
                verdict_map[vid] = v

        for idx, r in enumerate(batch):
            v = verdict_map.get(idx + 1, {})
            pub_date = str(v.get("date", "unknown")).strip()

            if pub_date == "unknown" or len(pub_date) < 8:
                rc = rc_map.get(r.get("連結", ""), {})
                pub_date = extract_date_from_snippet(rc.get("snippet", ""))

            if pub_date != "unknown" and not pub_date.startswith(TARGET_MONTH):
                removed += 1
                print(f"    移除 (日期 {pub_date}): {r.get('媒體', '')} - {r.get('標題', '')[:30]}")
                continue

            r["日期"] = pub_date
            fixed.append(r)

        print(f"    batch {batch_start+1}-{batch_start+len(batch)} done")

    already_ok = [r for r in results if r.get("日期", "").startswith(TARGET_MONTH)]
    new_results = already_ok + fixed

    print(f"  [{task_name}] 結果: {len(results)} → {len(new_results)} (移除 {removed}, unknown日期保留)")

    data["results"] = new_results
    data["summary"] = {
        "total": len(new_results),
        "original": sum(1 for r in new_results if r.get("原生/轉載") == "原生"),
        "repost": sum(1 for r in new_results if r.get("原生/轉載") != "原生"),
    }

    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  [{task_name}] 已儲存")


def main():
    pattern = os.path.join(JSON_DIR, "*_2026-*.json")
    files = sorted(glob.glob(pattern))

    if not files:
        print("沒有找到 JSON 結果檔")
        return

    print(f"找到 {len(files)} 個 JSON 檔案")
    print(f"目標月份: {TARGET_MONTH}\n")

    for fpath in files:
        name = os.path.basename(fpath)
        print(f"\n處理: {name}")
        reverify_file(fpath)

    print("\n完成！")


if __name__ == "__main__":
    main()
