import datetime
import os
import sys
import tkinter as tk
from tkinter import messagebox

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


# =========================
# Google Calendar 権限
# =========================
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


# =========================
# ★ exe対応：実行ファイルと同じフォルダ取得
# =========================
if getattr(sys, "frozen", False):
    # exe実行時
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # Python実行時
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials.json")
TOKEN_PATH = os.path.join(BASE_DIR, "token.json")


# =========================
# Googleカレンダー接続
# =========================
def get_calendar_service():
    creds = None

    # token.json があれば読み込み
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    # 認証が無効 or 初回実行
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError(
                    f"credentials.json が見つかりません:\n{CREDENTIALS_PATH}"
                )

            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        # token保存
        with open(TOKEN_PATH, "w", encoding="utf-8") as token:
            token.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


# =========================
# カレンダー登録処理
# =========================
def add_orders_to_calendar(order_list):
    service = get_calendar_service()

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    added = 0
    skipped = 0

    for order in order_list:
        try:
            summary = (
                f"{order['案件名']}"
                f"（管理:{order['管理番号']} / ID:{order['オーダーID']}）"
            )

            location = f"{order['都道府県']}{order['市区町村']}"

            confirm_msg = (
                f"日付: {order['start'].strftime('%Y/%m/%d %H:%M')}\n"
                f"案件: {summary}\n"
                f"住所: {location}\n\n"
                f"登録しますか？"
            )

            if not messagebox.askyesno("登録確認", confirm_msg):
                skipped += 1
                continue

            event = {
                "summary": summary,
                "location": location,
                "description": (
                    f"管理番号: {order['管理番号']}\n"
                    f"オーダーID: {order['オーダーID']}\n\n"
                    f"{order['受注前備考']}\n\n"
                    f"{order['URL']}"
                ),
                "start": {
                    "dateTime": order["start"].isoformat(),
                    "timeZone": "Asia/Tokyo",
                },
                "end": {
                    "dateTime": order["end"].isoformat(),
                    "timeZone": "Asia/Tokyo",
                },
                "reminders": {
                    "useDefault": False,
                    "overrides": [
                        {"method": "popup", "minutes": 35},
                        {"method": "email", "minutes": 35},
                    ],
                },
            }

            service.events().insert(calendarId="primary", body=event).execute()

            added += 1

        except Exception as e:
            print("[ERROR]", e)
            skipped += 1

    messagebox.showinfo(
        "完了",
        f"登録完了\n新規: {added}件\nスキップ: {skipped}件",
    )
