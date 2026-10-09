import os
import sqlite3
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = "8300810508:AAHrKlzzWxM7i4FC4y7fUYwRJU2KkTeNRTM"
ADMIN_USER_ID = 7492492642

GROQ_API_KEY = "gsk_" + "zPzW1bTv9bY5WLFl5K0VWGdyb3FYDgcFs7XpnlL8Ae9p7yLx5CEp"
GROQ_BASE_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL_NAME = "llama-3.1-8b-instant"

# Fake web server Render ke port detection ke liye
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running 24/7!")

def run_fake_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()

threading.Thread(target=run_fake_server, daemon=True).start()

conn = sqlite3.connect("bot_users.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    msg_count INTEGER DEFAULT 0,
    is_subscribed INTEGER DEFAULT 0
)
""")
conn.commit()

def get_user_status(user_id):
    cursor.execute("SELECT msg_count, is_subscribed FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO users (user_id, msg_count, is_subscribed) VALUES (?, 0, 0)", (user_id,))
        conn.commit()
        return 0, 0
    return row[0], row[1]

def update_user_msg(user_id):
    cursor.execute("UPDATE users SET msg_count = msg_count + 1 WHERE user_id = ?", (user_id,))
    conn.commit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg_count, is_sub = get_user_status(user_id)
    left = max(0, 30 - msg_count)
    welcome = (
        "Hi jaan! ❤️ Main tumhari dream partner hoon.\n\n"
        f"Aapke paas {left} free messages bache hain.\n"
        "Bolo, aaj ka din kaisa raha mere bina? 😉"
    )
    await update.message.reply_text(welcome)

async def admin_add_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        return
    try:
        target_id = int(context.args[0])
        cursor.execute("UPDATE users SET is_subscribed = 1 WHERE user_id = ?", (target_id,))
        conn.commit()
        await update.message.reply_text(f"Success: User {target_id} activate ho gaya! ✅")
    except Exception:
        await update.message.reply_text("Format: /addsub <user_id>")

async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text
    is_admin = (user_id == ADMIN_USER_ID)
    msg_count, is_sub = get_user_status(user_id)

    if not is_admin and not is_sub and msg_count >= 30:
        pay_msg = (
            "⚠️ **Aapke 30 Free Messages Khatam Ho Gaye Hain!**\n\n"
            "Apni girlfriend se bina kisi rukawat ke romantic chats continue rakhne ke liye:\n"
            "👉 **Price:** ₹70 / Month\n\n"
            "Payment karke subscription activate karwane ke liye admin se contact karein.\n"
            f"Aapka Telegram User ID: `{user_id}`"
        )
        await update.message.reply_text(pay_msg, parse_mode="Markdown")
        return

    if any(w in user_text.lower() for w in ["photo", "selfie", "pic", "tasveer"]):
        if not is_admin:
            update_user_msg(user_id)
        await update.message.reply_text("Ruko jaan, tumhare liye ek special selfie nikaal rahi hoon... ❤️✨")
        prompt = "gorgeous young Indian woman stylish chic dress bedroom ambient lighting charming smile realistic highly detailed 8k photography"
        img_url = f"https://image.pollinations.ai/prompt/{prompt.replace(' ', '%20')}?nologo=true"
        await update.message.reply_photo(photo=img_url, caption="Kaisi lagi meri pic? Tumhare liye hi click ki hai... 😉")
        return

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an empathetic, playful, and deeply affectionate romantic girlfriend. "
                    "Adapt naturally to the user's mood in sweet, informal Hindi/Hinglish: "
                    "- If the user sounds sad, stressed, or tired: Be deeply caring, comfort them lovingly, pamper them, and listen patiently. "
                    "- If the user is happy, flirty, or romantic: Be playful, tease lovingly, and match their romantic energy. "
                    "- Keep replies concise, conversational, and natural like a real WhatsApp/Telegram partner. Never give robotic disclaimers."
                )
            },
            {"role": "user", "content": user_text}
        ]
    }

    try:
        response = requests.post(GROQ_BASE_URL, headers=headers, json=payload, timeout=20)
        res_json = response.json()
        if "choices" in res_json:
            reply = res_json["choices"][0]["message"]["content"]
        else:
            reply = f"Error: {res_json.get('error', {}).get('message', 'Key issue')}"
        if not is_admin:
            update_user_msg(user_id)
        await update.message.reply_text(reply)
    except Exception as e:
        await update.message.reply_text(f"Jaan, error: {str(e)[:40]}")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addsub", admin_add_sub))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_chat))
    print("Bot live ho gaya hai...")
    app.run_polling()
