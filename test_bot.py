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
GROUP_CHAT_ID = -1002461315654

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

# Подключаемся к Google Таблице
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
sheet = spreadsheet.sheet1  # используем первый лист

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

# Функция обработки вопроса через ChatGPT
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
        model="gpt-3.5",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip().lower()

# Обработчик сообщений (фильтр на группу и гостей)
@dp.message()
async def handle_message(message: Message):
    user_text = message.text.strip().lower() if message.text else None

    # Проверяем, пришло ли сообщение из группы
    if message.chat.id == GROUP_CHAT_ID:
        print(f"📨 Сообщение в группе (Chat ID: {message.chat.id}): '{user_text}'")

        # Если это ответ на сообщение (Reply), значит админ отвечает на вопрос
        if message.reply_to_message:
            print("📝 Это ответ на вопрос, передаем в обработку.")
            await handle_group_reply(message)
        else:
            print("⚠ Игнорируем сообщение в группе, это не ответ.")
        return

    # Обработка сообщений от гостей (личные сообщения боту)
    if not user_text:
        print(f"⚠ Бот получил НЕ текстовое сообщение (тип: {message.content_type})")
        return

    user_id = message.from_user.id
    print(f"📩 Вопрос от пользователя (ID {user_id}): {user_text}")

    matched_question = await process_question_with_gpt(user_text)

    if matched_question in FAQ:
        print(f"✅ Найден ответ: '{matched_question}'")
        await message.answer(FAQ[matched_question])
    else:
        print(f"❌ Неизвестный вопрос: '{user_text}', отправляем в группу")

        sent_message = await bot.send_message(
            GROUP_CHAT_ID,
            f"📩 <b>Новый вопрос от гостя:</b>\n❓ {user_text}\n👤 <b>ID гостя:</b> {user_id}\n\n✍ Напишите ответ на этот вопрос, и он будет отправлен гостю автоматически.",
            parse_mode="HTML"
        )

        # Сохраняем связь: ID сообщения в группе → ID гостя
        pending_questions[sent_message.message_id] = user_id

        await message.answer("Я пока не знаю ответа на этот вопрос, но могу уточнить у хозяина.")

# Обработчик ответов в группе (отправка гостю)
async def handle_group_reply(message: Message):
    print(f"📨 Получено сообщение в группе: '{message.text}' (Chat ID: {message.chat.id}, Message ID: {message.message_id})")

    if message.chat.id != GROUP_CHAT_ID:
        return  # Если сообщение не из нужной группы, игнорируем

    print("✅ Бот видит сообщение в группе!")

    if not message.reply_to_message:
        print("⚠ Бот не видит, что это ответ на сообщение.")
        await message.reply("⚠ Ошибка: Ответьте на сообщение с вопросом, чтобы бот понял, кому отправить.")
        return

    original_message_id = message.reply_to_message.message_id
    print(f"📝 Это ответ на сообщение ID: {original_message_id}")

    if original_message_id in pending_questions:
        guest_id = pending_questions.pop(original_message_id)
        response_text = message.text.strip()

        print(f"✅ Отправляем ответ гостю (ID {guest_id}): '{response_text}'")
        await bot.send_message(guest_id, f"💬 Ответ на ваш вопрос:\n{response_text}")
        await message.reply("✅ Ответ отправлен гостю!")
    else:
        print(f"❌ Ошибка: Вопрос с ID {original_message_id} не найден в pending_questions.")
        await message.reply("⚠ Ошибка: Не могу найти гостя, которому нужно отправить ответ.")

# Запуск бота
async def main():
    print("🚀 Бот запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
