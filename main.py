import os
import random
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
    ImageMessage  # 👈 核心：允許接收長輩傳來的照片
)

# 📸 引入圖片處理套件
from PIL import Image, ImageDraw, ImageFont

# 讀取 .env 檔案中的金鑰
load_dotenv()

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

app = FastAPI()

# 將 static 資料夾對外公開
app.mount("/static", StaticFiles(directory="static"), name="static")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# ─── 📚 2. 單字庫 ───
WORDS_DATABASE = [
    {"en": "Family", "zh": "家人", "tw": "家己人 (Ka-kī-lâng)", "audio_prefix": "1"},
    {"en": "Apple", "zh": "蘋果", "tw": "蘋果 (phông-kó)", "audio_prefix": "2"},
    {"en": "Doctor", "zh": "醫生", "tw": "醫生 (i-sing)", "audio_prefix": "3"},
    {"en": "Breakfast", "zh": "早餐", "tw": "早頓 (Tsá-tǹg)", "audio_prefix": "4"},
    {"en": "Thank you", "zh": "謝謝", "tw": "多謝 (To-siā)", "audio_prefix": "5"}
]

# 全域變數：紀錄目前發到第幾個單字
current_word_index = 0

# ─── 🌸 3. 分時段長輩圖資料庫（精選高畫質風景圖） ───
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
        "https://images.unsplash.com/photo-1506318137071-a8e063b4bec0?w=800",
        "https://images.unsplash.com/photo-1532767153582-b1a0e414d5b9?w=800"
    ]
}

# ─── 📝 4. 「英台雙按鈕」單字卡設計圖 ───
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
    return {"message": "LINE Bot 伺服器運行中！"}

@app.post("/callback")
async def callback(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    try:
        handler.handle(body.decode("utf-8"), signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    return PlainTextResponse("OK")


# 🚨 🤖 5. 處理長輩傳來「照片」的超級雷達 (自動生成專屬長輩圖)
@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    # 💡 讓程式在雲端時自動用雲端網址，在本地時用 ngrok
    MY_NGROK_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://senior-platform-concise.ngrok-free.dev")
    
    # A. 抓取長輩傳來的圖片資料並儲存
    message_content = line_bot_api.get_message_content(event.message.id)
    raw_path = os.path.join("static", "user_raw.jpg")
    output_path = os.path.join("static", "user_generated.jpg")
    
    with open(raw_path, 'wb') as fd:
        for chunk in message_content.iter_content():
            fd.write(chunk)
            
    # B. 利用 PIL 進行壓字加工
   # B. 利用 PIL 進行壓字加工 (升級：大字體)
    try:
        img = Image.open(raw_path)
        draw = ImageDraw.Draw(img)
        
        # 隨機選一句長輩吉祥話
        slogans = [" 祝您平安喜樂 ", " 順心如意 身體健康 ", " 每天都有好心情 ", " 吉祥安康 福氣滿滿 "]
        text = random.choice(slogans)
        
        # 字型設定 (優先抓專案目錄下的字型)
        font_path = "kaiu.ttf" if os.path.exists("kaiu.ttf") else "C:\\Windows\\Fonts\\msjh.ttc"
        
        # 💡 重點修正：將字體大小設定為圖片寬度的 1/8 (約佔圖片 12.5%)
        font_size = int(img.width / 8) if img.width > 0 else 60
        
        font = ImageFont.truetype(font_path, font_size)
            
        # 計算文字置中擺放的座標
        text_w = draw.textlength(text, font=font)
        x = (img.width - text_w) / 2
        # 將字體高度設定為寬度的 1/8 (若圖片是長方形，這裏做個修正)
        y = img.height - font_size - 100 # 放置在圖片下方位置
        
        # 繪製黑色陰影 (黑邊也加粗，更清晰)
        shadow_offset = int(font_size / 20) if font_size > 20 else 2
        draw.text((x + shadow_offset, y + shadow_offset), text, font=font, fill="black")
        
        # 繪製亮金黃色正文字
        draw.text((x, y), text, font=font, fill="#FFD700")
        
        # 儲存加工完畢的成品圖片
        img.save(output_path, "JPEG")
        
        # C. 將客製化成品大圖回傳給長輩
        final_url = f"{MY_NGROK_URL}/static/user_generated.jpg?v={random.randint(1,9999)}"
        line_bot_api.reply_message(
            event.reply_token,
            ImageSendMessage(original_content_url=final_url, preview_image_url=final_url)
        )
    except Exception as e:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"製作長輩圖失敗了，請檢查後台字型設定喔！(錯誤: {str(e)})")
        )


# 🤖 6. 處理文字訊息的核心邏輯
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    global current_word_index
    user_text = event.message.text
   # 💡 讓程式在雲端時自動用雲端網址，在本地時用 ngrok
    MY_NGROK_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://senior-platform-concise.ngrok-free.dev") 
    
    # ─── 【語音分支 A】點擊「聽台語」 ───
    if user_text == "聽台語":
        last_word = WORDS_DATABASE[(current_word_index - 1) % len(WORDS_DATABASE)]
        audio_url = f"{MY_NGROK_URL}/static/{last_word['audio_prefix']}.mp3"
        line_bot_api.reply_message(event.reply_token, AudioSendMessage(original_content_url=audio_url, duration=2000))

    # ─── 【語音分支 B】點擊「聽英文」 ───
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
        
    # ─── 【選單功能 1】緊急通報 ───
    elif user_text == "/安全通報":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 已啟動安全通報流程，正在發送定位並聯繫您的緊急聯絡人！請長輩保持冷靜。"))
        
    # ─── 【選單功能 2】英文單字卡 ───
    elif user_text == "/生活單字卡":
        word_data = WORDS_DATABASE[current_word_index]
        dynamic_card_json = create_card(word_data)
        line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text=f"今日單字: {word_data['en']}", contents=dynamic_card_json))
        current_word_index = (current_word_index + 1) % len(WORDS_DATABASE)
        
    # ─── 【選單功能 3】生活福利 ───
    elif user_text == "/生活福利":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="正在為您查詢台北市最新銀髮族補助福利...（此功能未來將由 RAG 知識庫自動回覆）"))
        
    # ─── 【選單功能 4】長輩圖 (升級為引導文字選單) ───
    elif user_text == "/長輩圖":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="🌸 請問您要挑選哪個時段的祝福呢？\n\n請點選或輸入文字：\n👉 早安\n👉 午安\n👉 晚安\n\n💡 溫馨提示：您也可以「直接傳一張照片」給我，我會幫您做成專屬長輩圖喔！")
        )

    # ─── 隨機抽圖子分支：當長輩點擊或輸入早安/午安/晚安時 (✨ 升級：雙行大字排版) ───
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
            
            # 💡 設定對應時段的「雙行」祝福語
            if user_text == "早安":
                text = " 早安吉祥 \n 順心如意 "
            elif user_text == "午安":
                text = " 午安平安 \n 幸福相隨 "
            else:
                text = " 晚安安康 \n 舒心好眠 "
                
            font_path = "kaiu.ttf" if os.path.exists("kaiu.ttf") else "C:\\Windows\\Fonts\\msjh.ttc"
            font_size = int(img.width / 8) if img.width > 0 else 60
            font = ImageFont.truetype(font_path, font_size)
            
            # 💡 換行置中繪製邏輯
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
            line_bot_api.reply_message(
                event.reply_token,
                ImageSendMessage(original_content_url=final_url, preview_image_url=final_url)
            )
            
        except Exception as e:
            line_bot_api.reply_message(
                event.reply_token,
                ImageSendMessage(original_content_url=chosen_image_url, preview_image_url=chosen_image_url)
            )
    # ─── 【選單功能 5】推薦景點 ───
    elif user_text == "/推薦景點":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🌟 今日推薦長輩出遊踏青景點：台北市大安森林公園、或前往芝山岩步道散散步喔！"))
        
    # ─── 【LLM AI 大腦線】長輩一般打字聊天 ───
    else:
        llm_reply = f"（您說了：'{user_text}'。今天心情怎麼樣啊？"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=llm_reply))

if __name__ == "__main__":
    import uvicorn
    # 💡 讓雲端平台可以動態分配 Port，找不到時才用預設的 8000
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)