import os, logging, base64, json, requests, io, subprocess, asyncio
from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from groq import Groq

# --- BLACKLINES ART STUDIOS CONFIG ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

from groq import Groq
import os

client = Groq(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)
HF_URL = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell"

logging.basicConfig(level=logging.INFO)

async def analyze_art(path):
    try:
        with open(path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode('utf-8')
        
        # FIXED: Using the new 90B Vision model for 2026
        resp = client.chat.completions.create(
            model="llama-3.2-90b-vision-preview",
            messages=[{"role": "user", "content": [
                {"type": "text", "text": "As Blacklines Art Studios director, suggest 6 B&W line art styles for this. Return ONLY JSON: {'styles': [{'name': '...', 'prompt': '...'}]}"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
            ]}],
            response_format={"type": "json_object"}
        )
        return json.loads(resp.choices[0].message.content)["styles"]
    except Exception as e:
        logging.error(f"Analysis failed: {e}")
        return []

async def generate_images(prompt_keyword):
    paths = []
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    for i in range(4):
        p = f"Blacklines Art Studios style, {prompt_keyword}, high contrast ink, white background, variation {i}"
        r = requests.post(HF_URL, headers=headers, json={"inputs": p})
        if r.status_code == 200:
            fname = f"gen_{i}.jpg"
            Image.open(io.BytesIO(r.content)).save(fname)
            paths.append(fname)
    return paths

def make_video(img):
    out = "speed_art.mp4"
    # Optimized 3-minute cinematic zoom for Blacklines Art Studios
    cmd = (
        f"ffmpeg -loop 1 -i {img} -vf "
        "\"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        "zoompan=z='min(zoom+0.0001,1.5)':d=5400:s=1080x1920\" "
        "-c:v libx264 -preset ultrafast -t 180 -pix_fmt yuv420p {out} -y"
    )
    subprocess.run(cmd, shell=True)
    return out

async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.photo[-1].get_file()
    await file.download_to_drive("input.jpg")
    await update.message.reply_text("🖋 Blacklines Art Studios is studying your image...")
    styles = await analyze_art("input.jpg")
    if not styles:
        await update.message.reply_text("❌ Analysis failed. Please try again.")
        return
    context.user_data['styles'] = styles
    btns = [[InlineKeyboardButton(s['name'], callback_data=f"s_{i}")] for i, s in enumerate(styles)]
    await update.message.reply_text("Select the Style:", reply_markup=InlineKeyboardMarkup(btns))

async def on_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    idx = int(query.data.split("_")[1])
    style = context.user_data['styles'][idx]
    await query.edit_message_text(f"🚀 Creating 4 versions in '{style['name']}'...")
    paths = await generate_images(style['prompt'])
    if not paths:
        await query.message.reply_text("❌ Error: Hugging Face API is busy.")
        return
    for p in paths:
        await query.message.reply_photo(open(p, 'rb'))
    await query.message.reply_text("🎬 Generating 3-minute Speed-Art video. This takes a moment...")
    video = make_video(paths[0])
    await query.message.reply_video(open(video, 'rb'), caption="Ready for Master Venky! @Blacklines Art Studios")

if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(CallbackQueryHandler(on_click))
    import asyncio  async def main():     app = Application.builder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()      # add handlers here     # app.add_handler(...)      await app.run_polling()  if __name__ == "__main__":     asyncio.run(main())
