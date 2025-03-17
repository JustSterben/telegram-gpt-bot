import os
import json
import asyncio
import gspread
from google.oauth2.service_account import Credentials
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from openai import OpenAI
from dotenv import load_dotenv

# Загружаем переменные окружения из .env (Railway Variables загружаются автоматически)
load_dotenv()

# Переменные из Railway Variables (загружаются автоматически в Railway)
GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Переменные из .env
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SIPNET_LOGIN = os.getenv("SIPNET_LOGIN")
SIPNET_PASSWORD = os.getenv("SIPNET_PASSWORD")
SHLAGBAUM_NUMBER = os.getenv("SHLAGBAUM_NUMBER")

# ID группы, куда отправляются неизвестные вопросы
GROUP_CHAT_ID = -1002461315654

# Проверяем, что все переменные заданы
if not all([GOOGLE_CREDENTIALS_JSON, OPENAI_API_KEY, TELEGRAM_BOT_TOKEN, SIPNET_LOGIN, SIPNET_PASSWORD, SHLAGBAUM_NUMBER]):
    print("❌ Ошибка! Не найдены все необходимые переменные окружения.")
    exit(1)

# Инициализация бота
bot = Bot(
    token=TELEGRAM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Подключаемся к Google Таблице
creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
gc = gspread.authorize(creds)

# Открываем Google Таблицу
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1gVa34e1k0wpjantVq91IQV7TxMDrZiZpSKWrz8IBpmo/edit?gid=0"
spreadsheet = gc.open_by_url(SPREADSHEET_URL)
sheet = spreadsheet.sheet1

# Храним, кто задал вопрос (формат: {ID сообщения в группе: ID гостя})
pending_questions = {}

# Функция загрузки FAQ из Google Sheets
def load_faq():
    try:
        data = sheet.get_all_records()
        if not data:
            return {}
        
        question_key = next((key for key in data[0].keys() if "вопрос" in key.lower()), None)
        answer_key = next((key for key in data[0].keys() if "ответ" in key.lower()), None)
        
        if not question_key or not answer_key:
            return {}
        
        faq_dict = {row.get(question_key, "").strip().lower(): row.get(answer_key, "").strip() for row in data if row.get(question_key)}
        return faq_dict
    except Exception as e:
        print(f"❌ Ошибка при загрузке FAQ: {e}")
        return {}

# Загружаем FAQ
FAQ = load_faq()

# Функция обработки вопроса через ChatGPT
async def process_question_with_gpt(user_text):
    client = OpenAI(api_key=OPENAI_API_KEY)
    prompt = f"Вопрос: {user_text}. Найди наиболее похожий вопрос из списка: {', '.join(FAQ.keys())}"
    response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}])
    return response.choices[0].message.content.strip().lower()

# Обработчик сообщений от пользователей
@dp.message()
async def handle_message(message: Message):
    user_text = message.text.strip().lower() if message.text else None
    if not user_text:
        return
    user_id = message.from_user.id
    print(f"📩 Вопрос от пользователя (ID {user_id}): {user_text}")

    matched_question = await process_question_with_gpt(user_text)
    if matched_question in FAQ:
        await message.answer(FAQ[matched_question])
    else:
        sent_message = await bot.send_message(GROUP_CHAT_ID, f"📩 Новый вопрос: {user_text}\n👤 ID гостя: {user_id}")
        pending_questions[sent_message.message_id] = user_id
        await message.answer("Я уточню у владельца и скоро отвечу!")

# Запуск бота
async def main():
    print("🚀 Бот запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
