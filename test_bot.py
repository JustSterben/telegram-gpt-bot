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
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS")  # Данные из credentials.json

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
creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)  # Декодируем JSON из переменной

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
    data = sheet.get_all_records()  # Получаем все записи
    print("📥 Данные из Google Sheets:", data)  # Вывод всех данных
    print("🔍 Ключи первой строки таблицы:", list(data[0].keys()))  # Вывод заголовков
    

    if not data:
        print("❌ Ошибка: Google Sheets пустая или не читается")
        return {}

    # Очищаем заголовки от скрытых символов (\t, пробелы, лишние символы)
    headers = {key.strip().replace("\t", "").replace("\n", ""): key for key in data[0].keys()}
    print("🔍 Исправленные ключи таблицы:", headers)  # Вывод в логи

    # Проверяем, какие ключи бот будет использовать
    question_key = headers.get("Основной вопрос", None)
    answer_key = headers.get("Ответ", None)

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

    print("✅ Загруженные вопросы:", list(faq_dict.keys()))  # Проверяем загруженные вопросы
    return faq_dict

FAQ = load_faq()

# Функция поиска наиболее похожего вопроса
def find_best_match(user_question, faq_dict):
    """Находит наиболее похожий вопрос в базе"""
    matches = get_close_matches(user_question, faq_dict.keys(), n=1, cutoff=0.6)
    print(f"🔍 Поиск совпадений для: '{user_question}' → Найдено: {matches}")
    return matches[0] if matches else None

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
    print(f"📩 Вопрос от пользователя: {user_text}")  # Логируем вопрос

    # Найдём наиболее похожий вопрос в базе
    matched_question = find_best_match(user_text, FAQ)

    if matched_question:
        print(f"✅ Совпадение найдено: '{matched_question}' → Отправляем ответ")
        await message.answer(FAQ[matched_question])  # Отправляем ответ из базы
    else:
        print(f"❌ Совпадение не найдено для: '{user_text}' → Отправляем в Telegram-группу")
        await message.answer("Я пока не знаю ответа на этот вопрос, но могу уточнить у хозяина. Напишите подробнее, что вас интересует, и я передам информацию.")
        await send_to_group(user_text, message.from_user.id)  # Отправляем вопрос в Telegram-группу

# Функция запуска бота
async def main():
    print("🚀 Бот успешно запущен на Railway!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

# Запуск
if __name__ == "__main__":
    asyncio.run(main())
