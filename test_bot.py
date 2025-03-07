import os
import asyncio
from openai import OpenAI
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

<<<<<<< HEAD
# Получаем API-ключи из переменных окружения
=======
# Получаем API-ключи
>>>>>>> b9c6fa5 (Исправлены ошибки отступов и загрузки API-ключей)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Проверяем, что ключи существуют
if not OPENAI_API_KEY or not TELEGRAM_BOT_TOKEN:
<<<<<<< HEAD
    raise ValueError("❌ Не найдены API-ключи. Проверь переменные окружения в Railway!")
=======
    print("❌ Ошибка: API-ключи не найдены!")
    print("🔹 Проверь переменные окружения в Railway.")
    exit(1)  # Завершаем работу, если ключей нет
>>>>>>> b9c6fa5 (Исправлены ошибки отступов и загрузки API-ключей)

# Создаём бота и диспетчер
bot = Bot(
    token=TELEGRAM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Функция общения с ChatGPT
async def chat_with_gpt(prompt):
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

# Обработчик команды /start
@dp.message(Command("start"))
async def start_command(message: Message):
    await message.answer("🤖 Привет! Я бот с ChatGPT, развернутый на Railway. Напиши мне что-нибудь!")

# Обработчик текстовых сообщений
@dp.message()
async def handle_message(message: Message):
    user_text = message.text
    response = await chat_with_gpt(user_text)
    await message.answer(response)

# Функция запуска бота
async def main():
    print("🚀 Бот успешно запущен на Railway!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

# Запуск
if __name__ == "__main__":
    asyncio.run(main())
