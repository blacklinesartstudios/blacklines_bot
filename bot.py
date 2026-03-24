import os
import logging
import json
import requests
import io
import time

from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    MessageHandler,
    CallbackQueryHandler,
    CommandHandler,
    filters,
    ContextTypes
)

from groq import Groq

# --- CONFIG ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")

if not BOT_TOKEN or not GROQ_API_KEY or not HF_TOKEN:
    raise ValueError("❌ Missing environment variables")

logging.basicConfig(level=logging.INFO)

# --- GROQ CLIENT ---
client = Groq(api_key=GROQ_API_KEY)

HF_URL = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell"

# --- START ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Send me an image to generate styles 🎨")

# --- GENERATE STYLES (TEXT ONLY - WORKING) ---
async def get_styles():
    try:
        resp = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{
                "role": "user",
                "content": "Give 6 black & white line art styles in JSON: {styles:[{name,prompt}]}"
            }],
            response_format={"type": "json_object"}
        )

        data = json.loads(resp.choices[0].message.content)
        return data.get("styles", [])

    except Exception as e:
        logging.error(f"Groq error: {e}")
        return []

# --- IMAGE GENERATION ---
async def generate_images(prompt):
    paths = []
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}

    for i in range(4):
        try:
            r = requests.post(
                HF_URL,
                headers=headers,
                json={"inputs": f"{prompt}, variation {i}"},
                timeout=60
            )

            if r.status_code == 200:
                fname = f"gen_{i}.jpg"
                Image.open(io.BytesIO(r.content)).save(fname)
                paths.append(fname)

        except Exception as e:
            logging.error(f"HF error: {e}")

    return paths

# --- PHOTO HANDLER ---
async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🖋 Generating styles...")

    styles = await get_styles()

    if not styles:
        await update.message.reply_text("❌ Style generation failed")
        return

    context.user_data["styles"] = styles

    buttons = [
        [InlineKeyboardButton(s.get("name", "Style"), callback_data=f"s_{i}")]
        for i, s in enumerate(styles)
    ]

    await update.message.reply_text(
        "Choose a style:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# --- BUTTON CLICK ---
async def on_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    idx = int(query.data.split("_")[1])
    styles = context.user_data.get("styles", [])

    if idx >= len(styles):
        await query.message.reply_text("❌ Invalid selection")
        return

    style = styles[idx]

    await query.edit_message_text(f"🎨 Generating: {style.get('name','Style')}")

    paths = await generate_images(style.get("prompt", ""))

    if not paths:
        await query.message.reply_text("❌ Image generation failed")
        return

    for p in paths:
        with open(p, "rb") as img:
            await query.message.reply_photo(img)

    # cleanup
    try:
        for p in paths:
            os.remove(p)
    except:
        pass

# --- RUN BOT ---
def run_bot():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(CallbackQueryHandler(on_click))

    print("✅ Bot running...")
    app.run_polling()

# --- AUTO RESTART LOOP ---
if __name__ == "__main__":
    while True:
        try:
            run_bot()
        except Exception as e:
            print(f"❌ Crash: {e}")
            time.sleep(5)
