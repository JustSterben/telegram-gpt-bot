import os
import json
import requests
import asyncio
import gspread
from google.oauth2.service_account import Credentials
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# API-ключи и данные
SIPNET_LOGIN = os.getenv("SIPNET_LOGIN")  # Логин SIPNET
SIPNET_PASSWORD = os.getenv("SIPNET_PASSWORD")  # Пароль SIPNET
SHLAGBAUM_NUMBER = os.getenv("SHLAGBAUM_NUMBER")  # Номер телефона шлагбаума
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # Токен Telegram бота
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")  # Данные Google
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")  # ID группы для вопросов

# Проверяем, что все данные загружены
if not all([SIPNET_LOGIN, SIPNET_PASSWORD, SHLAGBAUM_NUMBER, BOT_TOKEN, GOOGLE_CREDENTIALS_JSON]):
    print("❌ Ошибка: Не все переменные окружения заданы!")
    exit(1)

# Инициализация бота
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Подключаемся к Google Sheets
creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
gc = gspread.authorize(creds)

# Открываем Google Таблицу
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1gVa34e1k0wpjantVq91IQV7TxMDrZiZpSKWrz8IBpmo/edit?gid=0"
spreadsheet = gc.open_by_url(SPREADSHEET_URL)
sheet = spreadsheet.sheet1  # Первый лист

# Загружаем вопросы и ответы из таблицы
def load_faq():
    try:
        data = sheet.get_all_records()
        print("📥 Данные из Google Sheets загружены:", data)

        if not data:
            print("❌ Ошибка: Таблица пустая!")
            return {}

        faq_dict = {row["Основной вопрос"].strip().lower(): row["Ответ"].strip() for row in data if row["Основной вопрос"] and row["Ответ"]}
        
        print(f"✅ Успешно загружено {len(faq_dict)} вопросов из таблицы.")
        return faq_dict
    except Exception as e:
        print(f"❌ Ошибка при загрузке FAQ: {e}")
        return {}

FAQ = load_faq()

# Обработчик сообщений из Telegram
@dp.message()
async def handle_message(message: types.Message):
    user_text = message.text.strip().lower() if message.text else None

    if not user_text:
        return

    user_id = message.from_user.id
    print(f"📩 Вопрос от пользователя (ID {user_id}): {user_text}")

    if user_text in FAQ:
        print(f"✅ Найден ответ: {FAQ[user_text]}")
        await message.answer(FAQ[user_text])
    else:
        print(f"❌ Неизвестный вопрос: '{user_text}', отправляем в группу")
        sent_message = await bot.send_message(
            GROUP_CHAT_ID,
            f"📩 <b>Новый вопрос от гостя:</b>\n❓ {user_text}\n👤 <b>ID гостя:</b> {user_id}",
            parse_mode="HTML"
        )
        await message.answer("Я пока не знаю ответа на этот вопрос, но уточню и сообщу тебе!")

# Функция для звонка через SIPNET
def call_gate():
    url = "https://www.sipnet.ru/api/callback.php"  # Проверь правильность URL
    params = {
        "operation": "genCall",
        "sipuid": SIPNET_LOGIN,
        "password": SIPNET_PASSWORD,
        "DstPhone": SHLAGBAUM_NUMBER,
        "format": "json",
        "lang": "ru"
    }

    try:
        response = requests.get(url, params=params)

        if response.status_code != 200:
            return f"⚠️ Ошибка SIPNET: Код {response.status_code}"

        try:
            data = response.json()
        except json.JSONDecodeError:
            return "❌ Ошибка: пустой ответ от SIPNET"

        if "id" in data:
            return "✅ Звонок на шлагбаум отправлен!"
        else:
            return f"⚠️ Ошибка SIPNET: {data.get('error', 'Неизвестная ошибка')}"

    except Exception as e:
        return f"❌ Ошибка при выполнении запроса: {e}"

# Команда для открытия шлагбаума
@dp.message(Command("open_gate"))
async def open_gate_command(message: types.Message):
    user_id = message.from_user.id
    print(f"📞 Пользователь {user_id} запросил открытие шлагбаума")

    response = call_gate()
    await message.answer(response)

# Запуск бота
async def main():
    print("🚀 Бот запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
