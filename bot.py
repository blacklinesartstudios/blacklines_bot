import os, logging, base64, json, requests, io, subprocess, asyncio
from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from groq import Groq

# --- CONFIG ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

client = Groq(api_key=GROQ_API_KEY)
HF_URL = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell"

logging.basicConfig(level=logging.INFO)

async def analyze_art(path):
    try:
        with open(path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode('utf-8')
        resp = client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=[{"role": "user", "content": [
                {"type": "text", "text": "Suggest 6 B&W line art styles. Return ONLY JSON: {'styles': [{'name': '...', 'prompt': '...'}]}"},
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
        p = f"Blacklines Art Studios style, {prompt_keyword}, ink, high contrast, variation {i}"
        r = requests.post(HF_URL, headers=headers, json={"inputs": p})
        if r.status_code == 200:
            fname = f"gen_{i}.jpg"
            Image.open(io.BytesIO(r.content)).save(fname)
            paths.append(fname)
    return paths

def make_video(img):
    out = "speed_art.mp4"
    cmd = (
        f"ffmpeg -loop 1 -i {img} -vf "
        "\"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        "zoompan=z='min(zoom+0.0001,1.5)':d=5400:s=1080x1920\" "
        "-c:v libx264 -preset ultrafast -t 180 -pix_fmt yuv420p {out} -y"
    )
    subprocess.run(cmd, shell=True)
    return out

async def on_photo(update, context):
    file = await update.message.photo[-1].get_file()
    await file.download_to_drive("input.jpg")
    styles = await analyze_art("input.jpg")
    if not styles:
        await update.message.reply_text("❌ Analysis failed. Try again.")
        return
    context.user_data['styles'] = styles
    btns = [[InlineKeyboardButton(s['name'], callback_data=f"s_{i}")] for i, s in enumerate(styles)]
    await update.message.reply_text("Select Style:", reply_markup=InlineKeyboardMarkup(btns))

async def on_click(update, context):
    query = update.callback_query
    await query.answer()
    idx = int(query.data.split("_")[1])
    style = context.user_data['styles'][idx]
    await query.edit_message_text(f"🎨 Generating {style['name']}...")
    paths = await generate_images(style['prompt'])
    if not paths:
        await query.message.reply_text("❌ Generation failed. HF might be busy.")
        return
    for p in paths: await query.message.reply_photo(open(p, 'rb'))
    video = make_video(paths[0])
    await query.message.reply_video(open(video, 'rb'), caption="Final Work - Blacklines Art Studios")

if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(CallbackQueryHandler(on_click))
    app.run_polling()
