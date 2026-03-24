import os, logging, base64, json, requests, io, subprocess, asyncio
from PIL import Image
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

# --- GROQ CLIENT ---
client = Groq(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

HF_URL = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell"

# --- START COMMAND ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Send me an image to generate Blacklines styles!")

# --- ANALYZE IMAGE ---
async def analyze_art(path):
    try:
        with open(path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")

        resp = client.chat.completions.create(
            model="llama-3.2-90b-vision-preview",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Give 6 black & white line art styles. Return JSON: {'styles':[{'name':'','prompt':''}]}"}, 
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                ]
            }],
            response_format={"type": "json_object"}
        )

        data = json.loads(resp.choices[0].message.content)
        return data.get("styles", [])

    except Exception as e:
        logging.error(f"Analysis failed: {e}")
        return []

# --- GENERATE IMAGES ---
async def generate_images(prompt_keyword):
    paths = []
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}

    for i in range(4):
        prompt = f"Blacklines line art, {prompt_keyword}, high contrast ink, white background, variation {i}"

        try:
            r = requests.post(HF_URL, headers=headers, json={"inputs": prompt}, timeout=60)

            if r.status_code == 200:
                fname = f"gen_{i}.jpg"
                Image.open(io.BytesIO(r.content)).save(fname)
                paths.append(fname)

        except Exception as e:
            logging.error(f"HF error: {e}")

    return paths

# --- VIDEO (SAFE: optional) ---
def make_video(img):
    out = "speed_art.mp4"

    try:
        cmd = (
            f"ffmpeg -loop 1 -i {img} -vf "
            "\"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            "zoompan=z='min(zoom+0.0001,1.5)':d=5400:s=1080x1920\" "
            "-c:v libx264 -preset ultrafast -t 180 -pix_fmt yuv420p "
            f"{out} -y"
        )
        subprocess.run(cmd, shell=True)
        return out
    except:
        return None

# --- HANDLE PHOTO ---
async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.photo[-1].get_file()
    await file.download_to_drive("input.jpg")

    await update.message.reply_text("🖋 Processing your image...")

    styles = await analyze_art("input.jpg")

    if not styles:
        await update.message.reply_text("❌ Could not analyze image.")
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
        await query.message.reply_text("❌ Invalid selection.")
        return

    style = styles[idx]

    await query.edit_message_text(f"🎨 Generating: {style.get('name','Style')}")

    paths = await generate_images(style.get("prompt", ""))

    if not paths:
        await query.message.reply_text("❌ Image generation failed.")
        return

    for p in paths:
        await query.message.reply_photo(open(p, "rb"))

    # --- VIDEO (optional) ---
    video = make_video(paths[0])
    if video and os.path.exists(video):
        await query.message.reply_video(open(video, "rb"))

    # --- CLEANUP ---
    try:
        os.remove("input.jpg")
        for p in paths:
            os.remove(p)
        if video and os.path.exists(video):
            os.remove(video)
    except:
        pass



# --- RUN ---
if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(CallbackQueryHandler(on_click))

    print("✅ Bot started")
    app.run_polling()
