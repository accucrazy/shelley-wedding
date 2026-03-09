---
name: pandora-news
description: 新聞稿媒體露出批次掃描（GNews+DDG 三層搜尋 + LLM驗證 + 作者爬取）+ Google Sheet 月報生成
metadata: {"openclaw":{"requires":{}}}
---

# Pandora News — 新聞露出追蹤（v4.2）

三層掃描：Google News RSS → DDG 廣域搜尋 → DDG site 補漏 → Gemini Flash 批次驗證 → 日期窗口過濾 → 作者爬取。
支援全家 + 7-ELEVEN 多品牌掃描。不依賴瀏覽器，完全背景自動執行。

## 指令速查

核心腳本：`pandora-news-scanner/scanner_v4_test.py`

```bash
cd pandora-news-scanner
```

| 動作 | 指令 |
|------|------|
| 掃描全家全部任務 | `python scanner_v4_test.py scan` |
| 掃描 7-ELEVEN 全部 | `python scanner_v4_test.py scan --brand 7-11` |
| 掃描 7-ELEVEN 單一任務 | `python scanner_v4_test.py scan --brand 7-11 --task 711藝伎咖啡` |
| 全家一月份 Google Sheet 月報 | `python scanner_v4_test.py monthly --month 一月` |
| 7-ELEVEN 一月份月報 | `python scanner_v4_test.py monthly --month 一月 --brand 7-11` |
| 比較報告 (vs 舊版 vs 意藍) | `python scanner_v4_test.py report` |
| 查看單一任務結果 | `python scanner_v4_test.py results --task 全家草莓季` |
| 品質檢核 | `python scanner_v4_test.py results --check-quality` |
| 查看新聞稿設定 | `python scanner_v4_test.py press` |

### 作者爬取（獨立步驟）

```bash
python extract_authors.py   # 從文章 HTML 提取真實作者，更新 v4_combined_{brand}.json
```

## 架構（v4.2 三層搜尋）

### Phase 1a: Google News RSS（主力，~56%）
- 用 `after:{press_date}` 日期過濾
- 從 `<source>` 標籤提取媒體名
- 每組關鍵字 + 新聞稿標題片段都搜尋

### Phase 1b: DDG 廣域搜尋（~39%）
- 不加 `site:`，搜完透過 345 家 domain map 匹配
- max_results=80，使用前 6 組關鍵字
- 從 snippet 提取日期做硬性過濾

### Phase 1c: DDG Site 補漏（~5%）
- 僅針對 Phase 1a+1b 未覆蓋的高價值媒體
- 300s 全域 timeout，5 次連續失敗即跳過

### Phase 2: LLM 嚴格驗證
- 品牌動態 prompt（BRAND_PROMPT_MAP 依 --brand 切換）
- 含 press_date 日期意識，舊年份 → false
- 每批 40–60 篇，Gemini 2.0 Flash，temperature 0.1

### Phase 3: 後處理
- 日期窗口過濾：< press_date 或 > press_date+30天 → 移除
- 缺日期填補：URL 提取 → fallback press_date
- 作者爬取：extract_authors.py 從 HTML meta/JSON-LD 提取

### 輸出
- Google Sheet：統計報表 + 新聞明細（兩個分頁）
- JSON 備份：`v4_test_output/monthly_{月}_{brand}.json`
- 合併結果：`v4_test_output/v4_combined_{brand}.json`

## 已設定任務

### 一月 — 全家（11 任務）
全家草莓季、全家UCC咖啡、全家開運鮮食、全家年菜預購、全家蜷川實花、
全家特力屋、全家溏心蛋、全家高山茶、全家超人力霸王、全家寒流抗寒、全家伴手禮

### 一月 — 7-ELEVEN（20 任務）
711清水服務區週年慶、711米其林法餐、711年節社交經濟、711把愛找回來公益、
711智能果昔機、711阜杭豆漿飯糰、711小熊維尼集點、711馬年前哨戰優惠、
711Fresh橋港門市、711藝伎咖啡、711抗寒保暖、711金馬年開運、711東南亞美食、
711桂氣茶飲優惠、711西村優志集點、711開運福袋、711OPEN家族貼圖、
711香菜美食、711貓福珊迪

### 二月 — 全家（14 任務）
全家助你擺脫收假症候群、Fami!ce x 哆啦A夢、全家草莓季、年後甩油動起來、
抗寒三寶優惠出爐、全家迎開學、情人節空運玫瑰、全家應援中華隊、
化身不打烊寵物店、春遊賞櫻趣、就一起挺中華隊、世界番薯日、228優惠、日落優惠

## 關鍵設定檔

| 檔案 | 說明 |
|------|------|
| `scanner_v4_test.py` | 核心掃描器，含 TASKS_CONFIG、MONTHLY_ORDER、scan/monthly 指令 |
| `extract_authors.py` | 作者爬取腳本 |
| `新聞掃描方法論.md` | 完整方法論文件（含踩坑紀錄） |

## 新增品牌/任務

1. 在 `scanner_v4_test.py` 的 `TASKS_CONFIG` 中新增 task，設定 `"brand": "品牌名"`
2. 在 `MONTHLY_ORDER` 中新增對應月份的排序
3. 在 `BRAND_PROMPT_MAP` 中新增品牌的 LLM prompt 設定

## 日誌

- 掃描輸出：`v4_test_output/` 目錄
- 個別任務結果：`v4_test_output/{task_name}_v4.json`
- 合併結果：`v4_test_output/v4_combined_{brand}.json`
