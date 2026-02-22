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
# Chrome設定
# =========================
USER_HOME = os.path.expanduser("~")
CHROME_PROFILE_DIR = os.path.join(USER_HOME, "eo_selenium_profile")
os.makedirs(CHROME_PROFILE_DIR, exist_ok=True)

options = Options()
options.add_argument("--window-size=1200,900")
options.add_argument(f"--user-data-dir={CHROME_PROFILE_DIR}")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options,
)

driver.execute_script(
    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
)

wait = WebDriverWait(driver, 20)


# =========================
# ログイン
# =========================
def login():
    driver.get(config.LOGIN_URL)
    time.sleep(5)


# =========================
# 一覧へ
# =========================
def go_to_myorder_list():
    driver.get(config.MYORDER_LIST_URL)
    wait.until(EC.presence_of_element_located((By.XPATH, "//input[@value='詳細']")))


# =========================
# 詳細解析
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
# 取得
# =========================
def fetch_all_orders():
    results = []

    buttons = driver.find_elements(By.XPATH, "//input[@value='詳細']")
    total = len(buttons)

    for i in range(total):

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
def save_to_csv(results):

    filename = "eo_myorder_list.csv"

    with open(filename, "w", newline="", encoding="cp932") as f:
        writer = csv.writer(f)

        writer.writerow(
            [
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
        )

        for r in results:
            writer.writerow(
                [
                    r["オーダーID"],
                    r["管理番号"],
                    r["案件名"],
                    r["start"].strftime("%Y/%m/%d %H:%M"),
                    r["end"].strftime("%Y/%m/%d %H:%M"),
                    r["都道府県"],
                    r["市区町村"],
                    r["受注前備考"],
                    r["URL"],
                ]
            )

    return filename


# =========================
# メイン
# =========================
def main():
    try:
        login()
        go_to_myorder_list()

        results = fetch_all_orders()

        if results:
            csv_path = save_to_csv(results)

            from calendar_importer import sync_orders_to_calendar

            sync_orders_to_calendar(results)

            # CSV削除
            if os.path.exists(csv_path):
                os.remove(csv_path)

        else:
            print("データなし")

    finally:
        driver.get("about:blank")
        time.sleep(2)
        driver.quit()


if __name__ == "__main__":
    main()
