import requests
import sqlite3
import time
import json
import csv
import re
from datetime import datetime

URL = "https://www.gov.taipei/OpenData.aspx?SN=DD102593FDB1A032"
DB_NAME = "events.db"


def fetch_data():
    headers = {"User-Agent": "Mozilla/5.0"}

    for i in range(3):
        try:
            response = requests.get(
                URL,
                headers=headers,
                timeout=(10, 60),
                verify=False
                )
            response.encoding = "utf-8-sig"
            response.raise_for_status()
            return json.loads(response.text)

        except requests.exceptions.RequestException as e:
            print(f"第 {i + 1} 次抓取失敗：{e}")
            time.sleep(3)

        except Exception as e:
            print(f"第 {i + 1} 次解析失敗：{e}")
            time.sleep(3)

    raise Exception("連續 3 次抓取失敗，請稍後再試。")


def clean_display_time(text):
    if not text:
        return "時間未提供"

    stop_words = [
        "活動對象", "參加對象", "活動地點", "地點",
        "活動內容", "參加辦法", "報名方式", "交通資訊",
        "備註", "洽詢電話", "電話", "主講人"
    ]

    for word in stop_words:
        if word in text:
            text = text.split(word)[0]

    text = text.replace("&nbsp;", " ")
    text = " ".join(text.split())

    return text.strip(" ：:，,。")


def extract_display_time(item):
    title = item.get("title", "")
    content = item.get("內容", "")
    text = title + " " + content

    patterns = [
        r"活動時間[：:]\s*([^。；\n]+)",
        r"活動日期[：:]\s*([^。；\n]+)",
        r"講座日期[：:]\s*([^。；\n]+)",
        r"講座時間[：:]\s*([^。；\n]+)",
        r"辦理時間[：:]\s*([^。；\n]+)",
        r"時間[：:]\s*([^。；\n]+)",
        r"日期[：:]\s*([^。；\n]+)"
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return clean_display_time(match.group(1))

    start_time = item.get("活動開始時間", "")
    end_time = item.get("活動結束時間", "")

    if start_time and end_time:
        return f"{start_time} - {end_time}"

    return "時間未提供"


def classify_event(item):
    text = " ".join(str(v) for v in item.values())

    exception = [
        "祖孫", "65歲以上", "長者", "銀髮", "樂齡", "高齡"
    ]

    exclude = [
        "就業", "徵才", "職缺", "招募", "求職", "面試",
        "就服站", "就業服務處", "現場徵才", "微型徵才",
        "成年禮", "16-18歲", "青少年",
        "兒童", "幼兒", "小朋友", "學童限定", "學生限定",
        "親子限定",
        "交通管制", "道路管制", "公車改道",
        "競賽", "考試"
    ]

    if any(k in text for k in exception):
        return "include"

    if any(k in text for k in exclude):
        return "exclude"

    return "include"


def parse_datetime(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def get_event_status(start_time, end_time):
    now = datetime.now()

    start_dt = parse_datetime(start_time)
    end_dt = parse_datetime(end_time)

    # 例如結束日期是 2050，代表長期公告，不當作一般活動日期顯示
    if end_dt and end_dt.year >= 2030:
        return "long_term"

    if end_dt and end_dt < now:
        return "expired"

    if start_dt and start_dt >= now:
        return "upcoming"

    if start_dt and end_dt and start_dt <= now <= end_dt:
        return "ongoing"

    return "unknown"


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS events (
        DataSN TEXT PRIMARY KEY,
        title TEXT,
        content TEXT,
        display_time TEXT,
        start_time TEXT,
        end_time TEXT,
        publisher TEXT,
        category TEXT,
        source_url TEXT,
        senior_type TEXT,
        status TEXT,
        first_seen_at TEXT,
        updated_at TEXT
    )
    """)

    conn.commit()
    conn.close()


def save_events(data):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    inserted_count = 0
    updated_count = 0

    for item in data:
        data_sn = item.get("DataSN", "")
        if not data_sn:
            continue

        title = item.get("title", "")
        content = item.get("內容", "")
        display_time = extract_display_time(item)
        start_time = item.get("活動開始時間", "")
        end_time = item.get("活動結束時間", "")
        publisher = item.get("發布單位", "")
        source_url = item.get("Source", "")

        senior_type = classify_event(item)
        status = get_event_status(start_time, end_time)

        category = item.get("類別", "")
        if isinstance(category, list):
            category = "、".join(category)

        cur.execute("SELECT DataSN FROM events WHERE DataSN = ?", (data_sn,))
        exists = cur.fetchone()

        if exists:
            cur.execute("""
            UPDATE events
            SET
                title = ?,
                content = ?,
                display_time = ?,
                start_time = ?,
                end_time = ?,
                publisher = ?,
                category = ?,
                source_url = ?,
                senior_type = ?,
                status = ?,
                updated_at = ?
            WHERE DataSN = ?
            """, (
                title,
                content,
                display_time,
                start_time,
                end_time,
                publisher,
                category,
                source_url,
                senior_type,
                status,
                now_text,
                data_sn
            ))
            updated_count += 1

        else:
            cur.execute("""
            INSERT INTO events (
                DataSN,
                title,
                content,
                display_time,
                start_time,
                end_time,
                publisher,
                category,
                source_url,
                senior_type,
                status,
                first_seen_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data_sn,
                title,
                content,
                display_time,
                start_time,
                end_time,
                publisher,
                category,
                source_url,
                senior_type,
                status,
                now_text,
                now_text
            ))
            inserted_count += 1

    conn.commit()
    conn.close()

    return inserted_count, updated_count


def refresh_expired_status():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("SELECT DataSN, start_time, end_time FROM events")
    rows = cur.fetchall()

    for data_sn, start_time, end_time in rows:
        status = get_event_status(start_time, end_time)
        cur.execute(
            "UPDATE events SET status = ? WHERE DataSN = ?",
            (status, data_sn)
        )

    conn.commit()
    conn.close()


def write_csv(filename, headers, rows):
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def export_csv():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    SELECT
        DataSN,
        title,
        display_time,
        start_time,
        end_time,
        publisher,
        category,
        senior_type,
        status,
        source_url,
        updated_at
    FROM events
    ORDER BY start_time
    """)

    rows = cur.fetchall()
    conn.close()

    headers = [
        "DataSN",
        "title",
        "display_time",
        "start_time",
        "end_time",
        "publisher",
        "category",
        "senior_type",
        "status",
        "source_url",
        "updated_at"
    ]

    senior_rows = [
        row for row in rows
        if row[7] == "include"
        and row[8] in ["upcoming", "ongoing", "unknown"]
    ]

    excluded_rows = [
        row for row in rows
        if row[7] == "exclude"
    ]

    expired_rows = [
        row for row in rows
        if row[8] == "expired"
    ]

    write_csv("all_events.csv", headers, rows)
    write_csv("senior_events.csv", headers, senior_rows)
    write_csv("excluded_events.csv", headers, excluded_rows)
    write_csv("expired_events.csv", headers, expired_rows)

    print(f"all_events.csv：{len(rows)} 筆")
    print(f"senior_events.csv：{len(senior_rows)} 筆")
    print(f"excluded_events.csv：{len(excluded_rows)} 筆")
    print(f"expired_events.csv：{len(expired_rows)} 筆")


def run_crawler():
    print("開始抓取台北市活動資料...")

    data = fetch_data()
    print(f"成功取得 {len(data)} 筆資料")

    init_db()

    inserted_count, updated_count = save_events(data)

    refresh_expired_status()
    export_csv()

    print(f"新增 {inserted_count} 筆")
    print(f"更新 {updated_count} 筆")
    print("資料庫更新完成")



if __name__ == "__main__":
    run_crawler()