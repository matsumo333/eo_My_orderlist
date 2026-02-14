import os
import time
import re
import csv
from datetime import datetime, timedelta

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

import config


# =========================
# Chromeプロファイル保存
# =========================
BASE_DIR = os.getcwd()
CHROME_PROFILE_DIR = os.path.join(BASE_DIR, "selenium_profile")
os.makedirs(CHROME_PROFILE_DIR, exist_ok=True)

options = Options()
options.add_argument("--window-size=1200,900")
options.add_argument(f"--user-data-dir={CHROME_PROFILE_DIR}")

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options,
)

wait = WebDriverWait(driver, 20)


# =========================
# ログイン
# =========================
def login():
    print("[1] ログインページへ")
    driver.get(config.LOGIN_URL)
    time.sleep(2)

    if "menu/menu.asp" in driver.current_url:
        print("[OK] 既にログイン済み")
        return

    print("👉 初回のみ手動ログインしてください")
    wait.until(EC.url_contains("menu/menu.asp"))
    print("[OK] ログイン成功")


# =========================
# 受注済一覧へ
# =========================
def go_to_myorder_list():
    print("[2] 受注済一覧へ移動")
    driver.get(config.MYORDER_LIST_URL)

    wait.until(EC.presence_of_element_located((By.XPATH, "//input[@value='詳細']")))

    print("[OK] 受注済一覧表示")


# =========================
# 詳細ページ解析
# =========================
def parse_detail_page():

    def get_value(label):
        try:
            element = driver.find_element(
                By.XPATH,
                f"//td[contains(normalize-space(), '{label}')]/following-sibling::td[1]",
            )
            return element.text.strip()
        except:
            return ""

    visit_date_raw = get_value("訪問予定日")
    if not visit_date_raw:
        print("⚠ 訪問予定日取得失敗")
        return None

    visit_date = visit_date_raw.split()[0]
    time_zone = get_value("訪問予定時間帯")
    note = get_value("受注前備考")

    end_match = re.search(r"【工事終了目安】\s*(\d{1,2}:\d{2})", note)
    end_time = end_match.group(1) if end_match else None

    if end_time:
        start_dt = datetime.strptime(f"{visit_date} {end_time}", "%Y/%m/%d %H:%M")
        end_dt = start_dt + timedelta(hours=1)
    else:
        if "午前" in time_zone:
            start_dt = datetime.strptime(f"{visit_date} 09:00", "%Y/%m/%d %H:%M")
            end_dt = datetime.strptime(f"{visit_date} 12:00", "%Y/%m/%d %H:%M")
        elif "午後" in time_zone:
            start_dt = datetime.strptime(f"{visit_date} 13:00", "%Y/%m/%d %H:%M")
            end_dt = datetime.strptime(f"{visit_date} 17:00", "%Y/%m/%d %H:%M")
        else:
            start_dt = datetime.strptime(f"{visit_date} 09:00", "%Y/%m/%d %H:%M")
            end_dt = datetime.strptime(f"{visit_date} 17:00", "%Y/%m/%d %H:%M")

    return {
        "オーダーID": get_value("オーダーＩＤ"),
        "管理番号": get_value("管理番号"),
        "案件名": get_value("案件名称"),
        "start": start_dt,
        "end": end_dt,
        "都道府県": get_value("訪問先住所（都道府県）"),
        "市区町村": get_value("訪問先住所（市区町村）"),
        "受注前備考": note,
        "URL": driver.current_url,
    }


# =========================
# 詳細取得
# =========================
def fetch_all_orders():
    print("[3] 詳細を順番に取得")

    results = []

    buttons = driver.find_elements(By.XPATH, "//input[@value='詳細']")
    total = len(buttons)

    for i in range(total):
        print(f"--- {i+1} 件目 ---")

        buttons = driver.find_elements(By.XPATH, "//input[@value='詳細']")
        onclick = buttons[i].get_attribute("onclick")

        driver.execute_script(onclick)

        wait.until(lambda d: "view.asp" in d.current_url)
        wait.until(EC.presence_of_element_located((By.XPATH, "//form")))

        data = parse_detail_page()
        if data:
            results.append(data)

        driver.get(config.MYORDER_LIST_URL)
        wait.until(EC.presence_of_element_located((By.XPATH, "//input[@value='詳細']")))

    return results


# =========================
# CSV保存
# =========================
def save_to_csv(order_list):

    if not order_list:
        print("保存するデータがありません")
        return

    filename = f"orders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    fieldnames = [
        "オーダーID",
        "管理番号",
        "案件名",
        "開始日時",
        "終了日時",
        "都道府県",
        "市区町村",
        "受注前備考",
        "URL",
    ]

    with open(filename, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for order in order_list:
            writer.writerow(
                {
                    "オーダーID": order["オーダーID"],
                    "管理番号": order["管理番号"],
                    "案件名": order["案件名"],
                    "開始日時": order["start"].strftime("%Y-%m-%d %H:%M"),
                    "終了日時": order["end"].strftime("%Y-%m-%d %H:%M"),
                    "都道府県": order["都道府県"],
                    "市区町村": order["市区町村"],
                    "受注前備考": order["受注前備考"],
                    "URL": order["URL"],
                }
            )

    print(f"[OK] CSV保存完了: {filename}")


# =========================
# メイン
# =========================
def main():
    try:
        login()
        go_to_myorder_list()

        results = fetch_all_orders()

        if results:
            save_to_csv(results)

        print("[OK] 全処理完了")

    except Exception:
        import traceback

        print("❌ エラー発生")
        traceback.print_exc()

    finally:
        time.sleep(3)
        driver.quit()


if __name__ == "__main__":
    main()
