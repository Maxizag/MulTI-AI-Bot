print("🔍 Начинаю загрузку bot.py...")

import asyncio
import logging
print("✅ asyncio и logging загружены")

from aiogram import Bot, Dispatcher, F
print("✅ aiogram загружен")

from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
print("✅ aiogram types загружены")

from config import TELEGRAM_BOT_TOKEN, MODELS, DAILY_LIMIT
print("✅ config загружен")

from database import (
    init_db, get_or_create_user, check_and_update_limit, 
    update_selected_model, get_user_info,
    save_message, get_conversation_history, clear_conversation_history,
    create_new_session, get_user_sessions, switch_session, get_current_session  # Новые функции
)
print("✅ database загружен")

from openrouter import send_message, get_model_name
print("✅ openrouter загружен")

print("🚀 Все модули загружены успешно!")

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()


# Клавиатура с выбором модели
def get_models_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for key, model in MODELS.items():
        buttons.append([
            InlineKeyboardButton(
                text=model["name"],
                callback_data=f"model_{key}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# Команда /start
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username
    )
    
    welcome_text = (
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        f"Я бот с доступом к разным AI моделям:\n\n"
    )
    
    for key, model in MODELS.items():
        welcome_text += f"{model['name']} - {model['description']}\n"
    
    welcome_text += (
        f"\n🎯 Выбери модель ниже, потом просто пиши свои вопросы!\n"
        f"📊 Лимит: {DAILY_LIMIT} запросов в день\n"
        f"💬 Все модели видят историю диалога!\n\n"
        f"Команды:\n"
        f"/start - главное меню\n"
        f"/model - сменить модель\n"
        f"/stats - статистика\n"
        f"/clear - очистить историю текущего чата\n"
        f"/new - создать новый чат\n"
        f"/chats - переключиться между чатами\n"
        f"/id - узнать свой ID"
    )
    
    await message.answer(
        welcome_text,
        reply_markup=get_models_keyboard()
    )


# Команда /model - смена модели
@dp.message(Command("model"))
async def cmd_model(message: Message):
    user = await get_user_info(message.from_user.id)
    current_model = get_model_name(user.selected_model) if user else "Не выбрана"
    
    await message.answer(
        f"Текущая модель: {current_model}\n\nВыбери новую модель:",
        reply_markup=get_models_keyboard()
    )


# Команда /stats - статистика
@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    from config import ADMIN_IDS
    
    user = await get_user_info(message.from_user.id)
    
    if not user:
        await message.answer("❌ Пользователь не найден. Используй /start")
        return
    
    current_model = get_model_name(user.selected_model)
    is_admin = message.from_user.id in ADMIN_IDS
    
    if is_admin:
        stats_text = (
            f"📊 Твоя статистика:\n\n"
            f"👑 Статус: АДМИН (безлимит)\n"
            f"🤖 Текущая модель: {current_model}\n"
            f"📝 Запросов сегодня: {user.requests_today}\n"
            f"📅 Зарегистрирован: {user.created_at.strftime('%d.%m.%Y')}"
        )
    else:
        remaining = DAILY_LIMIT - user.requests_today
        stats_text = (
            f"📊 Твоя статистика:\n\n"
            f"🤖 Текущая модель: {current_model}\n"
            f"📝 Запросов сегодня: {user.requests_today}/{DAILY_LIMIT}\n"
            f"⏳ Осталось: {remaining}\n"
            f"📅 Зарегистрирован: {user.created_at.strftime('%d.%m.%Y')}"
        )
    
    await message.answer(stats_text)


# Команда /clear - очистка истории
@dp.message(Command("clear"))
async def cmd_clear(message: Message):
    await clear_conversation_history(message.from_user.id)
    await message.answer(
        "🗑 История диалога очищена!\n\n"
        "Теперь AI не помнит предыдущих сообщений."
    )


# Команда /id - узнать свой Telegram ID
@dp.message(Command("id"))
async def cmd_id(message: Message):
    from config import ADMIN_IDS
    
    is_admin = message.from_user.id in ADMIN_IDS
    admin_status = "👑 Админ (безлимит)" if is_admin else "👤 Обычный юзер"
    
    await message.answer(
        f"🆔 Твой Telegram ID: `{message.from_user.id}`\n"
        f"Статус: {admin_status}",
        parse_mode="Markdown"
    )

    # Команда /new - создать новый чат
@dp.message(Command("new"))
async def cmd_new_chat(message: Message):
    # Создаем новый чат
    session_id = await create_new_session(message.from_user.id, "Новый чат")
    
    await message.answer(
        f"✨ Создан новый чат!\n\n"
        f"Теперь это твой активный чат. История предыдущего чата сохранена.\n"
        f"Используй /chats чтобы увидеть все чаты."
    )


# Команда /chats - список всех чатов
@dp.message(Command("chats"))
async def cmd_list_chats(message: Message):
    sessions = await get_user_sessions(message.from_user.id)
    current_session = await get_current_session(message.from_user.id)
    
    if not sessions:
        await message.answer("У тебя пока нет чатов. Напиши что-нибудь для создания первого!")
        return
    
    # Формируем список чатов
    buttons = []
    for session in sessions:
        is_current = current_session and session.session_id == current_session.session_id
        emoji = "✅ " if is_current else "💬 "
        
        # Берем первые 30 символов названия
        title = session.title[:30]
        
        buttons.append([
            InlineKeyboardButton(
                text=f"{emoji}{title}",
                callback_data=f"chat_{session.session_id[:8]}"  # Первые 8 символов UUID
            )
        ])
    
    # Кнопка "Новый чат"
    buttons.append([
        InlineKeyboardButton(
            text="➕ Создать новый чат",
            callback_data="chat_new"
        )
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await message.answer(
        f"💬 Твои чаты ({len(sessions)}):\n\n"
        f"✅ - активный чат\n"
        f"💬 - другие чаты\n\n"
        f"Выбери чат для переключения:",
        reply_markup=keyboard
    )


# Обработка выбора модели
@dp.callback_query(F.data.startswith("model_"))
async def callback_model_select(callback: CallbackQuery):
    model_key = callback.data.split("_")[1]
    
    if model_key not in MODELS:
        await callback.answer("❌ Неизвестная модель", show_alert=True)
        return
    
    # Обновляем модель в БД
    await update_selected_model(callback.from_user.id, model_key)
    
    model_info = MODELS[model_key]
    await callback.answer(f"✅ Выбрана {model_info['name']}", show_alert=False)
    
    await callback.message.edit_text(
        f"✅ Модель изменена на: {model_info['name']}\n\n"
        f"{model_info['description']}\n\n"
        f"Теперь просто напиши свой вопрос!",
        reply_markup=None
    )

    # Обработка переключения чатов
@dp.callback_query(F.data.startswith("chat_"))
async def callback_chat_select(callback: CallbackQuery):
    action = callback.data.split("_")[1]
    
    # Создание нового чата
    if action == "new":
        session_id = await create_new_session(callback.from_user.id, "Новый чат")
        await callback.answer("✨ Новый чат создан!", show_alert=False)
        await callback.message.edit_text(
            "✨ Создан новый чат!\n\n"
            "Это твой активный чат. Можешь начинать диалог!"
        )
        return
    
    # Переключение на существующий чат
    # Получаем полный session_id из базы (action это первые 8 символов)
    sessions = await get_user_sessions(callback.from_user.id)
    selected_session = None
    
    for session in sessions:
        if session.session_id.startswith(action):
            selected_session = session
            break
    
    if not selected_session:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return
    
    # Переключаемся
    await switch_session(callback.from_user.id, selected_session.session_id)
    await callback.answer(f"✅ Переключено на {selected_session.title}", show_alert=False)
    
    await callback.message.edit_text(
        f"✅ Активный чат: {selected_session.title}\n\n"
        f"Теперь можешь продолжить диалог в этом чате."
    )


# Обработка текстовых сообщений (вопросы к AI)
@dp.message(F.text)
async def handle_message(message: Message):
    # Проверяем лимит
    can_request, remaining = await check_and_update_limit(message.from_user.id)
    
    if not can_request:
        await message.answer(
            f"❌ Дневной лимит исчерпан!\n\n"
            f"Попробуй завтра или подожди до полуночи UTC 🌙"
        )
        return
    
    # Получаем выбранную модель
    user = await get_user_info(message.from_user.id)
    if not user:
        await message.answer("❌ Используй /start для начала работы")
        return
    
    model_key = user.selected_model
    model_name = get_model_name(model_key)
    
    # Сохраняем сообщение юзера в историю
    await save_message(
        telegram_id=message.from_user.id,
        role="user",
        content=message.text
    )
    
    # Получаем историю диалога (последние 5 пар сообщений)
    history = await get_conversation_history(message.from_user.id, limit=5)
    # ОТЛАДКА: Смотрим что в истории
    print(f"🔍 История для юзера {message.from_user.id}:")
    print(f"📝 Количество сообщений в истории: {len(history)}")
    for i, msg in enumerate(history):
        print(f"  {i+1}. {msg['role']}: {msg['content'][:50]}...")
    
    # Показываем что бот печатает
    await bot.send_chat_action(message.chat.id, "typing")
    
    # Отправляем запрос в OpenRouter с историей
    result = await send_message(model_key, history)
    
    if result["success"]:
        # Успешный ответ
        response_text = result["response"]
        tokens = result["tokens"]
        
        # Сохраняем ответ AI в историю
        await save_message(
            telegram_id=message.from_user.id,
            role="assistant",
            content=response_text,
            model_used=model_key
        )
        
        await message.answer(
            f"{response_text}\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🤖 {model_name}\n"
            f"💰 Токены: {tokens}\n"
            f"⏳ Осталось запросов: {remaining}\n"
            f"💬 История: {len(history)//2} сообщений"
        )
    else:
        # Ошибка
        error = result["error"]
        await message.answer(
            f"❌ Ошибка при запросе к AI:\n\n"
            f"{error}\n\n"
            f"Попробуй другую модель через /model"
        )


# Главная функция
async def main():
    print("🚀 Запуск бота...")
    
    # Инициализация БД
    await init_db()
    
    # Запуск бота
    print("✅ Бот запущен и готов к работе!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    print("🎬 Запуск main()...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 Бот остановлен")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()