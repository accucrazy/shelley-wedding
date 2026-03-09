# Pandora News Scanner — 一月掃描完整紀錄

## 概要

- **掃描期間**：2026-02-28
- **目標**：全家便利商店 2026 年 1 月 11 則新聞稿對應的媒體報導
- **媒體清單**：345 個台灣媒體
- **最終結果**：3,632 筆搜尋結果，涵蓋全部 345 個媒體

## 任務列表（11 則新聞稿）

| # | 任務名稱 | 最終筆數 |
|---|---------|---------|
| 1 | 全家草莓季 | 345 |
| 2 | 全家特力屋 | 288 |
| 3 | 全家高山茶 | 329 |
| 4 | 全家蜷川實花 | 341 |
| 5 | 全家年菜預購 | 344 |
| 6 | 全家超人力霸王 | 337 |
| 7 | 全家寒流抗寒 | 344 |
| 8 | 全家開運鮮食 | 344 |
| 9 | 全家UCC咖啡 | 344 |
| 10 | 全家溏心蛋 | 282 |
| 11 | 全家伴手禮 | 334 |

## 搜尋方法與演進

### 第一階段：DuckDuckGo API + Gemini LLM（`pandora_batch_scanner.py`）

- **方法**：對 345 個媒體逐一做 `{keyword} site:{domain}` DDG 搜尋
- **LLM 驗證**：用 Gemini 2.0 Flash 判斷是否相關
- **Phase 1**（搜尋）：每個任務掃 345 個域名，delay 1.5s
- **Phase 2**（驗證）：批次送 LLM 驗證，15 筆一批
- **結果**：完成 4 個任務（草莓季、UCC 咖啡、開運鮮食、年菜預購），每任務約 340 個 candidates
- **問題**：速度太慢（每任務 ~17 分鐘），只有草莓季完成 Phase 2（65 pass）

### 第二階段：Google News RSS（`gnews_scan.py` / `gnews_scan_v2.py`）

- **方法**：用 Google News RSS feed 搜尋關鍵字，解析 XML 取得結果
- **域名匹配**：從 RSS `<source url="...">` 屬性提取真實媒體域名
- **關鍵字擴展**：每任務 1-2 個關鍵字 + 新聞稿標題片段
- **結果**：+283 筆（GNews）
- **優點**：速度快、不限速、有發布日期
- **發現**：RSS 的 `<source>` tag 有真實域名，比 Google redirect link 更準確

### 第三階段：Google News RSS 大量關鍵字（`gnews_expanded.py`）

- **方法**：每任務擴展到 10-15 個拆開/重組的關鍵字變體
- **結果**：+240 筆（GNews-RSS）
- **關鍵字範例**（草莓季）：全家草莓季、全家 草莓、FamilyMart 草莓季、全家 ASAMIMICHAN、全家 草莓甜點 等 15 種

### 第四階段：DDG 快速 per-domain 掃描（`fast_domain_scan.py`）

- **方法**：對剩餘 7 個未完成任務，用 DDG `site:` 逐域名搜尋，delay 降到 0.8s
- **結果**：+1,800 筆（DDG-fast），每任務約 230-273 筆
- **耗時**：約 70 分鐘完成 7 個任務

### 其他嘗試（失敗/效果有限）

1. **Playwright Google Search**：被 CAPTCHA 擋住（headless 被偵測）
2. **Playwright stealth + Google**：仍被擋（即使加了 `--disable-blink-features`）
3. **Bing Search（httpx）**：需 JS 渲染，靜態 HTML 無搜尋結果
4. **Bing Search（Playwright）**：Bing 也有反機器人驗證
5. **Brave Search**：429 Too Many Requests
6. **SearXNG 公開實例**：全部 429 或 403
7. **Yahoo News 搜尋**：結果不相關（返回一般新聞而非搜尋結果）
8. **媒體站內搜尋**（`media_site_search.py`）：+10 筆，部分是導航元素雜訊

## 來源分布

| 來源 | 筆數 | 方法 |
|------|------|------|
| DDG-fast | 1,800 | DDG per-domain 快速版 |
| DDG-domain | 1,229 | DDG per-domain 原始版 |
| GNews | 283 | Google News RSS v1+v2 |
| GNews-RSS | 240 | Google News RSS 擴展關鍵字 |
| DDG | 41 | DDG broad search |
| DDG-broad | 28 | DDG 無 site: 限制搜尋 |
| SiteSearch | 10 | 媒體站內搜尋 |
| DDG-title | 1 | DDG 新聞稿標題搜尋 |

## 日期驗證問題

- **問題**：初期 scanner 錄入掃描日期而非發布日期
- **修復**：用 LLM 重新提取日期 + 月份篩選
- **結論**：嚴格日期篩選會大幅減少結果（66→10），最終改為先收集再人工確認

## 重要注意事項

1. DDG per-domain 結果（3,029 筆）未經 LLM 相關性驗證，含大量雜訊
2. Google News RSS 結果（523 筆）經過 LLM 驗證，品質較高
3. 完整資料已匯出至 Google Sheet「Pandora掃描結果」分頁
4. Sheet URL: https://docs.google.com/spreadsheets/d/1hh6wOIny3CwPB4bIVUPV7mtXNijijE2jN-p8zVK9qcU

## 最佳實踐（供二月掃描參考）

1. **優先順序**：Google News RSS（快+準）→ DDG per-domain（廣覆蓋）→ LLM 篩選
2. **關鍵字策略**：每任務 10+ 個變體（拆開、重組、英文、品牌名）
3. **DDG 延遲**：0.8-1.2s 可避免大部分 rate limit
4. **域名匹配**：用 RSS source URL 而非 Google redirect
5. **去重鍵值**：`媒體名|任務名`（一個媒體對一個任務只保留一筆）
