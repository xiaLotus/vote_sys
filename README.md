# vote_sys

## Station 狀態 HTML 郵件

`machine_status_email.py` 會查詢 K11 8F 每個 Station 的最新狀態、移除 SQL
輔助欄位 `rn`，再將 DataFrame 轉成含樣式的 HTML 表格寄出。資料庫帳密與收件者
不會寫在程式內，執行前請設定環境變數：

```bash
export MACHINE_DB_USER='資料庫帳號'
export MACHINE_DB_PASSWORD='資料庫密碼'
# 以下皆為選填
export MACHINE_DB_HOST='10.11.104.247'
export MACHINE_DB_PORT='3306'
export MACHINE_DB_NAME='a3cim_department'
export MACHINE_STATUS_ORDER_COLUMN='id'
export STATUS_MAIL_CC='cc@example.com'
export STATUS_SMTP_HOST='10.12.10.31'
export STATUS_SMTP_PORT='25'

# 只產生可用瀏覽器直接開啟的 HTML 檔（不寄信）
python machine_status_email.py

# 指定輸出位置
python machine_status_email.py --output report.html

# 如需寄信，再設定收件者並加入 --send
export STATUS_MAIL_TO='recipient@example.com'
python machine_status_email.py --send
```

需要安裝 `pandas`、`SQLAlchemy` 與 `PyMySQL`。HTML 儲存格預設會跳脫特殊
字元，避免 Station 或狀態內容被當作 HTML 執行。

### 在開發介面查看程式碼

程式檔位於專案根目錄的 `machine_status_email.py`。可以使用下列任一方式查看：

1. 在左側檔案總管展開專案根目錄，點選 `machine_status_email.py`。
2. 在終端機執行 `sed -n '1,240p' machine_status_email.py`，直接輸出完整程式碼。
3. 在 GitHub Pull Request 頁面切換到 **Files changed**，再點選
   `machine_status_email.py`。

若要查看程式產生的表格而不是 Python 原始碼，請先執行
`python machine_status_email.py`，再從檔案總管開啟產生的
`K11_8F_Station_Latest.html`。
