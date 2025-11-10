# 維運組術科考試系統

## 📁 檔案結構

```
quiz_system/
├── app.py                  # Flask 後台
├── questions.json          # 題庫 JSON
├── requirements.txt        # Python 套件
├── static/
│   ├── style.css          # CSS 樣式
│   └── script.js          # JavaScript 邏輯
└── templates/
    └── index.html         # HTML 頁面
```

## 🚀 安裝與運行

### 1. 安裝 Flask

```bash
pip install Flask
```

或使用 requirements.txt：

```bash
pip install -r requirements.txt
```

### 2. 運行系統

```bash
python app.py
```

### 3. 開啟瀏覽器

訪問：http://127.0.0.1:5000

## 📋 API 說明

### GET /api/questions
隨機獲取題目（IT 1題 + 軟體 1題）

**回應範例：**
```json
{
  "success": true,
  "questions": [
    {
      "id": 1,
      "分類": "IT",
      "題號": "Q1",
      "主題": "帳號與權限管理",
      "敘述": "...",
      "面向": [...]
    }
  ]
}
```

### POST /api/submit
提交答案並獲取評分

**請求範例：**
```json
{
  "answers": {
    "1": {
      "基本操作/管理流程": "使用者答案...",
      "異常判斷": "使用者答案..."
    }
  },
  "question_ids": [1, 6]
}
```

**回應範例：**
```json
{
  "success": true,
  "final_score": 85.5,
  "results": [...]
}
```

## 🎯 功能特色

✅ Flask 後台 API
✅ 前後端分離架構
✅ 隨機抽題（IT + 軟體）
✅ 題目提示顯示
✅ 自動評分系統
✅ 詳細結果比對

## 📝 題庫格式

題庫使用 `questions.json`，格式如下：

```json
[
  {
    "id": 1,
    "分類": "IT",
    "題號": "Q1",
    "主題": "帳號與權限管理",
    "敘述": "題目描述...",
    "面向": [
      {
        "名稱": "基本操作/管理流程",
        "提示": "作答提示...",
        "解答": "參考答案..."
      }
    ]
  }
]
```

## 🔧 修改抽題規則

在 `app.py` 的 `get_questions()` 函數中修改：

```python
# 目前：IT 1題 + 軟體 1題
it_questions = [q for q in questions if q['分類'] == 'IT']
software_questions = [q for q in questions if q['分類'] == '軟體']

# 可改為其他組合，例如：
# IT、軟體、硬體各1題
```

## ⚠️ 注意事項

- 確保 `questions.json` 與 `app.py` 在同一目錄
- 預設 debug 模式已開啟，生產環境請關閉
- 評分算法在 `calculate_score()` 函數中，可自行調整

## 🌐 瀏覽器支援

- Chrome / Edge (推薦)
- Firefox
- Safari

## 📞 問題排查

**問題：Flask 無法啟動**
- 確認是否已安裝 Flask：`pip install Flask`

**問題：找不到題庫**
- 確認 `questions.json` 與 `app.py` 在同一目錄

**問題：頁面無法載入**
- 確認瀏覽器訪問 http://127.0.0.1:5000
- 檢查 console 是否有錯誤訊息
