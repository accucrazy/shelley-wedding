# -*- coding: utf-8 -*-
"""
LLM 驗證：批次驗證 combined.json 中所有未驗證的結果。
用 Gemini Flash 判斷每筆是否真的跟該任務相關。
"""
import json, os, sys, time, re
from pathlib import Path

sys.path.insert(0, os.path.expanduser(
    "~/.openclaw/skills/pandora-news/venv/lib/python3.9/site-packages"))
import httpx

if sys.stdout:
    sys.stdout.reconfigure(encoding='utf-8')

COMBINED = Path(os.path.expanduser(
    "~/.openclaw/workspace/newscollect/Pandora News IO 0226/3-Pandora News io/一月/全部任務_combined.json"))
GEMINI_KEY = os.environ.get("GOOGLE_API_KEY", "")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"

BATCH_SIZE = 30


def call_gemini(prompt, retries=3):
    for attempt in range(retries):
        try:
            resp = httpx.post(
                GEMINI_URL,
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=30)
            if resp.status_code == 200:
                body = resp.json()
                text = body["candidates"][0]["content"]["parts"][0]["text"]
                return text.strip()
            elif resp.status_code == 429:
                time.sleep(5 * (attempt + 1))
            else:
                time.sleep(2)
        except Exception:
            time.sleep(2)
    return None


def verify_batch(task_name, items):
    """Verify a batch of items with LLM. Returns dict of id -> pass/fail."""
    items_text = ""
    for idx, item in enumerate(items, 1):
        items_text += f"{idx}. 媒體={item.get('媒體','')}, 標題={item.get('標題','')}, 連結={item.get('連結','')}\n"

    prompt = (
        f"以下是搜尋「{task_name}」（全家便利商店活動）的結果。\n"
        f"請判斷每一條是否真的與「{task_name}」相關。\n\n"
        f"判斷標準：\n"
        f"- 必須是與全家便利商店的「{task_name}」活動直接相關的新聞報導\n"
        f"- 包含全家相關活動的報導（即使標題不完全匹配）→ pass\n"
        f"- 與全家無關的內容（其他通路、其他品牌、一般草莓/咖啡資訊）→ fail\n"
        f"- 標題明顯是其他主題 → fail\n"
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
    if not GEMINI_KEY:
        env_file = os.path.expanduser("~/.openclaw/skills/pandora-news/.env")
        if os.path.exists(env_file):
            for line in open(env_file):
                if line.startswith("GOOGLE_API_KEY="):
                    global GEMINI_URL
                    key = line.strip().split("=", 1)[1]
                    GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
                    break

    data = json.loads(COMBINED.read_text(encoding="utf-8"))
    results = data.get("results", [])

    unverified = [(i, r) for i, r in enumerate(results)
                  if r.get("來源") in ("DDG-domain", "") and "llm_verified" not in r]

    print(f"總結果: {len(results)}, 未驗證: {len(unverified)}")

    if not unverified:
        print("全部已驗證")
        return

    by_task = {}
    for idx, r in unverified:
        by_task.setdefault(r.get("新聞", ""), []).append((idx, r))

    total_pass = 0
    total_fail = 0

    for task_name, items_with_idx in by_task.items():
        print(f"\n[{task_name}] 驗證 {len(items_with_idx)} 筆...")
        task_pass = 0

        for batch_start in range(0, len(items_with_idx), BATCH_SIZE):
            batch = items_with_idx[batch_start:batch_start + BATCH_SIZE]
            batch_items = [r for _, r in batch]
            batch_indices = [idx for idx, _ in batch]

            verdicts = verify_batch(task_name, batch_items)

            for pos, (orig_idx, r) in enumerate(batch, 1):
                result = verdicts.get(pos, "pass")
                results[orig_idx]["llm_verified"] = result
                if result == "pass":
                    task_pass += 1
                    total_pass += 1
                else:
                    total_fail += 1

            time.sleep(1)

            if (batch_start + BATCH_SIZE) % 90 == 0:
                data["results"] = results
                COMBINED.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"  → {task_name}: {task_pass} pass / {len(items_with_idx)-task_pass} fail")

    data["results"] = results
    COMBINED.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    passed = [r for r in results if r.get("llm_verified", "pass") == "pass"]
    print(f"\n{'='*50}")
    print(f"驗證完成: {total_pass} pass, {total_fail} fail")
    print(f"最終結果: {len(passed)} 筆 (含原已驗證)")

    export_verified(passed)


def export_verified(passed):
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
                 r.get("關鍵字",""), r.get("來源","")] for r in passed]
        service.spreadsheets().values().update(
            spreadsheetId=SHEET_ID, range=f"{TAB}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": [header] + rows}).execute()
        print(f"Sheet 已更新: {len(rows)} 筆 (只含 pass)")
    except Exception as e:
        print(f"[!] Sheet 更新失敗: {e}")


if __name__ == "__main__":
    main()
