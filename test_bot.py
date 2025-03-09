import os
import asyncio
import gspread
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

# Ссылка на Google Таблицу
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1gVa34e1k0wpjantVq91IQV7TxMDrZiZpSKWrz8IBpmo/edit?gid=0"

# Проверяем, что ключи существуют
if not OPENAI_API_KEY or not TELEGRAM_BOT_TOKEN:
    print("❌ Ошибка! Не найдены ключи API.")
    exit(1)

# Создаём бота и диспетчер
bot = Bot(
    token=TELEGRAM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Подключение к Google Таблице
gc = gspread.service_account(filename="credentials.json")  # Файл с ключами Google API
spreadsheet = gc.open_by_url(GOOGLE_SHEET_URL)
sheet = spreadsheet.sheet1  # Используем первый лист

# Загружаем вопросы и ответы из таблицы
def load_faq():
    data = sheet.get_all_records()  # Получаем все записи
    faq_dict = {}
    for row in data:
        question = row.get("Вопрос", "").strip().lower()
        answer = row.get("Ответ", "").strip()
        if question and answer:
            faq_dict[question] = answer
    return faq_dict

FAQ = load_faq()

# Функция общения с ChatGPT для обработки вопросов
async def process_question_with_gpt(user_text):
    client = OpenAI(api_key=OPENAI_API_KEY)
    prompt = f"""
    Ты бот-помощник по дому, который должен помочь гостям с их вопросами.
    Если вопрос касается дома, попробуй найти наиболее подходящий вариант среди этих вопросов:

    {', '.join(FAQ.keys())}

    Если вопрос не связан с домом (например, про политику, погоду, космос), скажи: 
    'Я отвечаю только на вопросы по дому. Чем могу помочь?'

    Вопрос гостя: {user_text}
    """
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip().lower()

# Функция отправки сообщения в Telegram-группу
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

    # Сначала обрабатываем вопрос через GPT, чтобы он понял его смысл
    matched_question = await process_question_with_gpt(user_text)

    # Если GPT распознал вопрос и нашёл его в списке FAQ, даём ответ
    if matched_question in FAQ:
        await message.answer(FAQ[matched_question])
    elif "я отвечаю только на вопросы по дому" in matched_question:
        await message.answer("Я отвечаю только на вопросы по дому. Чем могу помочь?")
    else:
        await message.answer("Я пока не знаю ответа на этот вопрос, но могу уточнить у хозяина. Напишите подробнее, что вас интересует, и я передам информацию.")
        await send_to_group(user_text, message.from_user.id)  # Отправляем вопрос в группу

# Функция запуска бота
async def main():
    print("🚀 Бот успешно запущен на Railway!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

# Запуск
if __name__ == "__main__":
    asyncio.run(main())
