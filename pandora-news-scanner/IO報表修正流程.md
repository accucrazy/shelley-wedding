# IO 報表修正流程

> 從 Pandora 掃描結果到最終 IO 報表的完整流程，以及常見修正情境的處理方法。

---

## 一、IO 報表結構

每份 IO 報表包含三個分頁：

### 1.1 統計報表

| 欄位 | 說明 |
|------|------|
| 新聞標題 | 新聞稿標題（與客戶新聞稿清單一致） |
| 發稿日期 | YYYY/MM/DD |
| 發稿編號 | 流水號 |
| 新聞頻道數 | 去重後的新聞媒體數量 |
| 新聞總主文數 | 新聞文章總篇數 |
| 社群頻道數 | 去重後的社群媒體數量 |
| 社群總主文數 | 社群文章總篇數 |

### 1.2 明細報表

| 欄位 | 說明 |
|------|------|
| 編號 | 流水號（從 1 開始連續編號） |
| 發布時間 | YYYY-MM-DD |
| 主題 | 對應的新聞稿標題 |
| 新聞標題 | 文章標題 |
| 網站 | 媒體名稱 |
| 連結 | 文章連結 |
| 作者 | 記者/作者 |
| 原生/轉載 | 原生 or 轉載 |

### 1.3 報表說明

報表的基本說明文字，通常包含監測時間範圍和來源說明。

---

## 二、從掃描結果到 IO 報表

### 2.1 輸入來源

```
Pandora 掃描 JSON（全部任務_combined.json）
    ↓
客戶新聞稿清單（.xlsx）
    ↓
比對 & 分類
    ↓
IO 報表（Google Sheets）
```

### 2.2 分類邏輯

**新聞 vs 社群**的判定標準（以域名/媒體名判斷）：

```python
SOCIAL_KEYWORDS = [
    "facebook", "粉絲團", "instagram", "threads", "tiktok",
    "youtube", "ptt", "dcard", "mobile01", "plurk", "blogger",
    "痞客邦", "medium.com", "popdaily", "pixnet",
]
```

包含以上關鍵字的歸類為「社群」，其餘為「新聞」。

**原生 vs 轉載**的判定標準：

```python
AGGREGATORS = [
    "yahoo新聞", "yahoo股市", "line today", "msn",
    "pchome online 新聞", "蕃新聞", "match生活網",
]
```

以上為「轉載」，其餘為「原生」。

### 2.3 統計計算

```python
for task in tasks:
    articles = [a for a in all_articles if a["主題"] == task["title"]]
    news = [a for a in articles if not is_social(a)]
    social = [a for a in articles if is_social(a)]

    task["news_channels"] = len(set(a["媒體"] for a in news))
    task["news_articles"] = len(news)
    task["social_channels"] = len(set(a["媒體"] for a in social))
    task["social_posts"] = len(social)
```

---

## 三、常見修正情境

### 3.1 新聞稿數量不對（IO 報表筆數 < 客戶新聞稿數）

**診斷步驟**：
1. 從客戶的新聞稿清單（`.xlsx`）取得完整列表（標題 + 發稿日 + 編號）
2. 與 IO 報表的統計報表逐一比對
3. 找出缺少的新聞稿

**常見原因**：
- 同一主題的新聞稿發了多次，但 IO 報表只列了一次 → 需要拆分
- 某篇新聞稿漏掃了 → 需要補掃

### 3.2 開工優惠類拆分（同一新聞稿多次發稿）

這是最常遇到的修正情境。某些促銷活動（如開工優惠）會在不同日期發布內容相似但細節不同的新聞稿。

**拆分流程**：

```
1. 確認發稿次數和日期
   ├── 第一次：2/11（CNY 後開工）
   └── 第二次：2/20（延續優惠）

2. 從明細報表中按日期切割文章
   ├── 2/11 ~ 2/19 的文章 → 歸入第一次發稿
   └── 2/20 以後的文章 → 歸入第二次發稿

3. 分別計算兩次的統計數據
   ├── 第一次：頻道數、文章數、社群頻道數、社群篇數
   └── 第二次：頻道數、文章數、社群頻道數、社群篇數

4. 在統計報表中拆為兩行，標題加註（第一次發稿）（第二次發稿）
```

**二月實際案例**：

全家開工優惠：
- 第一次發稿 2/11：5 頻道 / 7 篇新聞，9 頻道 / 71 篇社群
- 第二次發稿 2/20：26 頻道 / 46 篇新聞，60 頻道 / 469 篇社群

7-ELEVEN 開工優惠：
- 「推開工優惠、鮮乳兌換及元宵燈籠」：33 頻道 / 59 篇
- 「開工咖啡優惠、鮮乳兌換與元宵燈籠」：13 頻道 / 19 篇

### 3.3 數據太少的修正（補掃）

**診斷步驟**：
1. 先用 Google 搜尋確認是否有更多報導
2. 用 Google News RSS 重新掃描多組關鍵字

**補掃流程**：

```python
import urllib.request
from xml.etree import ElementTree

keywords = [
    "7-ELEVEN 蕎麥茶",
    "統一超商 蕎麥茶",
    "7-11 黃金蕎麥茶",
    "7-ELEVEN 蕎麥茶 新品",
]

for kw in keywords:
    url = f"https://news.google.com/rss/search?q={quote_plus(kw)}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    data = urllib.request.urlopen(url).read()
    root = ElementTree.fromstring(data)
    for item in root.findall(".//item"):
        title = item.findtext("title", "")
        pub_date = item.findtext("pubDate", "")
        # 過濾：只保留 2026 年 2 月的結果
        # 去重：URL 正規化
```

**蕎麥茶修正實例**：原本 3 頻道 / 3 篇 → 重新掃描後 15 頻道 / 17 篇。

### 3.4 缺少特定日期的新聞稿

**診斷**：比對客戶清單發現某個日期的新聞稿完全沒有資料。

**解法**：
1. 取得該新聞稿的標題和內容
2. 設計 4-6 組搜尋關鍵字
3. Google News RSS + DDG 補掃
4. LLM 驗證相關性
5. 加入明細報表並更新統計

---

## 四、修正 Google Sheets 的技術要點

### 4.1 .xlsx 檔無法直接用 API 修改

Google Sheets API 對上傳到 Drive 的 `.xlsx` 格式檔案回傳 `HttpError 400`。

**解法**：建立新的 native Google Sheet，用 `spreadsheets().create()` 然後 `values().update()` 寫入。

```python
from googleapiclient.discovery import build

service = build('sheets', 'v4', credentials=creds)

# 建立新 Sheet
body = {
    'properties': {'title': '全家 2026-03-07 (修正版)'},
    'sheets': [
        {'properties': {'title': '統計報表'}},
        {'properties': {'title': '明細報表'}},
        {'properties': {'title': '報表說明'}},
    ]
}
result = service.spreadsheets().create(body=body).execute()
new_id = result['spreadsheetId']
```

### 4.2 明細報表的空行問題

從 `.xlsx` 下載的明細報表常有大量空行（只有流水號但無內容）。

**過濾方法**：只保留有「主題」欄位的行。

```python
filtered = [row for row in all_rows if row[2].strip()]  # row[2] = 主題
for i, row in enumerate(filtered, 1):
    row[0] = str(i)  # 重新編號
```

### 4.3 RSS 日期解析

Google News RSS 的 `pubDate` 格式：`Mon, 23 Feb 2026 08:00:00 GMT`

```python
import re

def parse_rss_date(d):
    months = {'Jan':'01','Feb':'02','Mar':'03','Apr':'04','May':'05','Jun':'06',
              'Jul':'07','Aug':'08','Sep':'09','Oct':'10','Nov':'11','Dec':'12'}
    m = re.match(r'\w+,\s+(\d+)\s+(\w+)\s+(\d+)', d)
    if m:
        day = m.group(1).zfill(2)
        mon = months.get(m.group(2), '01')
        year = m.group(3)
        return f"{year}-{mon}-{day}"
    return ''
```

### 4.4 OAuth scope 注意事項

- `https://www.googleapis.com/auth/spreadsheets`：讀寫 Sheets（建立新 Sheet 也需要）
- `https://www.googleapis.com/auth/drive.readonly`：讀取 Drive 上的 `.xlsx` 檔案
- 完整 `drive` scope 才能修改 Drive 上的檔案

**建議**：建立新的 native Sheet 只需 `spreadsheets` scope，不需要 `drive` 寫入權限。

---

## 五、檢核清單

修正完成後的檢核事項：

- [ ] 統計報表的新聞稿數量與客戶清單一致
- [ ] 明細報表的文章數量加總等於統計報表的數字
- [ ] 明細報表沒有空行（每行都有主題、標題、連結）
- [ ] 明細報表日期欄沒有空白
- [ ] 開工優惠類已正確拆分
- [ ] 社群 vs 新聞分類正確
- [ ] 原生 vs 轉載標記正確
- [ ] 流水號連續（從 1 開始無斷號）
