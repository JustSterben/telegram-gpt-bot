import os
import requests
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# API-ключи и данные для SIPNET
SIPNET_LOGIN = os.getenv("SIPNET_LOGIN")  # Логин SIPNET
SIPNET_PASSWORD = os.getenv("SIPNET_PASSWORD")  # Пароль SIPNET
SHLAGBAUM_NUMBER = os.getenv("SHLAGBAUM_NUMBER")  # Номер телефона шлагбаума
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # Токен Telegram бота

# Проверяем, что все данные загружены
if not all([SIPNET_LOGIN, SIPNET_PASSWORD, SHLAGBAUM_NUMBER, BOT_TOKEN]):
    print("❌ Ошибка: Не все переменные окружения заданы!")
    exit(1)

# Инициализация бота
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Функция для звонка через SIPNET
def call_gate():
    url = "https://www.sipnet.ru/api/callback.php"  # Проверь, что этот URL правильный
    params = {
        "operation": "genCall",
        "sipuid": SIPNET_LOGIN,
        "password": SIPNET_PASSWORD,
        "DstPhone": SHLAGBAUM_NUMBER,  # Номер шлагбаума
        "format": "json",
        "lang": "ru"
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
    await message.answer("👋 Привет! Я могу открыть шлагбаум. Используй команду /open_gate 🚪")

# Обработчик команды /open_gate
@dp.message(Command("open_gate"))
async def open_gate_command(message: types.Message):
    user_id = message.from_user.id
    print(f"📞 Пользователь {user_id} запросил открытие шлагбаума")

    # Совершаем звонок через SIPNET
    response = call_gate()
    await message.answer(response)

# Запуск бота
async def main():
    print("🚀 Бот успешно запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
