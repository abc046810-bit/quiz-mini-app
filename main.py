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

app = FastAPI()

# ================== DATABASE ==================
conn = sqlite3.connect("quiz.db", check_same_thread=False)
c = conn.cursor()

# OLD SYSTEM
c.execute("""CREATE TABLE IF NOT EXISTS questions 
(subject TEXT, question TEXT, options TEXT, answer TEXT)""")

c.execute("""CREATE TABLE IF NOT EXISTS leaderboard 
(user_id INT, score INT)""")

# NEW SYSTEM
c.execute("""CREATE TABLE IF NOT EXISTS exams
(subject TEXT, pdf TEXT)""")

c.execute("""CREATE TABLE IF NOT EXISTS answers
(subject TEXT, qno INT, ans TEXT)""")

conn.commit()

# ================== HOME ==================
@app.get("/")
def home():
    return FileResponse("index.html")

# ================== OLD PDF PARSER ==================
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

    pattern = r"(Q\d+[\.\)]\s.*?)(?=Q\d+[\.\)]|\Z)"
    blocks = re.findall(pattern, text, re.DOTALL)

    count = 0

    for q in blocks:
        options = re.findall(r"[A-D][\.\)]\s*(.*)", q)
        ans_match = re.search(r"(?:Answer|Ans)[\s:]*([A-D])", q)

        if len(options) == 4 and ans_match:
            answer = ans_match.group(1)

            c.execute("INSERT INTO questions VALUES (?,?,?,?)",
                      (subject, q, str(options), answer))
            count += 1

    conn.commit()
    return {"status": "saved", "count": count}

# ================== OLD QUIZ ==================
@app.get("/quiz")
def get_quiz(subject: str):
    return c.execute("SELECT * FROM questions WHERE subject=?", (subject,)).fetchall()

@app.post("/score")
def save_score(user_id: int, score: int):
    c.execute("INSERT INTO leaderboard VALUES (?,?)", (user_id, score))
    conn.commit()
    return {"status": "ok"}

@app.get("/leaderboard")
def leaderboard():
    return c.execute(
        "SELECT user_id, MAX(score) FROM leaderboard GROUP BY user_id ORDER BY MAX(score) DESC LIMIT 10"
    ).fetchall()

# ================== NEW EXAM SYSTEM ==================

# 📄 Upload Questions PDF
@app.post("/upload_questions")
async def upload_questions(subject: str, file: UploadFile = File(...), user_id: int = 0):

    if int(user_id) != OWNER_ID:
        return {"error": "Only owner"}

    content = await file.read()
    filename = f"{subject}.pdf"

    with open(filename, "wb") as f:
        f.write(content)

    c.execute("INSERT INTO exams VALUES (?,?)", (subject, filename))
    conn.commit()

    return {"status": "questions uploaded"}

# 🔑 Upload Answer Key
@app.post("/upload_answers")
async def upload_answers(subject: str, file: UploadFile = File(...), user_id: int = 0):

    if int(user_id) != OWNER_ID:
        return {"error": "Only owner"}

    content = await file.read()
    text = content.decode()

    for line in text.split("\n"):
        parts = line.strip().split()
        if len(parts) == 2:
            qno = int(parts[0])
            ans = parts[1].upper()
            c.execute("INSERT INTO answers VALUES (?,?,?)", (subject, qno, ans))

    conn.commit()
    return {"status": "answers uploaded"}

# 📥 Get Exam
@app.get("/exam")
def get_exam(subject: str):
    exam = c.execute("SELECT pdf FROM exams WHERE subject=?", (subject,)).fetchone()
    answers = c.execute("SELECT qno FROM answers WHERE subject=?", (subject,)).fetchall()

    return {
        "pdf": exam[0] if exam else "",
        "total": len(answers)
    }

# 🧠 Submit
@app.post("/submit")
def submit(subject: str, user_answers: dict):

    correct = 0

    for qno, ans in user_answers.items():
        real = c.execute(
            "SELECT ans FROM answers WHERE subject=? AND qno=?",
            (subject, int(qno))
        ).fetchone()

        if real and real[0] == ans:
            correct += 1

    return {"score": correct}

# ================== TELEGRAM BOT ==================
async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🚀 Open Quiz App", web_app=WebAppInfo(url=APP_URL))]
    ]
    await update.message.reply_text("Open App 👇", reply_markup=InlineKeyboardMarkup(keyboard))

async def run_bot():
    if not BOT_TOKEN:
        return

    bot = ApplicationBuilder().token(BOT_TOKEN).build()
    bot.add_handler(CommandHandler("start", start))

    await bot.initialize()
    await bot.start()
    await bot.updater.start_polling()

@app.on_event("startup")
async def startup():
    asyncio.create_task(run_bot())
