import os
import random
import sys  
from pathlib import Path  
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from gtts import gTTS

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, 
    FlexSendMessage, AudioSendMessage, ImageSendMessage,
    ImageMessage, LocationMessage, QuickReply, QuickReplyButton, MessageAction, LocationAction
)

# 圖片處理套件
from PIL import Image, ImageDraw, ImageFont


load_dotenv()

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

app = FastAPI()


app.mount("/static", StaticFiles(directory="static"), name="static")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)


PROJECT_ROOT = Path(__file__).resolve().parent
CHATBOT_DIR = PROJECT_ROOT / "LLM_run"
sys.path.insert(0, str(CHATBOT_DIR))

try:
    import chatbotV2  
    print("✅ 本地大腦模組 chatbotV2 成功與 LINE Bot 連線！")
except ImportError as e:
    chatbotV2 = None
    print(f"⚠️ 本地大腦模組載入失敗，錯誤訊息: {e}")


try:
    import app as map_module
    print("✅ 同學的地圖活動模組 app.py 成功與控制中心連線！")
except ImportError as e:
    map_module = None
    print(f"⚠️ 同學的地圖活動模組載入失敗: {e}")

# 單字庫
WORDS_DATABASE = [
    {"en": "Family", "zh": "家人", "tw": "家己人 (Ka-kī-lâng)", "audio_prefix": "1"},
    {"en": "Apple", "zh": "蘋果", "tw": "蘋果 (phông-kó)", "audio_prefix": "2"},
    {"en": "Doctor", "zh": "醫生", "tw": "醫生 (i-sing)", "audio_prefix": "3"},
    {"en": "Breakfast", "zh": "早餐", "tw": "早頓 (Tsá-tǹg)", "audio_prefix": "4"},
    {"en": "Thank you", "zh": "謝謝", "tw": "多謝 (To-siā)", "audio_prefix": "5"}
]

current_word_index = 0

# ─── 分時段長輩圖資料庫 ───
GREETING_IMAGES = {
    "早安": [
        "https://images.unsplash.com/photo-1506744038136-46273834b3fb?w=800",
        "https://images.unsplash.com/photo-1470240731273-7821a6eeb6bd?w=800"
    ],
    "午安": [
        "https://images.unsplash.com/photo-1501854140801-50d01698950b?w=800",
        "https://images.unsplash.com/photo-1447752875215-b2761acb3c5d?w=800"
    ],
    "晚安": [
        "https://images.unsplash.com/photo-1519681393784-d120267933ba?auto=format&fit=crop&w=800&q=80",  
        "https://images.unsplash.com/photo-1506318137071-a8e063b4bec0?auto=format&fit=crop&w=800&q=80"   
    ]
}

def create_card(word_data):
    return {
      "type": "bubble",
      "body": {
        "type": "box",
        "layout": "vertical",
        "contents": [
          {"type": "text", "text": "今日生活單字", "weight": "bold", "color": "#FF823A", "size": "sm"},
          {"type": "text", "text": word_data["en"], "weight": "bold", "size": "xxl", "margin": "md"},
          {"type": "separator", "margin": "lg"},
          {
            "type": "box",
            "layout": "vertical",
            "margin": "lg",
            "spacing": "sm",
            "contents": [
              {
                "type": "box", "layout": "baseline", "spacing": "sm",
                "contents": [
                  {"type": "text", "text": "中文", "color": "#aaaaaa", "size": "sm", "flex": 1},
                  {"type": "text", "text": word_data["zh"], "wrap": True, "color": "#666666", "size": "md", "flex": 4}
                ]
              },
              {
                "type": "box", "layout": "baseline", "spacing": "sm",
                "contents": [
                  {"type": "text", "text": "台語", "color": "#aaaaaa", "size": "sm", "flex": 1},
                  {"type": "text", "text": word_data["tw"], "wrap": True, "color": "#2E4D68", "size": "md", "flex": 4, "weight": "bold"}
                ]
              }
            ]
          }
        ]
      },
      "footer": {
        "type": "box",
        "layout": "horizontal",
        "spacing": "sm",
        "contents": [
          {
            "type": "button",
            "style": "primary",
            "color": "#4A90E2",
            "action": { "type": "message", "label": "聽英文 🇺🇸", "text": "聽英文" }
          },
          {
            "type": "button",
            "style": "primary",
            "color": "#2ECC71",
            "action": { "type": "message", "label": "聽台語 🔊", "text": "聽台語" }
          }
        ]
      }
    }

@app.get("/")
async def root():
    return {"message": "本地 LINE Bot 伺服器運行中！"}

@app.post("/callback")
async def callback(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    try:
        handler.handle(body.decode("utf-8"), signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    return PlainTextResponse("OK")

# 🚨 🤖 5. 處理長輩傳來「照片」的雷達
@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    MY_NGROK_URL = os.environ.get("MY_CURRENT_NGROK_URL", "https://senior-platform-concise.ngrok-free.dev")
    message_content = line_bot_api.get_message_content(event.message.id)
    raw_path = os.path.join("static", "user_raw.jpg")
    output_path = os.path.join("static", "user_generated.jpg")
    
    with open(raw_path, 'wb') as fd:
        for chunk in message_content.iter_content():
            fd.write(chunk)
            
    try:
        img = Image.open(raw_path)
        draw = ImageDraw.Draw(img)
        slogans = [" 祝您平安喜樂 ", " 順心如意 身體健康 ", " 每天都有好心情 ", " 吉祥安康 福氣滿滿 "]
        text = random.choice(slogans)
        
        font_path = "kaiu.ttf" if os.path.exists("kaiu.ttf") else "/System/Library/Fonts/Supplemental/Arial.ttf"
        font_size = int(img.width / 8) if img.width > 0 else 60
        font = ImageFont.truetype(font_path, font_size)
            
        text_w = draw.textlength(text, font=font)
        x = (img.width - text_w) / 2
        y = img.height - font_size - 100 
        
        shadow_offset = int(font_size / 20) if font_size > 20 else 2
        draw.text((x + shadow_offset, y + shadow_offset), text, font=font, fill="black")
        draw.text((x, y), text, font=font, fill="#FFD700")
        
        img.save(output_path, "JPEG")
        
        final_url = f"{MY_NGROK_URL}/static/user_generated.jpg?v={random.randint(1,9999)}"
        line_bot_api.reply_message(
            event.reply_token,
            ImageSendMessage(original_content_url=final_url, preview_image_url=final_url)
        )
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"製作長輩圖失敗了！(錯誤: {str(e)})"))

# 🤖 6. 處理文字訊息的核心邏輯
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    global current_word_index
    user_text = event.message.text.strip()
    user_id = event.source.user_id
    print(f"👤 當前發言使用者的 LINE User ID 是: {user_id}")
    MY_NGROK_URL = os.environ.get("MY_CURRENT_NGROK_URL", "https://senior-platform-concise.ngrok-free.dev") 
    
    # ------------- 🟢 安全蓋章：只要長輩打字互動，就證明他今天安全 -------------
    if map_module is not None:
        map_module.has_active_today[user_id] = True
    # ------------------------------------------------------------------------

    if user_text == "聽台語":
        last_word = WORDS_DATABASE[(current_word_index - 1) % len(WORDS_DATABASE)]
        audio_url = f"{MY_NGROK_URL}/static/{last_word['audio_prefix']}.mp3"
        line_bot_api.reply_message(event.reply_token, AudioSendMessage(original_content_url=audio_url, duration=2000))

    elif user_text == "聽英文":
        last_word = WORDS_DATABASE[(current_word_index - 1) % len(WORDS_DATABASE)]
        english_text = last_word['en']
        filename = f"{last_word['audio_prefix']}_en.mp3"
        filepath = os.path.join("static", filename)
        
        if not os.path.exists(filepath):
            tts = gTTS(text=english_text, lang='en', slow=False)
            tts.save(filepath)
            
        audio_url = f"{MY_NGROK_URL}/static/{filename}"
        line_bot_api.reply_message(event.reply_token, AudioSendMessage(original_content_url=audio_url, duration=2000))
        
    # ------------- 🚨 核心亮點：長輩主動觸發「緊急通報」 -------------
    elif user_text in ["緊急通報", "/安全通報", "救命", "/緊急通報"]:
        if map_module is not None:
            map_module.user_state[user_id] = "EMERGENCY_MODE"  # 先將大腦切換到緊急狀態
        
        
        quick_reply = QuickReply(items=[
            QuickReplyButton(action=LocationAction(label="🚨 點我立刻發送定位求救"))
        ])
        
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text="🚨 請點選下方大按鈕，直接送出您目前的位置：", quick_reply=quick_reply)
        )
        
    elif user_text == "/生活單字卡":
        word_data = WORDS_DATABASE[current_word_index]
        dynamic_card_json = create_card(word_data)
        line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text=f"今日單字: {word_data['en']}", contents=dynamic_card_json))
        current_word_index = (current_word_index + 1) % len(WORDS_DATABASE)
        
    elif user_text == "/生活福利":
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text="🤖 收到！正在為您翻閱「台北市銀髮族福利法規資料庫」，請長輩稍等助理 5秒鐘喔...⏳")
        )
        
        if chatbotV2 is not None:
            try:
                ai_reply = chatbotV2.chat_with_rag(user_text)
                line_bot_api.push_message(user_id, TextSendMessage(text=ai_reply))
            except Exception as e:
                print("AI 檢索錯誤:", e)
                line_bot_api.push_message(user_id, TextSendMessage(text=f"⚠️ 福利查詢系統出錯：{str(e)}"))
        else:
            line_bot_api.push_message(user_id, TextSendMessage(text="正在為您查詢台北市最新銀髮族補助福利...（大腦模組未啟動）"))
        
    elif user_text == "/長輩圖":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="🌸 請問您要挑選哪個時段的祝福呢？\n\n請點選或輸入文字：\n👉 早安\n👉 午安\n👉 晚安\n\n💡 溫馨提示：您也可以「直接傳一張照片」給我喔！")
        )

    elif user_text in ["早安", "午安", "晚安"]:
        import requests
        from io import BytesIO
        image_list = GREETING_IMAGES[user_text]
        chosen_image_url = random.choice(image_list)
        output_path = os.path.join("static", "preset_generated.jpg")
        
        try:
            response = requests.get(chosen_image_url)
            img = Image.open(BytesIO(response.content))
            draw = ImageDraw.Draw(img)
            
            if user_text == "早安": text = " 早安吉祥 \n 順心如意 "
            elif user_text == "午安": text = " 午安平安 \n 幸福相隨 "
            else: text = " 晚安安康 \n 舒心好眠 "
                
            font_path = "kaiu.ttf" if os.path.exists("kaiu.ttf") else "/System/Library/Fonts/Supplemental/Arial.ttf"
            font_size = int(img.width / 8) if img.width > 0 else 60
            font = ImageFont.truetype(font_path, font_size)
            
            lines = text.split("\n")
            line_spacing = int(font_size * 0.3)
            total_height = (font_size * len(lines)) + (line_spacing * (len(lines) - 1))
            current_y = img.height - total_height - 60
            
            for line in lines:
                text_w = draw.textlength(line, font=font)
                x = (img.width - text_w) / 2
                shadow_offset = int(font_size / 20) if font_size > 20 else 2
                draw.text((x + shadow_offset, current_y + shadow_offset), line, font=font, fill="black")
                draw.text((x, current_y), line, font=font, fill="#FFD700")
                current_y += font_size + line_spacing
            
            img.save(output_path, "JPEG")
            final_url = f"{MY_NGROK_URL}/static/preset_generated.jpg?v={random.randint(1,9999)}"
            line_bot_api.reply_message(event.reply_token, ImageSendMessage(original_content_url=final_url, preview_image_url=final_url))
        except Exception as e:
            line_bot_api.reply_message(event.reply_token, ImageSendMessage(original_content_url=chosen_image_url, preview_image_url=chosen_image_url))

    elif user_text in ["/推薦景點", "推薦景點", "活動資訊"]:
        intro_text = "🌟 今日推薦長輩出遊踏青景點：台北市大安森林公園、或前往芝山岩步道散散步喔！\n\n請選擇想查詢的類別："
        
        quick_reply = QuickReply(items=[
            QuickReplyButton(action=MessageAction(label="附近活動據點", text="附近活動據點")),
            QuickReplyButton(action=MessageAction(label="附近公園散步", text="附近公園散步")),
            QuickReplyButton(action=MessageAction(label="活動訊息", text="活動訊息"))
        ])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=intro_text, quick_reply=quick_reply))

    elif user_text == "附近活動據點" and map_module is not None:
        map_module.user_state[user_id] = "place"
        quick_reply = QuickReply(items=[QuickReplyButton(action=LocationAction(label="分享我的位置"))])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請分享您的位置，我會幫您找附近的活動據點。", quick_reply=quick_reply))

    elif user_text == "附近公園散步" and map_module is not None:
        map_module.user_state[user_id] = "park"
        quick_reply = QuickReply(items=[QuickReplyButton(action=LocationAction(label="分享我的位置"))])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請分享您的位置，我會幫您找附近適合散步的公園。", quick_reply=quick_reply))

    elif user_text in ["活動訊息", "銀髮活動訊息", "換一批活動"] and map_module is not None:
        msg_text, has_events = map_module.build_senior_events_message(user_id)
        if has_events:
            quick_reply = QuickReply(items=[QuickReplyButton(action=MessageAction(label="換一批活動", text="換一批活動"))])
        else:
            quick_reply = QuickReply(items=[
                QuickReplyButton(action=MessageAction(label="重新檢視", text="重新檢視活動")),
                QuickReplyButton(action=MessageAction(label="活動查詢網站", text="活動查詢網站"))
            ])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg_text, quick_reply=quick_reply))

    elif user_text == "重新檢視活動" and map_module is not None:
        map_module.user_seen_events.pop(user_id, None)
        msg_text, _ = map_module.build_senior_events_message(user_id)
        quick_reply = QuickReply(items=[QuickReplyButton(action=MessageAction(label="換一批活動", text="換一批活動"))])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg_text, quick_reply=quick_reply))

    elif user_text == "活動查詢網站":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="您可以到臺北市銀髮族學習及活動地圖查詢網站看看更多活動：\nhttps://map.dosw.gov.taipei/taipeiWelfare_map/all_new/elder_map.aspx"))
     
   # 💡 直接加在原本 else: (大腦聊天) 的前面一格喔！
    elif user_text == "查最後定位":
        last_lat = map_module.user_state.get(f"{user_id}_last_lat")
        last_lng = map_module.user_state.get(f"{user_id}_last_lng")
        
        if last_lat and last_lng:
            reply_text = (
                "📍【長輩最後已知位置回報】\n\n"
                "系統幫您翻閱了長輩今天最後一次與地圖互動的紀錄：\n"
                f"🗺️ Google 地圖最後定位：\nhttp://maps.google.com/?q={last_lat},{last_lng}"
            )
        else:
            reply_text = "📭 查無長輩今天的定位軌跡紀錄（長輩今天尚未開啟地圖功能）。"
            
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        
    else:
        if chatbotV2 is not None:
            try:
                ai_reply = chatbotV2.chat_with_rag(user_text)
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=ai_reply))
            except Exception as e:
                print(f"本地大腦執行出錯: {str(e)}")
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="（助理剛才打個盹，您可以再跟我說一次嗎？😊）"))
        else:
            llm_reply = f"（您說了：'{user_text}'。今天心情怎麼樣啊？）"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=llm_reply))

# ─── 🛰️ 7. 處理長輩發送 GPS 定位的核心雷達 (修復安全通報回傳位置機制) ───
@handler.add(MessageEvent, message=LocationMessage)
def handle_location(event):
    user_id = event.source.user_id
    latitude = event.message.latitude
    longitude = event.message.longitude
    
    if map_module is None:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="地圖活動模組未啟動。"))
        return

    # 只要長輩今天有傳過任何定位（查公園或據點），就默默幫他記下來！
    if user_id not in map_module.user_state:
        map_module.user_state[user_id] = {}
    
    # 用另外的秘密 key 把最後的經緯度存起來，才不會被清掉
    map_module.user_state[f"{user_id}_last_lat"] = latitude
    map_module.user_state[f"{user_id}_last_lng"] = longitude
    map_module.has_active_today[user_id] = True  # 安全蓋章
    # ---------------------------------------------------------

    # 🚨 2. 緊急求救攔截點
    mode = map_module.user_state.get(user_id)
    if mode == "EMERGENCY_MODE":
        try:
            sos_text = (
                "🚨🚨🚨【緊急救援求助通報】🚨🚨🚨\n\n"
                "您的家人剛剛按下了【緊急通報】求救按鈕！\n"
                "以下是長輩目前的即時 GPS 定位：\n"
                f"📍 Google 地圖導航：\nhttp://maps.google.com/?q={latitude},{longitude}"
            )
            line_bot_api.push_message(map_module.EMERGENCY_CONTACT_ID, TextSendMessage(text=sos_text))
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🚨 您的即時定位已成功傳送給緊急聯絡人！"))
        except Exception as e:
            print("緊急通報發送失敗:", e)
            
        map_module.user_state.pop(user_id, None)
        return

    # ─── 🌲 下面是原本的一般地圖功能 (查公園/查據點) ───
    if mode == "park":
        try:
            parks = map_module.search_nearby_parks(latitude, longitude)
            message = map_module.format_parks_message(parks)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=message))
        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="查詢附近公園時發生錯誤。"))
        map_module.user_state.pop(user_id, None)
        
    elif mode == "place":
        try:
            places = map_module.search_nearby_places(latitude, longitude)
            message = map_module.format_places_message(places)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=message))
        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="查詢附近活動據點時發生錯誤。"))
        map_module.user_state.pop(user_id, None)
        
    else:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="已收到您的位置，但請先點選「附近公園散步」或「附近活動據點」喔！"))
    # ------------------------------------------------------------------------

    # ─── 🌲 下面是原本的一般地圖功能 ───
    mode = map_module.user_state.get(user_id)
    
    if mode == "park":
        try:
            parks = map_module.search_nearby_parks(latitude, longitude)
            message = map_module.format_parks_message(parks)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=message))
        except Exception as e:
            print("公園查詢錯誤:", e)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="查詢附近公園時發生錯誤。"))
        map_module.user_state.pop(user_id, None)
        
    elif mode == "place":
        try:
            places = map_module.search_nearby_places(latitude, longitude)
            message = map_module.format_places_message(places)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=message))
        except Exception as e:
            print("據點查詢錯誤:", e)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="查詢附近活動據點時發生錯誤。"))
        map_module.user_state.pop(user_id, None)
        
    else:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="已收到您的位置，但請先點選「附近公園散步」或「附近活動據點」喔！"))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8555))
    uvicorn.run(app, host="0.0.0.0", port=port)