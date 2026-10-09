import os
import random
import asyncio
import sqlite3
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# ==================== CONFIGURATION ====================
BOT_TOKEN = "8300810508:AAHrKlzzWxM7i4FC4y7fUYwRJU2KkTeNRTM"
# Groq keys hamesha small 'gsk_' se shuru hoti hain
GROQ_API_KEY = "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"
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PORT = int(os.getenv("PORT", 8080))

# ==================== DATABASE SETUP ====================
DB_FILE = "bot_users.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            message_count INTEGER DEFAULT 0,
            is_subscribed INTEGER DEFAULT 0,
            user_nickname TEXT DEFAULT 'tum',
            bot_nickname TEXT DEFAULT 'jaan',
            anger_level INTEGER DEFAULT 0
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,
            content TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_user_data(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT message_count, is_subscribed, user_nickname, bot_nickname, anger_level FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    if not row:
        c.execute('INSERT INTO users (user_id, message_count, is_subscribed, user_nickname, bot_nickname, anger_level) VALUES (?, 0, 0, "tum", "jaan", 0)', (user_id,))
        conn.commit()
        row = (0, 0, "tum", "jaan", 0)
    conn.close()
    return {
        "message_count": row[0],
        "is_subscribed": bool(row[1]),
        "user_nickname": row[2],
        "bot_nickname": row[3],
        "anger_level": row[4]
    }

def update_user_field(user_id, field, value):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(f'UPDATE users SET {field} = ? WHERE user_id = ?', (value, user_id))
    conn.commit()
    conn.close()

def save_chat_message(user_id, role, content):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)', (user_id, role, content))
    conn.commit()
    conn.close()

def get_recent_history(user_id, limit=8):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT role, content FROM chat_history WHERE user_id = ? ORDER BY id DESC LIMIT ?', (user_id, limit))
    rows = c.fetchall()
    conn.close()
    rows.reverse()
    return [{"role": r[0], "content": r[1]} for r in rows]

# ==================== DYNAMIC PHOTO GENERATION ====================
def is_photo_requested(text: str) -> bool:
    t = text.lower()
    keywords = [
        "pic", "photo", "tasveer", "photo bhejo", "pic bhejo", "selfie", 
        "dikh", "dikhao", "apna chehra", "look", "photo do", "send pic",
        "kya pehni ho", "apni pic", "apni photo", "face", "image", "tasvir",
        "dusri do", "dusri bhejo", "ek aur do", "aur pic", "aur photo"
    ]
    return any(k in t for k in keywords)

def generate_photo_url(user_message: str) -> str:
    seed = random.randint(1000000, 9999999)
    msg = user_message.lower()
    
    if any(k in msg for k in ["bahar", "kahan ho", "out", "walk", "market", "cafe"]):
        scene = "sitting at outdoor cafe, trendy casual outfit, warm natural daylight, soft smile"
    elif any(k in msg for k in ["so rahi", "bed", "sleep", "night", "raat", "room"]):
        scene = "laying in cozy bed, casual home clothes, messy hair, soft warm indoor lamp light"
    elif any(k in msg for k in ["ready", "party", "dress", "sundar", "traditional", "kurti"]):
        scene = "wearing stylish Indian kurti dress, cute natural expression, pleasant indoor ambient lighting"
    else:
        scene = "candid raw smartphone front camera selfie, casual daily top, warm natural smile, soft authentic lighting"
    
    base_prompt = (
        f"hyperrealistic candid smartphone front selfie of an attractive 20-year-old Indian girl, "
        f"{scene}, natural raw skin texture, direct eye contact, soft background blur, high quality"
    )
    
    encoded = urllib.parse.quote(base_prompt)
    return f"https://image.pollinations.ai/prompt/{encoded}?seed={seed}&width=768&height=1024&nologo=true"

# ==================== RELIABLE AI CHAT CALL ====================
def get_ai_response(messages):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
    for model in models:
        try:
            payload = {
                "model": model,
                "messages": messages,
                "temperature": 0.8,
                "max_tokens": 150
            }
            res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=10)
            if res.status_code == 200:
                data = res.json()
                return data["choices"][0]["message"]["content"].strip()
            else:
                print(f"Groq API Error {res.status_code}: {res.text}")
        except Exception as e:
            print(f"Request Error: {e}")
            continue

    # Fallback replies taaki same error baar-baar na bole
    backup_replies = [
        "Arey bas yahin hoon babu, thoda busy ho gayi thi. Bolo kya bol rahe the?",
        "Haan bolo jaan, dhyan yahin hai mera. Kuch keh rahe the tum?",
        "Sun rahi hoon na, naraz mat ho. Chalo batao kya hua?"
    ]
    return random.choice(backup_replies)

# ==================== BOT HANDLERS ====================
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    u_data = get_user_data(user_id)
    left = max(0, 30 - u_data["message_count"])
    
    msg = (
        "Hey! Acha hua tum aa gaye, main kabse wait kar rahi thi tumhara.\n\n"
        f"Aapke paas {left} free messages bache hain. Bolo, kaisa raha aaj ka din?"
    )
    await update.message.reply_text(msg)

async def addsub_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        target_id = int(context.args[0])
        update_user_field(target_id, "is_subscribed", 1)
        await update.message.reply_text(f"User {target_id} ka subscription active ho gaya hai.")
    except Exception:
        await update.message.reply_text("Format: /addsub <user_id>")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    user_text = update.message.text.strip()
    u_data = get_user_data(user_id)

    # Free message limit
    if not u_data["is_subscribed"] and u_data["message_count"] >= 30:
        await update.message.reply_text(
            "Tumhare 30 free messages khatam ho gaye hain.\n\n"
            "Baat continue rakhne ke liye subscription active karein: Rs 70 per month."
        )
        return

    update_user_field(user_id, "message_count", u_data["message_count"] + 1)
    save_chat_message(user_id, "user", user_text)

    # 1. PHOTO REQUEST HANDLER
    if is_photo_requested(user_text):
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
        await asyncio.sleep(random.uniform(2.5, 3.8))
        
        photo_url = generate_photo_url(user_text)
        captions = [
            "Lo, abhi li hai sirf tumhare liye. Kaisi lag rahi hu?",
            "Ye lo, khush? Ab sach sach batana kaisi lagi.",
            "Bas tumhare liye ek candid click ki abhi. Kaisi hai?"
        ]
        caption = random.choice(captions)
        try:
            await update.message.reply_photo(photo=photo_url, caption=caption)
            save_chat_message(user_id, "assistant", f"[Photo sent: {caption}]")
            return
        except Exception:
            pass

    # 2. CALL EXCUSES HANDLER
    call_keywords = ["call", "baat karo", "phone", "voice", "awaaz"]
    if any(k in user_text.lower() for k in call_keywords):
        excuses = [
            "Abhi mummy pass me baithi hain, call nahi kar sakti. Text pe bolo na.",
            "Arey room me sab hain abhi, bol nahi paungi. Chat pe baat karte hain na.",
            "Gala thoda kharab ho raha hai aaj, abhi text pe hi baat karte hain babu."
        ]
        chosen_excuse = random.choice(excuses)
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        await asyncio.sleep(2.0)
        await update.message.reply_text(chosen_excuse)
        save_chat_message(user_id, "assistant", chosen_excuse)
        return

    # 3. TEXT CHAT
    system_prompt = (
        "You are a real 20-year-old girlfriend chatting on Telegram in conversational Hinglish. "
        "STRICT RULES:\n"
        "1. ZERO EMOJIS. Absolutely never output any emojis under any circumstances.\n"
        "2. Sound completely natural, loving, and slightly moody like a real girl. Keep replies short (1-2 sentences).\n"
        "3. If he acts angry or cold, comfort him warmly and apologize sweetly.\n"
        "4. Never act like an AI assistant."
    )

    history = get_recent_history(user_id, limit=8)
    messages = [{"role": "system", "content": system_prompt}] + history

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    await asyncio.sleep(random.uniform(1.5, 2.5))

    bot_reply = get_ai_response(messages)
    
    # Emojis cleanup
    clean_reply = bot_reply.encode('ascii', 'ignore').decode('ascii').strip()
    if not clean_reply:
        clean_reply = "Arey bolo na, sun rahi hoon tumhari baat."

    save_chat_message(user_id, "assistant", clean_reply)
    await update.message.reply_text(clean_reply)

# ==================== WEB SERVER (RENDER KEEP-ALIVE) ====================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is alive and running 24/7!")

    def log_message(self, format, *args):
        return

def run_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthCheckHandler)
    server.serve_forever()

# ==================== MAIN ====================
def main():
    t = threading.Thread(target=run_health_server, daemon=True)
    t.start()
    print(f"Health server running on port {PORT}")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("addsub", addsub_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Dream Girl Bot live ho gaya hai...")
    app.run_polling()

if __name__ == "__main__":
    main()
