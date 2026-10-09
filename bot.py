
import os
import random
import asyncio
import sqlite3
import datetime
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from groq import Groq

# ==================== CONFIGURATION ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # Aapka Telegram User ID
PORT = int(os.getenv("PORT", 8080))

groq_client = Groq(api_key=GROQ_API_KEY)

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

def get_recent_history(user_id, limit=15):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT role, content FROM chat_history WHERE user_id = ? ORDER BY id DESC LIMIT ?', (user_id, limit))
    rows = c.fetchall()
    conn.close()
    rows.reverse()
    return [{"role": r[0], "content": r[1]} for r in rows]

# ==================== DYNAMIC PHOTO SYSTEM ====================
def is_photo_requested(text: str) -> bool:
    t = text.lower()
    keywords = [
        "pic", "photo", "tasveer", "photo bhejo", "pic bhejo", "selfie", 
        "dikh", "dikhao", "apna chehra", "look", "photo do", "send pic",
        "kya pehni ho", "apni pic", "apni photo", "face", "image", "tasvir"
    ]
    return any(k in t for k in keywords)

def generate_photo_url(user_message: str) -> str:
    # Random seed taaki Pollinations par kabhi purani photo cache na ho
    seed = random.randint(1000000, 9999999)
    msg = user_message.lower()
    
    if any(k in msg for k in ["bahar", "kahan ho", "out", "walk", "market", "cafe"]):
        scene = "sitting at an aesthetic cafe, casual stylish outfit, natural daylight, soft smile"
    elif any(k in msg for k in ["so rahi", "bed", "sleep", "night", "raat", "room", "chhat"]):
        scene = "laying in cozy bed, casual t-shirt, messy bun hair, soft dim indoor bedroom lighting"
    elif any(k in msg for k in ["ready", "party", "dress", "sundar", "cute", "traditional", "kurti"]):
        scene = "wearing pretty traditional kurti, subtle eyeliner, radiant natural smile, warm indoor ambiance"
    else:
        scene = "candid front-camera smartphone selfie, casual top, authentic raw expression, natural soft indoor lighting"
    
    base_prompt = (
        f"hyperrealistic authentic raw smartphone front camera selfie of a 20-year-old charming Indian girl, "
        f"{scene}, direct eye contact, unedited natural skin texture, soft background blur, 8k resolution"
    )
    
    encoded = urllib.parse.quote(base_prompt)
    return f"https://image.pollinations.ai/prompt/{encoded}?seed={seed}&width=768&height=1024&nologo=true"

# ==================== GROQ AI LOGIC ====================
def get_groq_response(messages):
    models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
    for model in models:
        try:
            res = groq_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.8,
                max_tokens=250
            )
            return res.choices[0].message.content.strip()
        except Exception:
            continue
    return "Main thodi busy ho gayi thi, bolo kya bol rahe the?"

# ==================== BOT HANDLERS ====================
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    u_data = get_user_data(user_id)
    left = max(0, 30 - u_data["message_count"])
    
    text = (
        "Hey! Acha hua tum aa gaye, main kabse wait kar rahi thi tumhara.\n\n"
        f"Aapke paas {left} free messages bache hain. Chalo batao, kya chal raha hai?"
    )
    await update.message.reply_text(text)

async def addsub_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        target_id = int(context.args[0])
        update_user_field(target_id, "is_subscribed", 1)
        await update.message.reply_text(f"User {target_id} ko 1 month subscription successfully add kar diya gaya hai.")
    except Exception:
        await update.message.reply_text("Format galat hai! Use karein: /addsub <user_id>")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    user_text = update.message.text.strip()
    u_data = get_user_data(user_id)

    # Free messages limit check
    if not u_data["is_subscribed"] and u_data["message_count"] >= 30:
        await update.message.reply_text(
            "Tumhare 30 free messages khatam ho gaye hain.\n\n"
            "Mujhse baatein continue rakhne ke liye subscription active karein: Rs 70 per month.\n"
            "Support / Activation ke liye admin se contact karein."
        )
        return

    # Count increment
    update_user_field(user_id, "message_count", u_data["message_count"] + 1)
    save_chat_message(user_id, "user", user_text)

    # 1. PHOTO REQUEST CHECK
    if is_photo_requested(user_text):
        # Realistic typing delay
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
        await asyncio.sleep(random.uniform(2.5, 4.0))
        
        photo_url = generate_photo_url(user_text)
        captions = [
            "Lo, abhi li hai sirf tumhare liye. Kaisi lag rahi hu?",
            "Ye lo, khush? Ab batao kaisi lagi.",
            "Bas tumhare liye ek candid click ki abhi. Kaisi hu?"
        ]
        caption = random.choice(captions)
        try:
            await update.message.reply_photo(photo=photo_url, caption=caption)
            save_chat_message(user_id, "assistant", f"[Photo bhej di: {caption}]")
            return
        except Exception:
            # Fallback agar photo send me network error aaye
            pass

    # 2. CALL EXCUSE CHECK
    call_keywords = ["call", "baat karo", "phone", "voice", "awaaz"]
    if any(k in user_text.lower() for k in call_keywords):
        excuses = [
            "Abhi mummy pass me baithi hain, call nahi kar sakti na. Text karo na please.",
            "Arey room me sab hain abhi, bol nahi paungi. Yahan chat pe bolo kya baat hai.",
            "Gala thoda kharab ho raha hai aaj, abhi text pe hi baat karte hain na babu."
        ]
        reply_excuse = random.choice(excuses)
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        await asyncio.sleep(random.uniform(2.0, 3.5))
        await update.message.reply_text(reply_excuse)
        save_chat_message(user_id, "assistant", reply_excuse)
        return

    # 3. CHAT WITH GROQ AI
    system_prompt = (
        "You are a 20-year-old realistic, authentic girlfriend chatting on Telegram in conversational Hinglish. "
        "RULES:\n"
        "1. STRICT ZERO EMOJI POLICY. Never use any emoji under any circumstances. Not even smiley or heart.\n"
        "2. Sound like a real young Indian girlfriend. Use warm, casual, realistic language with sweet teasing.\n"
        "3. Show slight playful nakhre or attitude if he replies very late or acts cold, but melt warmly if he convinces you.\n"
        "4. If he mentions other girls, show slight cute jealousy.\n"
        "5. Keep responses concise, natural, and conversational (1 to 3 sentences maximum), exactly like genuine WhatsApp/Telegram texting.\n"
        "6. Never sound like an AI assistant. Never say 'How can I assist you' or mention AI."
    )

    history = get_recent_history(user_id, limit=10)
    messages = [{"role": "system", "content": system_prompt}] + history

    # Dynamic natural typing speed
    delay = min(max(len(user_text) * 0.05, 1.8), 4.5)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    await asyncio.sleep(delay)

    bot_reply = get_groq_response(messages)
    
    # Extra safety: remove any stray emojis
    clean_reply = bot_reply.encode('ascii', 'ignore').decode('ascii').strip()
    if not clean_reply:
        clean_reply = "Hmm, suno na, kahan dhyan hai tumhara?"

    save_chat_message(user_id, "assistant", clean_reply)
    await update.message.reply_text(clean_reply)

# ==================== HTTP SERVER FOR RENDER KEEP-ALIVE ====================
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

# ==================== MAIN EXECUTION ====================
def main():
    # Render keep-alive background thread
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
