import os
import json
import asyncio
import requests
import gspread
from google.oauth2.service_account import Credentials
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from openai import OpenAI
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# API-ключи
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS")
SIPNET_LOGIN = os.getenv("SIPNET_LOGIN")
SIPNET_PASSWORD = os.getenv("SIPNET_PASSWORD")
SHLAGBAUM_NUMBER = os.getenv("SHLAGBAUM_NUMBER")

# ID группы, куда отправляются неизвестные вопросы
GROUP_CHAT_ID = -1002461315654

# Проверяем, что все данные загружены
if not all([OPENAI_API_KEY, TELEGRAM_BOT_TOKEN, GOOGLE_CREDENTIALS_JSON, SIPNET_LOGIN, SIPNET_PASSWORD, SHLAGBAUM_NUMBER]):
    print("❌ Ошибка! Не найдены все переменные окружения.")
    exit(1)

# Создаём бота и диспетчер
bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Подключаемся к Google Sheets
creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
gc = gspread.authorize(creds)

# Открываем Google Таблицу
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1gVa34e1k0wpjantVq91IQV7TxMDrZiZpSKWrz8IBpmo/edit?gid=0"
spreadsheet = gc.open_by_url(SPREADSHEET_URL)
sheet = spreadsheet.sheet1  # Используем первый лист

# Храним, кто задал вопрос (формат: {ID сообщения в группе: ID гостя})
pending_questions = {}

# Функция загрузки FAQ из Google Sheets
def load_faq():
    try:
        data = sheet.get_all_records()
        print("📥 Данные из Google Sheets загружены:", data)

        if not data:
            print("❌ Ошибка: Google Sheets пустая!")
            return {}

        headers = {key.strip().replace("\t", "").replace("\n", ""): key for key in data[0].keys()}
        question_key = next((key for key in headers if "вопрос" in key.lower()), None)
        answer_key = next((key for key in headers if "ответ" in key.lower()), None)

        if not question_key or not answer_key:
            print("❌ Ошибка: Нет колонок 'Основной вопрос' или 'Ответ' в таблице!")
            return {}

        faq_dict = {}
        for row in data:
            question = row.get(question_key, "").strip().lower()
            answer = row.get(answer_key, "").strip()
            if question and answer:
                faq_dict[question] = answer

        print(f"✅ Успешно загружено {len(faq_dict)} вопросов из таблицы.")
        return faq_dict

    except Exception as e:
        print(f"❌ Ошибка при загрузке FAQ: {e}")
        return {}

# Загружаем FAQ
FAQ = load_faq()
if not FAQ:
    print("⚠ Внимание: FAQ пуст! Бот может не отвечать на вопросы.")

# Функция вызова SIPNET API для звонка на шлагбаум
def call_gate():
    url = "https://www.sipnet.ru/api/call"
    params = {
        "operation": "genCall",
        "sipuid": SIPNET_LOGIN,
        "password": SIPNET_PASSWORD,
        "DstPhone": SHLAGBAUM_NUMBER,
        "format": "json"
    }

    try:
        response = requests.get(url, params=params)
        data = response.json()

        if "id" in data:
            return "✅ Звонок на шлагбаум отправлен!"
        else:
            return f"⚠️ Ошибка SIPNET: {data.get('error', 'Неизвестная ошибка')}"

    except Exception as e:
        return f"❌ Ошибка при выполнении запроса: {e}"

# Обработчик команды /start
@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer("👋 Привет! Я могу ответить на вопросы о доме и открыть шлагбаум. Используй команду /open_gate 🚪")

# Обработчик команды /open_gate
@dp.message(Command("open_gate"))
async def open_gate_command(message: types.Message):
    user_id = message.from_user.id
    print(f"📞 Пользователь {user_id} запросил открытие шлагбаума")

    # Совершаем звонок через SIPNET
    response = call_gate()
    await message.answer(response)

# Обработчик сообщений (вопросы из Google Sheets)
@dp.message()
async def handle_message(message: Message):
    user_text = message.text.strip().lower() if message.text else None

    if message.chat.id == GROUP_CHAT_ID:
        if message.reply_to_message:
            await handle_group_reply(message)
        return

    if not user_text:
        return

    user_id = message.from_user.id
    print(f"📩 Вопрос от пользователя (ID {user_id}): {user_text}")

    if user_text in FAQ:
        print(f"✅ Найден ответ: '{user_text}'")
        await message.answer(FAQ[user_text])
    else:
        print(f"❌ Неизвестный вопрос: '{user_text}', отправляем в группу")

        sent_message = await bot.send_message(
            GROUP_CHAT_ID,
            f"📩 <b>Новый вопрос от гостя:</b>\n❓ {user_text}\n👤 <b>ID гостя:</b> {user_id}\n\n✍ Напишите ответ на этот вопрос, и он будет отправлен гостю автоматически.",
            parse_mode="HTML"
        )

        pending_questions[sent_message.message_id] = user_id
        await message.answer("Я пока не знаю ответа на этот вопрос, но могу уточнить у хозяина.")

# Обработчик ответов в группе (отправка гостю)
async def handle_group_reply(message: Message):
    if message.chat.id != GROUP_CHAT_ID:
        return

    if not message.reply_to_message:
        await message.reply("⚠ Ошибка: Ответьте на сообщение с вопросом, чтобы бот понял, кому отправить.")
        return

    original_message_id = message.reply_to_message.message_id

    if original_message_id in pending_questions:
        guest_id = pending_questions.pop(original_message_id)
        response_text = message.text.strip()

        await bot.send_message(guest_id, f"💬 Ответ на ваш вопрос:\n{response_text}")
        await message.reply("✅ Ответ отправлен гостю!")
    else:
        await message.reply("⚠ Ошибка: Не могу найти гостя, которому нужно отправить ответ.")

# Запуск бота
async def main():
    print("🚀 Бот запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
