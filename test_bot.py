import os
import json
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

# Загружаем переменные окружения
load_dotenv()

# API-ключи
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS")

# ID группы, куда отправляются неизвестные вопросы
GROUP_CHAT_ID = -4704353814

# Проверяем переменные окружения
if not OPENAI_API_KEY or not TELEGRAM_BOT_TOKEN or not GOOGLE_CREDENTIALS_JSON:
    print("❌ Ошибка! Не найдены ключи API или учетные данные Google.")
    exit(1)

# Создаём бота и диспетчер
bot = Bot(
    token=TELEGRAM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Подключение к Google Таблице
creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
gc = gspread.authorize(creds)

# Открываем Google Таблицу
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1gVa34e1k0wpjantVq91IQV7TxMDrZiZpSKWrz8IBpmo/edit?gid=0"
spreadsheet = gc.open_by_url(SPREADSHEET_URL)
sheet = spreadsheet.sheet1  # Первый лист

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

# Проверяем, загружены ли вопросы
if not FAQ:
    print("⚠ Внимание: FAQ пуст! Бот может не отвечать на вопросы.")

# Обработчик текстовых сообщений (если бот не знает ответа)
@dp.message()
async def handle_message(message: Message):
    user_text = message.text.strip().lower()
    user_id = message.from_user.id
    print(f"📩 Вопрос от пользователя (ID {user_id}): {user_text}")

    # Проверяем, есть ли ответ в FAQ
    if user_text in FAQ:
        print(f"✅ Найден ответ в FAQ: '{user_text}'")
        await message.answer(FAQ[user_text])
    else:
        print(f"❌ Неизвестный вопрос: '{user_text}', отправляем в группу")

        # Отправляем вопрос в группу
        sent_message = await bot.send_message(
            GROUP_CHAT_ID,
            f"📩 <b>Новый вопрос от гостя:</b>\n❓ {user_text}\n👤 <b>ID гостя:</b> {user_id}\n\n✍ Напишите ответ на этот вопрос, и он будет отправлен гостю автоматически.",
            parse_mode="HTML"
        )

        # Привязываем ID сообщения в группе к пользователю
        pending_questions[sent_message.message_id] = user_id

        await message.answer("Я пока не знаю ответа на этот вопрос, но могу уточнить у хозяина.")

# Обработчик ответов в группе
@dp.message()
async def handle_group_reply(message: Message):
    print(f"📨 Ответ в группе: {message.text} (ID: {message.message_id})")

    if message.chat.id == GROUP_CHAT_ID and message.reply_to_message:
        original_message_id = message.reply_to_message.message_id
        print(f"📝 Ответ привязан к сообщению ID: {original_message_id}")

        # Проверяем, есть ли сохранённый вопрос
        if original_message_id in pending_questions:
            guest_id = pending_questions.pop(original_message_id)  # Убираем связь после отправки
            response_text = message.text.strip()

            print(f"✅ Отправляем гостю (ID {guest_id}): '{response_text}'")

            # Отправляем ответ гостю
            await bot.send_message(guest_id, f"💬 Ответ на ваш вопрос:\n{response_text}")

            # Подтверждение в группе
            await message.reply("✅ Ответ отправлен гостю!")
        else:
            print("❌ Ошибка: Не найден гость, связанный с этим вопросом.")
            await message.reply("⚠ Ошибка: Я не могу найти гостя, который задал этот вопрос.")

# Запуск бота
async def main():
    print("🚀 Бот запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
