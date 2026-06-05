# app.py (運算、API、資料庫與排程)
import csv
import math
import os
import re
import sqlite3
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from crawler import run_crawler
import requests

# 記錄使用者的臨時狀態 (park 或 place)
user_state = {}
user_seen_events = {}
has_active_today = {}

# 🕒 1. 保持自動排程更新 SQLite 資料庫
def scheduled_crawler_job():
    try:
        run_crawler()
        user_seen_events.clear()
        print("✅ 爬蟲背景更新完成，已清空使用者看過的紀錄。")
    except Exception as e:
        print("⚠️ 排程爬蟲失敗：", e)

scheduler = BackgroundScheduler()
scheduler.start()


# Google Maps API 金鑰與檔案路徑
GOOGLE_MAPS_API_KEY = "AIzaSyD08cCeJKAlJUquS9AbPgQ-ek0riMWr2Go"
PLACE_CSV = "final_welfare_with_geo.csv"


def haversine_distance(lat1, lon1, lat2, lon2):
    r = 6371
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return r * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

# ─── 📌 功能一：搜尋附近活動據點 ───
def search_nearby_places(user_lat, user_lng, limit=5):
    places = []
    if not os.path.exists(PLACE_CSV):
        return []
    with open(PLACE_CSV, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                place_lat = float(row["latitude"])
                place_lng = float(row["longitude"])
            except Exception:
                continue
            row["distance"] = haversine_distance(user_lat, user_lng, place_lat, place_lng)
            places.append(row)
    places.sort(key=lambda x: x["distance"])
    return places[:limit]

def format_places_message(places):
    if not places: return "附近目前找不到活動據點。"
    lines = ["幫您找到附近的活動據點：", ""]
    for i, place in enumerate(places, start=1):
        lines.extend([
            f"{i}. {place.get('name', '未提供')}",
            f"類型：{place.get('category', '未提供')}",
            f"距離：約 {place.get('distance', 0):.1f} 公里",
            f"地址：{place.get('address', '未提供')}",
            f"電話：{place.get('phone', '未提供')}\n"
        ])
    lines.append("小提醒：建議出發前先電話確認服務時間。")
    return "\n".join(lines)

# ─── 🌳 功能二：搜尋附近公園（Google Maps API） ───
def search_nearby_parks(latitude, longitude):
    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location,places.rating,places.googleMapsUri"
    }
    payload = {
        "includedTypes": ["park"], "maxResultCount": 5, "languageCode": "zh-TW",
        "rankPreference": "DISTANCE",
        "locationRestriction": {"circle": {"center": {"latitude": latitude, "longitude": longitude}, "radius": 1500.0}}
    }
    response = requests.post(url, headers=headers, json=payload, timeout=10)
    
    # 安全檢查
    try:
        data = response.json()
        
        if not isinstance(data, dict):
            return []
        return data.get("places", [])  
    except Exception as e:
        print("解析 Google JSON 失敗:", e)
        return []
    
def format_parks_message(parks):
    if not parks: 
        return "附近 1.5 公里內目前找不到公園喔。"
        
    lines = ["🌳 幫您找到附近適合散步的公園："]
    
    for i, park in enumerate(parks, start=1):
        name = park.get("displayName", {}).get("text", "未命名公園")
        address = park.get("formattedAddress", "地址未提供")
        maps_url = park.get("googleMapsUri", "")
        
        lines.append(
            f"\n{i}. {name}\n"
            f"📍 地址：{address}\n"
            f"🗺️ 地圖導航：{maps_url}"
        )
        
    return "\n".join(lines)
    
def build_senior_events_message(user_id):
    events = get_senior_events(user_id, limit=5)

    if not events:
        return (
            "目前沒有新的活動可以推薦囉。\n\n"
            "您可以點選「重新檢視」再看一次，或點擊「活動查詢網站」查看更多活動：\n",
            False
        )

    if user_id not in user_seen_events:
        user_seen_events[user_id] = set()

    lines = [
        "👵 幫您整理好近期適合參加的活動囉：",
        ""
    ]

    for i, event in enumerate(events, start=1):
        data_sn, title, display_time, publisher, source_url, status, start_time, end_time = event

       
        user_seen_events[user_id].add(data_sn)

        lines.append(f"{i}. {title}")
        lines.append(f"📅 日期：{format_event_date(display_time, status, start_time, end_time)}")
        lines.append(f"🏢 主辦：{publisher or '未提供'}")
        lines.append(f"🔗 詳情連結：{source_url}")
        lines.append("")

    lines.append("想看其他活動的話，可以點選「換一批活動」。")
    lines.append("💡 小提醒：出門前記得先點官方連結確認喔！")

    return "\n".join(lines), True
    
def get_senior_events(user_id, limit=5):
    seen_ids = user_seen_events.get(user_id, set())


    conn = sqlite3.connect("events.db")
    cur = conn.cursor()

    if seen_ids:
        placeholders = ",".join(["?"] * len(seen_ids))
        query = f"""
        SELECT DataSN, title, display_time, publisher, source_url, status, start_time, end_time 
        FROM events 
        WHERE senior_type = 'include' 
          AND status IN ('upcoming', 'ongoing', 'unknown', 'long_term') 
          AND DataSN NOT IN ({placeholders}) 
        ORDER BY CASE WHEN status = 'long_term' THEN 1 ELSE 0 END, start_time 
        LIMIT ?
        """
        params = list(seen_ids) + [limit]
    else:
        query = """
        SELECT DataSN, title, display_time, publisher, source_url, status, start_time, end_time 
        FROM events 
        WHERE senior_type = 'include' 
          AND status IN ('upcoming', 'ongoing', 'unknown', 'long_term') 
        ORDER BY CASE WHEN status = 'long_term' THEN 1 ELSE 0 END, start_time 
        LIMIT ?
        """
        params = [limit]

    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()

    return rows

    
def format_event_date(display_time, status, start_time=None, end_time=None):
    if status == "long_term":
        return "請點官方連結查看最新資訊"

    text = str(display_time or "").strip()
    iso_range = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\s*-\s*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", text)

    if iso_range:
        start_date = format_iso_datetime(iso_range.group(1))
        end_date = format_iso_datetime(iso_range.group(2))
        return start_date if start_date == end_date else f"{start_date}至{end_date}"

    chinese_range = re.search(r"\d{1,2}月\d{1,2}日\s*[至到~-]\s*\d{1,2}月\d{1,2}日", text)
    if chinese_range:
        return chinese_range.group(0).replace(" ", "")

    chinese_date = re.search(r"\d{1,2}月\d{1,2}日", text)
    if chinese_date:
        return chinese_date.group(0)

    if start_time and end_time:
        start_date = format_iso_datetime(start_time)
        end_date = format_iso_datetime(end_time)
        return start_date if start_date == end_date else f"{start_date}至{end_date}"

    return "日期未提供"
    
def format_iso_datetime(value):
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value)
        return f"{dt.month}月{dt.day}日"
    except Exception:
        return value


# 安全通報

# 1. 核心變數設定
has_active_today = {}    # 紀錄每位長輩今天「有沒有跟機器人互動過」 (True / False)
user_state = {}          # 紀錄使用者的臨時狀態（例如：EMERGENCY_MODE）

# 👤 聯絡人
EMERGENCY_CONTACT_ID = "U7dad21ce59a8fd90611085c8dbaead5e" 

def check_daily_active_job():
    """【功能1】每日安全大腦巡邏：檢查長輩今天一整天到底有沒有活動過"""
    try:
        import main
        from linebot.models import TextSendMessage
    except ImportError:
        return

    target_user_id = "U7dad21ce59a8fd90611085c8dbaead5e"  

    #is_active = has_active_today.get(target_user_id, False)
    is_active = False # test

    if not is_active:
        # 定時9.
        try:
            sos_text = (
                "🚨【安全緊急通報 - 系統自動觸發】\n\n"
                "您的家人今天一整天皆未與 LINE 助理進行任何互動，且查無定位軌跡，可能發生異常，請家屬撥空進行關心聯繫！"
            )
            main.line_bot_api.push_message(EMERGENCY_CONTACT_ID, TextSendMessage(text=sos_text))
            print(f"🚨 [安全警報] 長輩 {target_user_id} 今日無任何活動紀錄，已通報家屬！")
        except Exception as e:
            print("通報家屬失敗:", e)
    else:
        print(f"🟢 [安全系統] 檢查完畢：長輩 {target_user_id} 今日活動正常，安全過關！")

#重置狀態
    has_active_today[target_user_id] = False


#scheduler.add_job(check_daily_active_job, 'cron', hour=21, minute=0)
# 測試
scheduler.add_job(check_daily_active_job, 'interval', seconds=10)