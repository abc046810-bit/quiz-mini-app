from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse
import sqlite3
import pdfplumber
import re
import os
import asyncio

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
APP_URL = os.getenv("APP_URL", "https://your-app.onrender.com")

# ================== FASTAPI ==================
app = FastAPI()

# ================== DATABASE ==================
conn = sqlite3.connect("quiz.db", check_same_thread=False)
c = conn.cursor()

c.execute("""CREATE TABLE IF NOT EXISTS questions 
(subject TEXT, question TEXT, options TEXT, answer TEXT)""")

c.execute("""CREATE TABLE IF NOT EXISTS leaderboard 
(user_id INT, score INT)""")

conn.commit()

# ================== HOME ==================
@app.get("/")
def home():
    return FileResponse("index.html")

# ================== PDF UPLOAD ==================
@app.post("/upload")
async def upload_pdf(subject: str, file: UploadFile = File(...), user_id: int = 0):

    if int(user_id) != OWNER_ID:
        return {"error": "Only owner allowed"}

    content = await file.read()

    with open("temp.pdf", "wb") as f:
        f.write(content)

    text = ""
    with pdfplumber.open("temp.pdf") as pdf:
        for page in pdf.pages:
            text += (page.extract_text() or "") + "\n"

    pattern = r"Q\d+\..*?Answer:\s*[A-D]"
    matches = re.findall(pattern, text, re.DOTALL)

    count = 0

    for q in matches:
        options = re.findall(r"[A-D]\.\s*(.*)", q)
        ans_match = re.search(r"Answer:\s*([A-D])", q)

        if len(options) == 4 and ans_match:
            answer = ans_match.group(1)

            c.execute("INSERT INTO questions VALUES (?,?,?,?)",
                      (subject, q, str(options), answer))
            count += 1

    conn.commit()

    return {"status": "saved", "count": count}

# ================== GET QUIZ ==================
@app.get("/quiz")
def get_quiz(subject: str):
    data = c.execute("SELECT * FROM questions WHERE subject=?", (subject,)).fetchall()
    return data

# ================== SAVE SCORE ==================
@app.post("/score")
def save_score(user_id: int, score: int):
    c.execute("INSERT INTO leaderboard VALUES (?,?)", (user_id, score))
    conn.commit()
    return {"status": "ok"}

# ================== LEADERBOARD ==================
@app.get("/leaderboard")
def leaderboard():
    data = c.execute(
        "SELECT user_id, MAX(score) FROM leaderboard GROUP BY user_id ORDER BY MAX(score) DESC LIMIT 10"
    ).fetchall()
    return data

# ================== TELEGRAM BOT ==================
async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🚀 Open Quiz App", web_app=WebAppInfo(url=APP_URL))]
    ]
    await update.message.reply_text(
        "🔥 Quiz App खोलने के लिए नीचे क्लिक करो 👇",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================== BOT RUN ==================
async def run_bot():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN missing")
        return

    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))

    print("✅ Bot Started")

    await app_bot.initialize()
    await app_bot.start()
    await app_bot.updater.start_polling()

# ================== STARTUP EVENT ==================
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(run_bot())
