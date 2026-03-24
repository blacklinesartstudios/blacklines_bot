import os, logging, base64, json, requests, io, subprocess, threading
from PIL import Image
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, MessageHandler, CallbackQueryHandler,
    CommandHandler, filters, ContextTypes
)
from groq import Groq

# --- CONFIG ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

logging.basicConfig(level=logging.INFO)

# --- DUMMY SERVER (for Render port) ---
def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is running")

    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()

# --- GROQ CLIENT ---
client = Groq(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

HF_URL = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell"

# --- START ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Send me an image!")

# --- ANALYZE ---
async def analyze_art(path):
    try:
        with open(path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")

        resp = client.chat.completions.create(
            model="llama-3.2-90b-vision-preview",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Give 6 black & white line art styles JSON"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                ]
            }],
            response_format={"type": "json_object"}
        )

        data = json.loads(resp.choices[0].message.content)
        return data.get("styles", [])

    except Exception as e:
        logging.error(f"Groq error: {e}")
        return []

# --- GENERATE ---
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
            logging.error(e)

    return paths

# --- PHOTO ---
async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.photo[-1].get_file()
    await file.download_to_drive("input.jpg")

    await update.message.reply_text("🖋 Processing...")

    styles = await analyze_art("input.jpg")

    if not styles:
        await update.message.reply_text("❌ Failed")
        return

    context.user_data["styles"] = styles

    buttons = [
        [InlineKeyboardButton(s.get("name", "Style"), callback_data=f"s_{i}")]
        for i, s in enumerate(styles)
    ]

    await update.message.reply_text(
        "Choose style:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# --- CLICK ---
async def on_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    idx = int(query.data.split("_")[1])
    styles = context.user_data.get("styles", [])

    if idx >= len(styles):
        await query.message.reply_text("❌ Invalid")
        return

    style = styles[idx]

    await query.edit_message_text("🎨 Generating...")

    paths = await generate_images(style.get("prompt", ""))

    for p in paths:
        await query.message.reply_photo(open(p, "rb"))

# --- RUN ---
if __name__ == "__main__":
    # Start dummy server (fix for Render)
    threading.Thread(target=run_dummy_server).start()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(CallbackQueryHandler(on_click))

    print("✅ Bot running...")
    app.run_polling()
