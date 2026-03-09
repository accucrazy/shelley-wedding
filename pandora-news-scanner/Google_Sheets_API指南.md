# Google Sheets API 操作指南

> 搭配 Pandora News Scanner 使用的 Google Sheets 自動化操作指南。

---

## 一、環境設定

### 1.1 認證檔案

```
~/.openclaw/skills/google-sheets/
├── oauth_credentials.json     # Google Cloud Console 下載的 OAuth 憑證
├── token.json                 # 授權後自動產生的 refresh token
├── venv_new/                  # Python 虛擬環境
└── scripts/
    └── sheets_tools.py        # 共用工具
```

### 1.2 安裝依賴

```bash
cd ~/.openclaw/skills/google-sheets
python3 -m venv venv_new
./venv_new/bin/pip3 install google-api-python-client google-auth google-auth-oauthlib openpyxl
```

### 1.3 OAuth Scopes

| Scope | 用途 |
|-------|------|
| `spreadsheets` | 讀寫 Google Sheets（含建立新 Sheet） |
| `drive.readonly` | 讀取 Drive 上的 `.xlsx` 檔案 |
| `drive` | 完整 Drive 讀寫（通常不需要） |

建議只用 `spreadsheets` + `drive.readonly`。

---

## 二、基本操作

### 2.1 取得 Service

```python
import os, json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
CRED_DIR = os.path.expanduser('~/.openclaw/skills/google-sheets')

def get_service():
    token_path = os.path.join(CRED_DIR, 'token.json')
    cred_path = os.path.join(CRED_DIR, 'oauth_credentials.json')
    creds = None

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(cred_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, 'w') as f:
            f.write(creds.to_json())

    return build('sheets', 'v4', credentials=creds)
```

### 2.2 讀取資料

```python
service = get_service()
result = service.spreadsheets().values().get(
    spreadsheetId=SHEET_ID,
    range='統計報表!A1:G20'
).execute()
rows = result.get('values', [])
```

### 2.3 寫入資料

```python
service.spreadsheets().values().update(
    spreadsheetId=SHEET_ID,
    range='統計報表!A1',
    valueInputOption='USER_ENTERED',
    body={'values': [header] + rows}
).execute()
```

### 2.4 建立新 Sheet

```python
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
new_url = result['spreadsheetUrl']
```

### 2.5 清空分頁

```python
service.spreadsheets().values().clear(
    spreadsheetId=SHEET_ID,
    range='明細報表!A:Z'
).execute()
```

### 2.6 新增/刪除分頁

```python
# 新增
service.spreadsheets().batchUpdate(
    spreadsheetId=SHEET_ID,
    body={'requests': [{'addSheet': {'properties': {'title': '新分頁'}}}]}
).execute()
```

---

## 三、.xlsx 檔案處理

### 3.1 為什麼不能直接修改 .xlsx

Google Sheets API 對 Drive 上的 `.xlsx` 格式回傳：
```
HttpError 400: This operation is not supported for this document
```

原因：API 的 `values.update` 只支援 native Google Sheets 格式。

### 3.2 處理方法：下載 → 本地修改 → 上傳新 Sheet

```python
# 1. 用 Drive API 下載 .xlsx
from googleapiclient.discovery import build as drive_build
drive = drive_build('drive', 'v3', credentials=creds)
request = drive.files().get_media(fileId=FILE_ID)
with open('/tmp/download.xlsx', 'wb') as f:
    f.write(request.execute())

# 2. 用 openpyxl 讀取
import openpyxl
wb = openpyxl.load_workbook('/tmp/download.xlsx')
ws = wb['統計報表']
for row in ws.iter_rows(min_row=2, values_only=True):
    print(row)

# 3. 建立新 native Sheet 並寫入修改後的資料
# （見上方 2.4）
```

### 3.3 從 Google Drive URL 取得 File ID

```
https://docs.google.com/spreadsheets/d/{FILE_ID}/edit...

範例：
URL: https://docs.google.com/spreadsheets/d/1Jd1uMSqpM4_oZ3fDBSPhkd3n_m1q4RKm/edit
File ID: 1Jd1uMSqpM4_oZ3fDBSPhkd3n_m1q4RKm
```

---

## 四、IO 報表專用操作

### 4.1 寫入統計報表

```python
header = ['新聞標題', '發稿日期', '發稿編號',
          '新聞頻道數', '新聞總主文數', '社群頻道數', '社群總主文數']

rows = []
for task in tasks:
    rows.append([
        task['title'], task['date'], task['id'],
        task['news_ch'], task['news_art'],
        task['social_ch'], task['social_posts'],
    ])

# 加上合計行
rows.append(['合計', '', '',
    sum(t['news_ch'] for t in tasks),
    sum(t['news_art'] for t in tasks),
    sum(t['social_ch'] for t in tasks),
    sum(t['social_posts'] for t in tasks),
])

service.spreadsheets().values().update(
    spreadsheetId=SHEET_ID,
    range='統計報表!A1',
    valueInputOption='USER_ENTERED',
    body={'values': [header] + rows}
).execute()
```

### 4.2 寫入明細報表

```python
header = ['編號', '發布時間', '主題', '新聞標題', '網站', '連結', '作者', '原生/轉載']

rows = []
for i, article in enumerate(all_articles, 1):
    rows.append([
        str(i),
        article['date'],
        article['topic'],
        article['title'],
        article['media'],
        article['url'],
        article.get('author', ''),
        article['native_or_repost'],
    ])

service.spreadsheets().values().update(
    spreadsheetId=SHEET_ID,
    range='明細報表!A1',
    valueInputOption='USER_ENTERED',
    body={'values': [header] + rows}
).execute()
```

---

## 五、實用 Sheet ID 一覽

| 用途 | Sheet ID | 備註 |
|------|----------|------|
| Pandora 掃描結果 | `1hh6wOIny3CwPB4bIVUPV7mtXNijijE2jN-p8zVK9qcU` | 掃描原始資料 |
| 全家二月 IO（修正版） | `1JDfpVMl0WlzuN5w-Az0kOliQZxG8rEy8b20hOTy0uK0` | 2026-03-07 修正 |
| 7-11 二月 IO（修正版） | `1YnKlrApibl8hz6eAsClgSMcdCSLD2FyqVxIRXLryx7s` | 2026-03-05 修正 |

---

## 六、疑難排解

### RefreshError: invalid_scope
`token.json` 的 scope 不足。刪除 `token.json` 重新授權。

### HttpError 400: This operation is not supported
目標是 `.xlsx` 格式。需建立新的 native Google Sheet。

### HttpError 403: insufficient permissions
需要 `drive` scope 而非只有 `drive.readonly`。或者改用建立新 Sheet 的方法（只需 `spreadsheets` scope）。

### ETIMEDOUT on launchctl restart
Gateway 的 full process restart 有時會超時。會自動 fallback 到 in-process restart。
