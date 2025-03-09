import os
import json
import asyncio
import gspread
from google.oauth2.service_account import Credentials
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from openai import OpenAI
from dotenv import load_dotenv
from difflib import get_close_matches

# Загружаем переменные окружения
load_dotenv()

# Получаем API-ключи
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS")

# ID группы в Telegram, куда отправлять вопросы без ответов
GROUP_CHAT_ID = -4704353814

# Проверяем, что все переменные окружения заданы
if not OPENAI_API_KEY or not TELEGRAM_BOT_TOKEN or not GOOGLE_CREDENTIALS_JSON:
    print("❌ Ошибка! Не найдены ключи API или учетные данные Google.")
    exit(1)

# Создаём бота и диспетчер
bot = Bot(
    token=TELEGRAM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Подключение к Google Таблице через переменные окружения
creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)

# ✅ Добавлены правильные OAuth-скопы
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)

# Авторизуемся в Google Sheets
gc = gspread.authorize(creds)

# Открываем Google Таблицу
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1gVa34e1k0wpjantVq91IQV7TxMDrZiZpSKWrz8IBpmo/edit?gid=0"
spreadsheet = gc.open_by_url(SPREADSHEET_URL)
sheet = spreadsheet.sheet1  # Первый лист

# Загружаем вопросы и ответы из Google Таблицы
def load_faq():
    data = sheet.get_all_records()
    print("📥 Данные из Google Sheets:", data)  

    if not data:
        print("❌ Ошибка: Google Sheets пустая или не читается")
        return {}

    # Очищаем заголовки от скрытых символов
    headers = {key.strip().replace("\t", "").replace("\n", ""): key for key in data[0].keys()}
    print("🔍 Исправленные ключи таблицы:", headers)

    # Определяем ключи
    question_key = next((key for key in headers if "вопрос" in key.lower()), None)
    answer_key = next((key for key in headers if "ответ" in key.lower()), None)

    if not question_key or not answer_key:
        print("❌ Ошибка: Не найдены столбцы 'Основной вопрос' или 'Ответ'")
        return {}

    # Заполняем словарь FAQ
    faq_dict = {}
    for row in data:
        question = row.get(question_key, "").strip().lower()
        answer = row.get(answer_key, "").strip()
        if question and answer:
            faq_dict[question] = answer

    print("✅ Загруженные вопросы:", list(faq_dict.keys()))
    return faq_dict

FAQ = load_faq()

# Функция обработки вопроса через ChatGPT для лучшего понимания
async def process_question_with_gpt(user_text):
    client = OpenAI(api_key=OPENAI_API_KEY)
    prompt = f"""
    Ты помощник по аренде дома. Гости задают вопросы о доме, удобствах, технике.
    Вот список вопросов, на которые у нас есть ответы:

    {', '.join(FAQ.keys())}

    Если вопрос похож на один из них, напиши точный вариант из списка.
    Если вопрос непонятен – просто напиши "Неизвестный вопрос".

    Вопрос гостя: {user_text}
    """
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip().lower()

# Функция отправки неизвестных вопросов в Telegram-группу
async def send_to_group(question, user_id):
    message_text = f"📩 <b>Новый вопрос от гостя:</b>\n❓ {question}\n\n👉 <i>Ответьте ему в чате или сообщите мне, чтобы я передал информацию.</i>"
    await bot.send_message(GROUP_CHAT_ID, message_text)

# Обработчик команды /start
@dp.message(Command("start"))
async def start_command(message: Message):
    await message.answer("🤖 Привет! Я бот-помощник по дому. Задавайте вопросы, и я помогу вам!")

# Обработчик текстовых сообщений
@dp.message()
async def handle_message(message: Message):
    user_text = message.text.strip().lower()
    print(f"📩 Вопрос от пользователя: {user_text}")

    # Обрабатываем вопрос через GPT, чтобы он понял его смысл
    matched_question = await process_question_with_gpt(user_text)

    # Если GPT распознал вопрос и нашёл его в списке FAQ, даём ответ
    if matched_question in FAQ:
        print(f"✅ Совпадение найдено: '{matched_question}' → Отправляем ответ")
        await message.answer(FAQ[matched_question])
    elif "неизвестный вопрос" in matched_question:
        print(f"❌ GPT не распознал вопрос: '{user_text}' → Отправляем в Telegram-группу")
        await message.answer("Я пока не знаю ответа на этот вопрос, но могу уточнить у хозяина. Напишите подробнее, что вас интересует, и я передам информацию.")
        await send_to_group(user_text, message.from_user.id)  # Отправляем вопрос в Telegram-группу
    else:
        print(f"❌ GPT предложил неизвестный вариант: '{matched_question}' → Отправляем в Telegram-группу")
        await message.answer("Я пока не знаю ответа на этот вопрос, но могу уточнить у хозяина.")
        await send_to_group(user_text, message.from_user.id)

# Функция запуска бота
async def main():
    print("🚀 Бот успешно запущен на Railway!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

# Запуск
if __name__ == "__main__":
    asyncio.run(main())
