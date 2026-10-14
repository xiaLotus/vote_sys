"""Query the latest K11 8F machine states and send them as an HTML table."""

from __future__ import annotations

import argparse
import html
import os
import re
import smtplib
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

import pandas as pd
from sqlalchemy import URL, create_engine, text


BUILDING = "K11"
FLOOR = "8F"
ORDER_BY_COLUMN = os.getenv("MACHINE_STATUS_ORDER_COLUMN", "id")


def database_url() -> URL:
    """Build the connection URL without keeping database credentials in source."""
    user = os.environ["MACHINE_DB_USER"]
    password = os.environ["MACHINE_DB_PASSWORD"]
    host = os.getenv("MACHINE_DB_HOST", "10.11.104.247")
    port = os.getenv("MACHINE_DB_PORT", "3306")
    database = os.getenv("MACHINE_DB_NAME", "a3cim_department")
    return URL.create(
        "mysql+pymysql",
        username=user,
        password=password,
        host=host,
        port=int(port),
        database=database,
        query={"charset": "utf8mb4"},
    )


def latest_status_query(order_by_column: str = ORDER_BY_COLUMN):
    """Return a parameterized query for each station's latest status."""
    # SQL parameters cannot represent identifiers, so only accept a plain column name.
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", order_by_column):
        raise ValueError("MACHINE_STATUS_ORDER_COLUMN must be a valid column name")

    return text(
        f"""
        WITH RankedStatus AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY station ORDER BY {order_by_column} DESC
                   ) AS rn
            FROM machine_monitoring.machine_status
            WHERE building = :building AND floor = :floor
        )
        SELECT * FROM RankedStatus WHERE rn = 1
        ORDER BY station
        """
    )


def load_latest_status() -> pd.DataFrame:
    """Load the latest status for every station on the configured floor."""
    engine = create_engine(database_url(), pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            frame = pd.read_sql_query(
                latest_status_query(),
                connection,
                params={"building": BUILDING, "floor": FLOOR},
            )
    finally:
        engine.dispose()
    return frame.drop(columns=["rn"], errors="ignore")


def render_html(frame: pd.DataFrame) -> str:
    """Render a complete, email-client-friendly HTML report."""
    safe_building = html.escape(BUILDING)
    safe_floor = html.escape(FLOOR)
    if frame.empty:
        table_or_message = '<p class="empty">目前沒有符合條件的站點資料。</p>'
    else:
        table_or_message = frame.to_html(
            index=False,
            border=0,
            classes="status-table",
            justify="center",
            escape=True,
        )

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <style>
    body {{ color: #1f2937; font-family: Arial, "Microsoft JhengHei", sans-serif; }}
    .report {{ margin: 0 auto; max-width: 1000px; }}
    h2 {{ color: #1d4ed8; margin-bottom: 6px; }}
    .summary {{ color: #4b5563; margin: 0 0 16px; }}
    .status-table {{ border-collapse: collapse; width: 100%; }}
    .status-table th {{ background: #2563eb; color: #fff; padding: 10px 8px; }}
    .status-table td {{ border: 1px solid #d1d5db; padding: 8px; text-align: center; }}
    .status-table tr:nth-child(even) {{ background: #f3f4f6; }}
    .empty {{ background: #f3f4f6; padding: 16px; }}
  </style>
</head>
<body>
  <div class="report">
    <h2>{safe_building} {safe_floor} Station 最新狀態</h2>
    <p class="summary">共 {len(frame)} 個 Station</p>
    {table_or_message}
  </div>
</body>
</html>"""


def save_html(frame: pd.DataFrame, output_path: str) -> None:
    """Write the report to a UTF-8 HTML file that can be opened in a browser."""
    with open(output_path, "w", encoding="utf-8") as output_file:
        output_file.write(render_html(frame))


def _addresses(value: str) -> list[str]:
    return [address.strip() for address in value.split(",") if address.strip()]


def send_mail(frame: pd.DataFrame) -> None:
    """Email a status frame using settings supplied through environment variables."""
    sender = os.getenv("STATUS_MAIL_FROM", "Purchase_Can@aseglobal.com")
    sender_name = os.getenv("STATUS_MAIL_FROM_NAME", "請購專用信件")
    to = _addresses(os.environ["STATUS_MAIL_TO"])
    cc = _addresses(os.getenv("STATUS_MAIL_CC", ""))
    if not to:
        raise ValueError("STATUS_MAIL_TO must contain at least one recipient")

    message = MIMEMultipart("alternative")
    message["From"] = formataddr((str(Header(sender_name, "utf-8")), sender))
    message["To"] = ", ".join(to)
    if cc:
        message["Cc"] = ", ".join(cc)
    message["Subject"] = str(Header(f"{BUILDING} {FLOOR} Station 最新狀態", "utf-8"))
    message.attach(MIMEText(render_html(frame), "html", "utf-8"))

    smtp_host = os.getenv("STATUS_SMTP_HOST", "10.12.10.31")
    smtp_port = int(os.getenv("STATUS_SMTP_PORT", "25"))
    with smtplib.SMTP(smtp_host, smtp_port) as smtp:
        smtp.sendmail(sender, to + cc, message.as_string())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="產生 K11 8F Station 最新狀態 HTML 報表")
    parser.add_argument(
        "--output",
        default="K11_8F_Station_Latest.html",
        help="HTML 預覽檔輸出位置（預設：%(default)s）",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="同時透過 SMTP 寄出報表；未指定時只產生 HTML 預覽檔",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    status_frame = load_latest_status()
    print(f"成功查詢到 {BUILDING} {FLOOR} 共 {len(status_frame)} 個 Station 的最新狀態")
    save_html(status_frame, arguments.output)
    print(f"HTML 報表已儲存至 {arguments.output}，可直接用瀏覽器開啟")
    if arguments.send:
        send_mail(status_frame)
        print("郵件發送成功")
