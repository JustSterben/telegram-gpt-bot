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

# Получаем API-ключи
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# ID группы в Telegram, куда отправлять вопросы без ответов
GROUP_CHAT_ID = -4704353814

# Проверяем, что ключи существуют
if not OPENAI_API_KEY or not TELEGRAM_BOT_TOKEN:
    print(f"🔹 OPENAI_API_KEY: {OPENAI_API_KEY}")
    print(f"🔹 TELEGRAM_BOT_TOKEN: {TELEGRAM_BOT_TOKEN}")
    exit(1)  # Завершаем работу, если ключей нет

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
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()

# Функция отправки сообщения в Telegram-группу
async def send_to_group(question, user_id):
    message_text = f"📩 <b>Новый вопрос от гостя:</b>\n❓ {question}\n\n👉 <i>Ответьте ему в чате или сообщите мне, чтобы я передал информацию.</i>"
    await bot.send_message(GROUP_CHAT_ID, message_text)

# Обработчик команды /start
@dp.message(Command("start"))
async def start_command(message: Message):
    await message.answer("🤖 Привет! Я бот, который поможет вам в доме. Задавайте вопросы!")

# Обработчик текстовых сообщений
@dp.message()
async def handle_message(message: Message):
    user_text = message.text
    response = await chat_with_gpt(user_text)

    # Проверяем, есть ли адекватный ответ от ChatGPT
    if not response or "не знаю" in response.lower() or "не уверен" in response.lower():
        await message.answer("Я пока не знаю ответа на этот вопрос, но могу уточнить у хозяина. Напишите подробнее, что вас интересует, и я передам информацию.")
        await send_to_group(user_text, message.from_user.id)  # Отправляем вопрос в группу
    else:
        await message.answer(response)

# Функция запуска бота
async def main():
    print("🚀 Бот успешно запущен на Railway!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

# Запуск
if __name__ == "__main__":
    asyncio.run(main())
