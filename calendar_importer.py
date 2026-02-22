import os
import sys
import datetime
import logging
import tkinter as tk
from tkinter import messagebox

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

# =========================
# exe対応
# =========================
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials.json")
TOKEN_PATH = os.path.join(BASE_DIR, "token.json")
LOG_PATH = os.path.join(BASE_DIR, "calendar_sync.log")

# =========================
# ログ設定
# =========================
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


# =========================
# Google接続
# =========================
def get_calendar_service():

    creds = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w", encoding="utf-8") as token:
            token.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


# =========================
# イベント構築
# =========================
def build_event(order):

    return {
        "summary": f"{order['案件名']}（管理:{order['管理番号']} / ID:{order['オーダーID']}）",
        "location": f"{order['都道府県']}{order['市区町村']}",
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
    }


# =========================
# 全イベント取得
# =========================
def fetch_all_google_events(service):

    events = []
    page_token = None

    while True:
        result = (
            service.events()
            .list(
                calendarId="primary",
                singleEvents=True,
                maxResults=2500,
                pageToken=page_token,
            )
            .execute()
        )

        events.extend(result.get("items", []))
        page_token = result.get("nextPageToken")

        if not page_token:
            break

    return events


# =========================
# 完全同期
# =========================
def sync_orders_to_calendar(order_list):

    service = get_calendar_service()

    root = tk.Tk()
    root.withdraw()

    added = updated = deleted = skipped = 0

    events = fetch_all_google_events(service)

    google_dict = {}

    # 既存イベント辞書化
    for ev in events:
        desc = ev.get("description", "")
        for line in desc.splitlines():
            if line.startswith("管理番号:"):
                key = line.replace("管理番号:", "").strip()
                google_dict[key] = ev
                break

    current_keys = set()

    # ======================
    # 追加・更新
    # ======================
    for order in order_list:

        key = order["管理番号"]
        current_keys.add(key)

        new_event = build_event(order)
        existing = google_dict.get(key)

        try:
            # -------- 新規 --------
            if not existing:

                confirm_msg = (
                    f"{order['start'].strftime('%Y/%m/%d %H:%M')}\n"
                    f"{order['案件名']}\n\n"
                    f"登録しますか？"
                )

                if not messagebox.askyesno("登録確認", confirm_msg):
                    skipped += 1
                    continue

                service.events().insert(
                    calendarId="primary",
                    body=new_event,
                ).execute()

                added += 1
                logging.info(f"追加: {key}")
                continue

            # -------- 更新判定 --------
            existing_start = existing["start"].get("dateTime") or existing["start"].get(
                "date"
            )
            existing_end = existing["end"].get("dateTime") or existing["end"].get(
                "date"
            )

            if (
                existing_start != new_event["start"]["dateTime"]
                or existing_end != new_event["end"]["dateTime"]
                or existing.get("summary") != new_event["summary"]
                or existing.get("description") != new_event["description"]
            ):

                service.events().update(
                    calendarId="primary",
                    eventId=existing["id"],
                    body=new_event,
                ).execute()

                updated += 1
                logging.info(f"更新: {key}")
            else:
                skipped += 1

        except Exception as e:
            logging.error(f"エラー({key}): {e}")

    # ======================
    # 削除
    # ======================
    delete_targets = [key for key in google_dict.keys() if key not in current_keys]

    if delete_targets:
        if messagebox.askyesno(
            "削除確認",
            f"{len(delete_targets)}件のイベントを削除しますか？",
        ):
            for key in delete_targets:
                service.events().delete(
                    calendarId="primary",
                    eventId=google_dict[key]["id"],
                ).execute()
                deleted += 1

    messagebox.showinfo(
        "同期完了",
        f"追加: {added}\n更新: {updated}\n削除: {deleted}\n変更なし: {skipped}",
    )
