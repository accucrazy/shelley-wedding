# -*- coding: utf-8 -*-
"""
LLM 驗證一月所有結果：批次驗證 combined.json 中全部未驗證的結果。
"""
import json, os, sys, time, re, signal
from pathlib import Path

sys.path.insert(0, os.path.expanduser(
    "~/.openclaw/skills/pandora-news/venv/lib/python3.9/site-packages"))
import httpx

if sys.stdout:
    sys.stdout.reconfigure(encoding='utf-8')

COMBINED = Path(os.path.expanduser(
    "~/.openclaw/workspace/newscollect/Pandora News IO 0226/3-Pandora News io/一月/全部任務_combined.json"))

GEMINI_KEY = ""
GEMINI_URL = ""
BATCH_SIZE = 25

_shutdown = False
def _sig(s, f):
    global _shutdown; _shutdown = True
    print("\n[!] 收到停止信號，安全退出中...", flush=True)
signal.signal(signal.SIGTERM, _sig)
signal.signal(signal.SIGINT, _sig)


def init_gemini():
    global GEMINI_KEY, GEMINI_URL
    env_file = os.path.expanduser("~/.openclaw/skills/pandora-news/.env")
    if os.path.exists(env_file):
        for line in open(env_file):
            if line.startswith("GOOGLE_API_KEY="):
                GEMINI_KEY = line.strip().split("=", 1)[1]
                break
    if not GEMINI_KEY:
        GEMINI_KEY = os.environ.get("GOOGLE_API_KEY", "")
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


def verify_batch(task_name, items):
    items_text = ""
    for pos, item in enumerate(items, 1):
        items_text += (
            f"{pos}. 媒體={item.get('媒體','')}, "
            f"標題={item.get('標題','')}, "
            f"連結={item.get('連結','')}\n")

    prompt = (
        f"以下是搜尋「{task_name}」（全家便利商店活動）的結果。\n"
        f"請判斷每一條是否真的與全家便利商店的「{task_name}」相關。\n\n"
        f"判斷標準：\n"
        f"- 必須是與全家便利商店的「{task_name}」活動直接相關的新聞報導 → pass\n"
        f"- 包含全家相關活動的報導（即使標題不完全匹配）→ pass\n"
        f"- 與全家無關的內容（其他通路、其他品牌、一般資訊）→ fail\n"
        f"- 網站首頁、目錄頁、404頁面 → fail\n\n"
        f"候選列表：\n{items_text}\n"
        f"請只回覆 JSON array，每個元素格式：\n"
        f'{{"id": 1, "result": "pass"}} 或 {{"id": 1, "result": "fail"}}\n'
        f"只回 JSON array，不要其他文字。"
    )

    response = call_gemini(prompt)
    if not response:
        return {}
    try:
        clean = response.strip()
        if clean.startswith("```"):
            clean = re.sub(r"^```\w*\n?", "", clean)
            clean = re.sub(r"\n?```$", "", clean)
        arr = json.loads(clean)
        return {item["id"]: item["result"] for item in arr}
    except Exception:
        return {}


def main():
    init_gemini()
    if not GEMINI_KEY:
        print("[!] 找不到 GOOGLE_API_KEY")
        return

    data = json.loads(COMBINED.read_text(encoding="utf-8"))
    results = data.get("results", [])

    unverified = [(i, r) for i, r in enumerate(results)
                  if "llm_verified" not in r]

    print(f"一月總計: {len(results)}, 未驗證: {len(unverified)}")

    if not unverified:
        print("全部已驗證")
        return

    by_task = {}
    for idx, r in unverified:
        by_task.setdefault(r.get("新聞", ""), []).append((idx, r))

    total_pass = 0
    total_fail = 0

    for task_name, items in by_task.items():
        if _shutdown:
            break
        print(f"\n[{task_name}] 驗證 {len(items)} 筆...")
        task_pass = 0

        for batch_start in range(0, len(items), BATCH_SIZE):
            if _shutdown:
                break
            batch = items[batch_start:batch_start + BATCH_SIZE]
            batch_items = [r for _, r in batch]

            verdicts = verify_batch(task_name, batch_items)

            for pos, (orig_idx, r) in enumerate(batch, 1):
                v = verdicts.get(pos, "pass")
                results[orig_idx]["llm_verified"] = v
                if v == "pass":
                    task_pass += 1
                    total_pass += 1
                else:
                    total_fail += 1

            time.sleep(1)

            if (batch_start + BATCH_SIZE) % 100 == 0:
                data["results"] = results
                COMBINED.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8")

        print(f"  → {task_name}: {task_pass} pass / {len(items)-task_pass} fail")
        data["results"] = results
        COMBINED.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*50}")
    print(f"驗證完成: {total_pass} pass, {total_fail} fail")

    passed = [r for r in results if r.get("llm_verified", "pass") == "pass"]
    from collections import Counter
    tc = Counter(r.get("新聞", "") for r in passed)
    mc = len(set(r.get("媒體", "") for r in passed))
    print(f"最終 pass: {len(passed)} 筆, {mc} 個媒體")
    for t, c in sorted(tc.items()):
        print(f"  {t}: {c}")


if __name__ == "__main__":
    main()
