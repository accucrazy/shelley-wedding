# Pandora News Scanner — 新聞露出自動掃描系統

## 概述

針對 FamilyMart（全家便利商店）及 7-ELEVEN（統一超商）新聞稿，自動掃描 345 個台灣媒體網站，檢查哪些媒體刊登了相關報導。支援完整的 IO 報表生成與修正流程。

### 為什麼不用瀏覽器自動化？

之前嘗試過的方案全部失敗：
- **Playwright headless 腳本** → Google 封鎖自動化搜尋（CAPTCHA）
- **OpenClaw Browser Relay (Chrome 擴充)** → 不穩定、Agent 常卡死
- **OpenClaw Agent 自己搜** → Agent 宣稱 356 筆但實際只有 1 筆，不可靠

### 現在的方案

**兩階段掃描**，完全脫離瀏覽器：

```
Phase 1: DuckDuckGo API 搜尋     (免費，不被封鎖)
    ↓
    345 個媒體 × N 組關鍵字 → 收集候選
    ↓
Phase 2: Gemini Flash LLM 驗證   (快速、便宜、精準)
    ↓
    批次判斷相關性 + 原生/轉載 → 最終結果
```

## 架構

```
~/.openclaw/skills/pandora-news/
├── SKILL.md                          # OpenClaw skill 定義
├── scripts/
│   ├── pandora_batch_scanner.py      # 核心掃描腳本 ★
│   ├── pandora_news.py               # 舊版（Playwright，不建議用）
│   └── news_cache.py                 # 快取模組
├── venv/                             # Python 虛擬環境（ddgs, httpx, etc.）
└── news_cache.db                     # SQLite 快取

~/Library/LaunchAgents/
└── ai.openclaw.pandora-scanner.plist # macOS 背景服務

輸出：
~/.openclaw/workspace/newscollect/Pandora News IO 0226/
└── 3-Pandora News io/
    ├── 一月/                          # JSON 結果檔
    └── 二月/
```

## 使用方式

### 基本指令

```bash
# 環境變數（方便後續使用）
VENV=~/.openclaw/skills/pandora-news/venv/bin/python
SCAN=~/.openclaw/skills/pandora-news/scripts/pandora_batch_scanner.py

# 完整流程：掃描 → LLM 驗證 → 產 HTML 報表
$VENV $SCAN run --month 一月

# 只掃描（Phase 1）
$VENV $SCAN scan --month 一月

# 只驗證（Phase 2）
$VENV $SCAN verify --month 一月

# 查看進度
$VENV $SCAN status

# 產 HTML 報表
$VENV $SCAN report --month 一月

# 單一任務
$VENV $SCAN run --task 全家草莓季

# 重新開始（清除舊進度）
$VENV $SCAN run --task 全家草莓季 --fresh
```

### 背景執行

```bash
$VENV $SCAN run --month 一月 > /tmp/pandora_scan.log 2>&1 &
disown

# 監看
tail -f /tmp/pandora_scan.log
```

### 用 LaunchAgent 啟動

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ai.openclaw.pandora-scanner.plist
```

## 技術細節

### Phase 1: DuckDuckGo 搜尋

- 使用 `ddgs` Python 套件（DuckDuckGo Search API）
- 每個媒體用 `{關鍵字} site:{domain}` 搜尋
- 聚合平台（LINE TODAY, Yahoo 新聞等）改用 `{關鍵字} {媒體名稱}`
- TLS 1.3 偶爾失敗（Python 3.9 + LibreSSL 限制），自動重試最多 5 次
- 每次搜尋間隔 1.5 秒
- 每 5 個媒體存檔一次，支持斷點續掃

### Phase 2: Gemini Flash LLM 驗證

- 使用 Google Gemini 2.0 Flash API（`GOOGLE_API_KEY` 在 `~/.openclaw/.env`）
- 每 15 筆候選打包成 1 個 prompt，要求 LLM 回 JSON array
- LLM 判斷標準：
  - 必須確實在報導全家便利商店的該活動/產品
  - 只是提到部分字眼但主題不同 → 不相關
  - 論壇閒聊、股票、不相干產業 → 不相關
- 同時判斷原生/轉載

### 效能

| 指標 | 數值 |
|------|------|
| Phase 1 速度 | ~345 媒體 / 15-20 分鐘 |
| Phase 2 速度 | ~342 候選 / 45 秒 |
| 候選 → 通過比例 | 約 15-20% |
| 全月 11 個任務 | 約 3-4 小時 |

### 實測結果（全家草莓季）

- DDG 候選：342 筆
- LLM 通過：66 筆
- 覆蓋媒體：ETtoday、聯合新聞網、三立、中時、上報、華視、LINE TODAY、Dcard、PTT 等

### 輸出格式

JSON 檔案欄位（遵循 PROJECT_SOP.md）：

```json
{
  "新聞": "全家草莓季",
  "日期": "2026-02-28",
  "關鍵字": "全家草莓季 site:ettoday.net",
  "標題": "全家草莓霜淇淋回歸！7-11季節限定甜點一次看",
  "媒體": "ETtoday新聞雲",
  "連結": "https://www.ettoday.net/news/...",
  "原生/轉載": "原生"
}
```

## 新增/修改任務

編輯 `pandora_batch_scanner.py` 裡的 `TASKS_CONFIG`：

```python
TASKS_CONFIG = {
    "全家草莓季": {
        "keywords": ["全家草莓季", "全家 ASAMIMICHAN"],
        "month": "一月",
    },
    # 新增...
}
```

## 7-ELEVEN 同業掃描

除了全家（客戶），也需要掃描 7-ELEVEN（同業）的新聞露出。

### 差異

- 品牌名需覆蓋多種寫法：`7-ELEVEN`、`7-11`、`統一超商`、`711`
- 新聞稿清單來自「同業」Excel：`全家月報_IO檢核_同業202502(含新聞列表).xlsx`
- 搜尋流程相同，但關鍵字設計需注意品牌名變體

---

## IO 報表生成與修正

掃描完成後需生成 IO 報表（統計報表 + 明細報表）並上傳 Google Sheets。

### 常見修正情境

1. **開工優惠拆分**：同一新聞稿多次發稿，需拆開計算各次的露出成效
2. **補掃數據不足**：某些任務的結果明顯偏低，需用 Google News RSS 多關鍵字補掃
3. **缺少新聞稿**：IO 報表的筆數少於客戶清單，需找出並補上遺漏

詳見：
- `IO報表修正流程.md` — 完整的修正流程與技術要點
- `Google_Sheets_API指南.md` — Sheets API 操作指南
- `LOG_二月掃描紀錄.md` — 二月具體修正案例

---

## 文件索引

| 文件 | 說明 |
|------|------|
| `README.md` | 本文件，系統概述 |
| `SKILL.md` | OpenClaw skill 定義 |
| `新聞掃描方法論.md` | 搜尋、篩選、驗證的完整方法論 |
| `IO報表修正流程.md` | IO 報表修正流程與常見情境 |
| `Google_Sheets_API指南.md` | Google Sheets API 操作指南 |
| `LOG_一月掃描紀錄.md` | 一月掃描完整紀錄 |
| `LOG_二月掃描紀錄.md` | 二月掃描完整紀錄 |

---

## 相依服務

| 服務 | 用途 | 位置 |
|------|------|------|
| DuckDuckGo API | 搜尋 | `ddgs` Python 套件（venv 裡） |
| Gemini Flash | LLM 驗證 | `GOOGLE_API_KEY` in `~/.openclaw/.env` |
| Google Sheets API | 結果匯出 + IO 報表 | `~/.openclaw/skills/google-sheets/` |
| Google News RSS | 補掃來源 | 免費，不需 API key |
| 靜態伺服器 | HTML 報表公開 | port 18800, Cloudflare Tunnel |
| openpyxl | .xlsx 讀取 | venv 裡 |

## 疑難排解

### TLS 錯誤 (Unsupported protocol version 0x304)
系統 Python 3.9 + LibreSSL 2.8.3 不完全支持 TLS 1.3。腳本會自動重試（最多 5 次）。
如果頻繁失敗，可考慮用 Homebrew 安裝新版 Python。

### 搜尋結果太少
DuckDuckGo 的索引比 Google 少，某些小眾媒體可能搜不到。
用 Google News RSS 補掃是最有效的方法。也可考慮 Serper.dev API（付費但用 Google 索引）。

### LLM 判斷太嚴格/太寬鬆
修改 `_call_gemini_batch()` 裡的 prompt。

### Google Sheets API 回傳 HttpError 400
目標是 `.xlsx` 格式，API 無法直接修改。需建立新的 native Google Sheet 再寫入。
詳見 `Google_Sheets_API指南.md`。

### 同一新聞稿的數據如何拆分
先從明細報表按文章發布日期切割，再分別計算統計數據。
詳見 `IO報表修正流程.md`。
