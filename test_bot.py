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

# 🔹 Проверяем, что все переменные заданы
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

# 🔹 Храним, кто задал вопрос (формат: {ID сообщения в группе: ID гостя})
pending_questions = {}

# 🔹 Функция загрузки вопросов из Google Sheets
def load_faq():
    try:
        data = sheet.get_all_records()
        print("📥 Данные из Google Sheets загружены:", data)

        if not data:
            print("❌ Ошибка: Google Sheets пустая!")
            return {}

        headers = {key.strip(): key for key in data[0].keys()}
        question_key = next((key for key in headers if "вопрос" in key.lower()), None)
        answer_key = next((key for key in headers if "ответ" in key.lower()), None)

        if not question_key or not answer_key:
            print("❌ Ошибка: В таблице нет колонок 'Основной вопрос' или 'Ответ'!")
            return {}

        faq_dict = {row.get(question_key, "").strip().lower(): row.get(answer_key, "").strip() for row in data if row.get(question_key)}
        print(f"✅ Загружено {len(faq_dict)} вопросов из таблицы.")
        return faq_dict
    except Exception as e:
        print(f"❌ Ошибка загрузки FAQ: {e}")
        return {}

# 🔹 Загружаем FAQ
FAQ = load_faq()

# 🔹 Функция обработки вопроса через GPT
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

import requests
import json

# 🔹 Функция регистрации номера в SIPNET (Шаг 1)
def register_phone():
    """Регистрирует номер телефона и получает ID для дальнейшего вызова."""
    url = "https://newapi.sipnet.ru/api.php"
    headers = {"Content-Type": "application/json"}
    params = {
        "operation": "registerphone1",
        "sipuid": SIPNET_LOGIN,   # Логин в SIPNET
        "password": SIPNET_PASSWORD,  # Пароль в SIPNET
        "Phone": SHLAGBAUM_NUMBER,   # Номер телефона для регистрации
        "format": "json"
    }

    try:
        response = requests.post(url, headers=headers, json=params)
        data = response.json()
        print(f"🔹 Ответ SIPNET (регистрация телефона): {data}")

        if "id" in data:
            call_id = data["id"]
            print(f"✅ Телефон зарегистрирован! ID: {call_id}")
            return call_id
        else:
            error_message = data.get("errorMessage", "Неизвестная ошибка")
            print(f"⚠️ Ошибка SIPNET (регистрация телефона): {error_message}")
            return None

    except Exception as e:
        print(f"❌ Ошибка при регистрации телефона: {e}")
        return None


# 🔹 Функция вызова шлагбаума (Шаг 2)
def call_gate(call_id):
    """Вызывает звонок на шлагбаум, используя полученный ID."""
    url = "https://newapi.sipnet.ru/api.php"
    headers = {"Content-Type": "application/json"}
    params = {
        "operation": "genCall",
        "id": call_id,  # Используем ID, полученный ранее
        "DstPhone": SHLAGBAUM_NUMBER,  # Номер шлагбаума
        "format": "json"
    }

    try:
        response = requests.post(url, headers=headers, json=params)
        data = response.json()
        print(f"🔹 Ответ SIPNET (звонок на шлагбаум): {data}")

        if "id" in data:
            call_id = data["id"]
            print(f"✅ Вызов успешно отправлен! ID звонка: {call_id}")
            return f"✅ Звонок на шлагбаум отправлен! (ID: {call_id})"
        else:
            error_message = data.get("errorMessage", "Неизвестная ошибка")
            print(f"⚠️ Ошибка SIPNET (звонок): {error_message}")
            return f"⚠️ Ошибка SIPNET: {error_message}"

    except Exception as e:
        print(f"❌ Ошибка при выполнении запроса: {e}")
        return f"❌ Ошибка при выполнении запроса: {e}"
        
import requests

def check_sipnet_call(call_id):
    url = "https://newapi.sipnet.ru/api.php"  # Новый URL API SIPNET
    headers = {"Content-Type": "application/json"}
    params = {
        "operation": "calls2",
        "sipuid": SIPNET_LOGIN,   # Твой логин в SIPNET
        "password": SIPNET_PASSWORD,  # Твой пароль в SIPNET
        "callid": call_id,   # ID звонка, который мы хотим проверить
        "format": "json"
    }

    try:
        response = requests.post(url, headers=headers, json=params)
        data = response.json()
        print(f"📞 История звонка (ID {call_id}): {data}")
        return data
    except Exception as e:
        print(f"❌ Ошибка при проверке истории звонка: {e}")
        return None

# 🔹 Функция проверки статуса звонка в SIPNET
def check_sipnet_call(call_id):
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
        print(f"🔹 Ответ SIPNET (история вызовов): {data}")

        if "calls" in data and data["calls"]:
            return f"✅ Звонок найден! Данные: {data['calls']}"
        else:
            return f"⚠️ Ошибка SIPNET: {data.get('errorMessage', 'Звонок не найден')}"

    except Exception as e:
        return f"❌ Ошибка при выполнении запроса: {e}"

# 🔹 Обработчик команды /open_gate
@dp.message(Command("open_gate"))
async def open_gate_command(message: types.Message):
    user_id = message.from_user.id
    print(f"📞 Пользователь {user_id} запросил открытие шлагбаума")

    response = call_gate()
    await message.answer(response)

# 🔹 Обработчик сообщений гостей
@dp.message()
async def handle_message(message: Message):
    user_text = message.text.strip().lower() if message.text else None

    # 🔹 Если сообщение из группы
    if message.chat.id == GROUP_CHAT_ID:
        if message.reply_to_message:
            await handle_group_reply(message)
        return

    # 🔹 Обработка сообщений от гостей
    if not user_text:
        return

    user_id = message.from_user.id
    print(f"📩 Вопрос от пользователя (ID {user_id}): {user_text}")

    matched_question = await process_question_with_gpt(user_text)

    if matched_question in FAQ:
        await message.answer(FAQ[matched_question])
    else:
        sent_message = await bot.send_message(
            GROUP_CHAT_ID,
            f"📩 <b>Новый вопрос от гостя:</b>\n❓ {user_text}\n👤 <b>ID гостя:</b> {user_id}\n\n✍ Напишите ответ на этот вопрос, и он будет отправлен гостю автоматически.",
            parse_mode="HTML"
        )

        pending_questions[sent_message.message_id] = user_id
        await message.answer("Я пока не знаю ответа, но уточню у хозяина.")

# 🔹 Обработчик ответов в группе
async def handle_group_reply(message: Message):
    if message.chat.id != GROUP_CHAT_ID or not message.reply_to_message:
        return

    original_message_id = message.reply_to_message.message_id
    if original_message_id in pending_questions:
        guest_id = pending_questions.pop(original_message_id)
        await bot.send_message(guest_id, f"💬 Ответ на ваш вопрос:\n{message.text.strip()}")
        await message.reply("✅ Ответ отправлен гостю!")

# 🔹 Обработчик команды /check_call
@dp.message(Command("check_call"))
async def check_call_command(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Используй команду так: /check_call <ID звонка>")
        return

    call_id = args[1]
    response = check_sipnet_call(call_id)

    if response:
        await message.answer(f"📞 История звонка: {json.dumps(response, indent=2, ensure_ascii=False)}")
    else:
        await message.answer("⚠️ Ошибка: не удалось получить информацию о звонке.")

# 🔹 Запуск бота
async def main():
    print("🚀 Бот запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
