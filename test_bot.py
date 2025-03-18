import os
import json
import requests
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

# 🔹 Загружаем переменные окружения
load_dotenv()

# 🔹 API-ключи и данные
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")

# 🔹 SIPNET ДАННЫЕ
SIPNET_LOGIN = os.getenv("SIPNET_LOGIN")
SIPNET_PASSWORD = os.getenv("SIPNET_PASSWORD")
SHLAGBAUM_NUMBER = os.getenv("SHLAGBAUM_NUMBER")

# 🔹 ID группы для неизвестных вопросов
GROUP_CHAT_ID = -1002461315654

# 🔹 Проверяем переменные окружения
if not all([OPENAI_API_KEY, TELEGRAM_BOT_TOKEN, GOOGLE_CREDENTIALS_JSON, SIPNET_LOGIN, SIPNET_PASSWORD, SHLAGBAUM_NUMBER]):
    print("❌ Ошибка! Не найдены все необходимые переменные окружения.")
    exit(1)

# 🔹 Создаём бота
bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# 🔹 Подключаемся к Google Sheets
try:
    creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    gc = gspread.authorize(creds)

    # 🔹 Открываем таблицу
    SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1gVa34e1k0wpjantVq91IQV7TxMDrZiZpSKWrz8IBpmo/edit?gid=0"
    spreadsheet = gc.open_by_url(SPREADSHEET_URL)
    sheet = spreadsheet.sheet1  # первый лист
    print("✅ Успешно подключились к Google Sheets!")
except Exception as e:
    print(f"❌ Ошибка подключения к Google Sheets: {e}")
    exit(1)

# 🔹 Храним ID звонка для SIPNET
REGISTERED_PHONE_ID = None

# 🔹 Функция регистрации номера в SIPNET
def register_phone():
    global REGISTERED_PHONE_ID
    url = "https://newapi.sipnet.ru/api.php"
    headers = {"Content-Type": "application/json"}
    params = {
        "operation": "registerphone1",
        "sipuid": SIPNET_LOGIN,
        "password": SIPNET_PASSWORD,
        "Phone": SHLAGBAUM_NUMBER,
        "format": "json"
    }

    try:
        response = requests.post(url, headers=headers, json=params)
        data = response.json()
        print(f"🔹 Ответ SIPNET (регистрация телефона): {data}")

        if "id" in data:
            REGISTERED_PHONE_ID = data["id"]
            print(f"✅ Телефон зарегистрирован! ID: {REGISTERED_PHONE_ID}")
            return REGISTERED_PHONE_ID
        else:
            error_message = data.get("errorMessage", "Неизвестная ошибка")
            print(f"⚠️ Ошибка SIPNET (регистрация телефона): {error_message}")
            return None
    except Exception as e:
        print(f"❌ Ошибка при регистрации телефона: {e}")
        return None

# 🔹 Функция вызова шлагбаума
def call_gate():
    global REGISTERED_PHONE_ID
    if not REGISTERED_PHONE_ID:
        REGISTERED_PHONE_ID = register_phone()
        if not REGISTERED_PHONE_ID:
            return "❌ Ошибка регистрации телефона в SIPNET."

    url = "https://newapi.sipnet.ru/api.php"
    headers = {"Content-Type": "application/json"}
    params = {
        "operation": "genCall",
        "id": REGISTERED_PHONE_ID,
        "DstPhone": SHLAGBAUM_NUMBER,
        "format": "json"
    }

    try:
        response = requests.post(url, headers=headers, json=params)
        data = response.json()
        print(f"🔹 Ответ SIPNET (вызов шлагбаума): {data}")

        if data.get("status") == "success":
            call_id = data.get("id", "неизвестно")
            print(f"✅ Вызов успешно отправлен! ID звонка: {call_id}")
            return f"✅ Звонок на шлагбаум отправлен! (ID: {call_id})"
        else:
            error_message = data.get("errorMessage", "Неизвестная ошибка")
            print(f"⚠️ Ошибка SIPNET: {error_message}")
            return f"⚠️ Ошибка SIPNET: {error_message}"
    except Exception as e:
        print(f"❌ Ошибка при выполнении запроса: {e}")
        return f"❌ Ошибка при выполнении запроса: {e}"

# 🔹 Обработчик команды /open_gate
@dp.message(Command("open_gate"))
async def open_gate_command(message: types.Message):
    user_id = message.from_user.id
    print(f"📞 Пользователь {user_id} запросил открытие шлагбаума")

    response = call_gate()
    await message.answer(response)

# 🔹 Обработчик команды /check_call
@dp.message(Command("check_call"))
async def check_call_command(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Используй команду так: /check_call <ID звонка>")
        return

    call_id = args[1]
    url = "https://newapi.sipnet.ru/api.php"
    headers = {"Content-Type": "application/json"}
    params = {
        "operation": "calls2",
        "sipuid": SIPNET_LOGIN,
        "password": SIPNET_PASSWORD,
        "id": call_id,
        "format": "json"
    }

    try:
        response = requests.post(url, headers=headers, json=params)
        data = response.json()
        print(f"🔹 История звонка (ID {call_id}): {data}")

        if "calls" in data and data["calls"]:
            await message.answer(f"✅ Звонок найден! Данные: {json.dumps(data['calls'], indent=2, ensure_ascii=False)}")
        else:
            await message.answer(f"⚠️ Ошибка SIPNET: {data.get('errorMessage', 'Звонок не найден')}")
    except Exception as e:
        await message.answer(f"❌ Ошибка при выполнении запроса: {e}")

# 🔹 Запуск бота
async def main():
    print("🚀 Бот запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
