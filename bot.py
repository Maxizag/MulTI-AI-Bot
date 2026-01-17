print("🔍 Начинаю загрузку bot.py...")

import asyncio
import logging
import re
import html
import time
print("✅ asyncio и logging загружены")

from aiogram import Bot, Dispatcher, F
print("✅ aiogram загружен")

from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
print("✅ aiogram types загружены")

from config import TELEGRAM_BOT_TOKEN, MODELS, DAILY_LIMIT
print("✅ config загружен")

from pricing import calculate_cost, estimate_tokens, format_cost, is_free_model
print("✅ pricing загружен")

from database import (
    init_db, get_or_create_user, check_and_update_limit, 
    update_selected_model, get_user_info,
    save_message, get_conversation_history, clear_conversation_history,
    create_new_session, get_user_sessions, switch_session, get_current_session,
    # Этап 1
    rename_session, delete_session, auto_title_session,
    save_previous_session, set_system_prompt, clear_system_prompt, 
    get_system_prompt,
    async_session, ChatSession, Message as DBMessage,
    # Этап 2 - новые функции
    check_token_limit, update_token_usage, get_user_stats, check_model_access
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


def markdown_to_html(text: str) -> str:
    """Конвертирует Markdown в HTML для Telegram с экранированием"""
    
    # 1. Сначала экранируем все HTML спецсимволы
    text = html.escape(text)
    
    # 2. Обрабатываем блоки кода (```код```)
    text = re.sub(
        r'```(\w*)\n(.*?)```',
        r'<pre><code class="\1">\2</code></pre>',
        text,
        flags=re.DOTALL
    )
    
    # 3. Инлайн код (`код`)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    
    # 4. Жирный текст (**текст** или __текст__)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)
    
    # 5. Курсив (*текст* или _текст_)
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
    text = re.sub(r'_(.+?)_', r'<i>\1</i>', text)
    
    # 6. Заголовки (### Заголовок)
    text = re.sub(r'###\s*(.+)', r'<b>\1</b>', text)
    text = re.sub(r'##\s*(.+)', r'<b>\1</b>', text)
    text = re.sub(r'#\s*(.+)', r'<b>\1</b>', text)
    
    return text


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
        f"💬 Все модели видят историю диалога!\n\n"
        f"Команды:\n"
        f"/start - главное меню\n"
        f"/model - сменить модель\n"
        f"/stats - статистика\n\n"
        f"💬 Чаты:\n"
        f"/new - создать новый чат\n"
        f"/chats - список чатов\n"
        f"/rename [название] - переименовать\n"
        f"/back - предыдущий чат\n"
        f"/clear - очистить историю\n\n"
        f"🤖 Запросы:\n"
        f"/ask [модель] [вопрос] - разовый запрос\n\n"
        f"⚙️ Настройки:\n"
        f"/system [текст] - системный промпт\n"
        f"/system_show - показать промпт\n"
        f"/system_clear - удалить промпт\n\n"
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
    stats = await get_user_stats(message.from_user.id)
    
    if not stats:
        await message.answer("❌ Пользователь не найден. Используй /start")
        return
    
    current_model = get_model_name(stats["selected_model"])
    
    # Форматируем прогресс-бар токенов
    used = stats["tokens_used"]
    limit = stats["tokens_limit"]
    remaining = stats["tokens_remaining"]
    
    percentage = (used / limit * 100) if limit > 0 else 0
    bar_length = 10
    filled = int(bar_length * percentage / 100)
    bar = "█" * filled + "░" * (bar_length - filled)
    
    if stats["is_admin"]:
        stats_text = (
            f"📊 <b>Твоя статистика</b>\n\n"
            f"👑 Статус: <b>АДМИН</b> (безлимит)\n"
            f"🤖 Модель: {current_model}\n\n"
            f"📝 Токенов использовано: {used:,}\n"
            f"💰 Всего потрачено: {format_cost(stats['total_spent'])}\n"
            f"📅 Зарегистрирован: {stats['created_at'].strftime('%d.%m.%Y')}"
        )
    else:
        stats_text = (
            f"📊 <b>Твоя статистика</b>\n\n"
            f"🎯 Тариф: <b>{stats['tier_name']}</b>\n"
            f"🤖 Модель: {current_model}\n\n"
            f"📝 Токены в этом месяце:\n"
            f"   {bar} {percentage:.0f}%\n"
            f"   Использовано: {used:,} / {limit:,}\n"
            f"   Осталось: <b>{remaining:,}</b>\n\n"
            f"💰 Потрачено: {format_cost(stats['total_spent'])}\n"
            f"📅 С нами: {stats['created_at'].strftime('%d.%m.%Y')}"
        )
    
    await message.answer(stats_text, parse_mode="HTML")


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
    
    buttons = []
    for session in sessions:
        is_current = current_session and session.session_id == current_session.session_id
        emoji = "✅ " if is_current else "💬 "
        title = session.title[:30]
        
        buttons.append([
            InlineKeyboardButton(
                text=f"{emoji}{title}",
                callback_data=f"chat_{session.session_id[:8]}"
            ),
            InlineKeyboardButton(
                text="🗑",
                callback_data=f"chat_delete_{session.session_id[:8]}"
            )
        ])
    
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
        f"💬 - другие чаты\n"
        f"🗑 - удалить чат\n\n"
        f"Выбери чат для переключения:",
        reply_markup=keyboard
    )


# Команда /rename - переименовать чат
@dp.message(Command("rename"))
async def cmd_rename_chat(message: Message):
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "❌ Использование: /rename [новое название]\n\n"
            "Пример: /rename Работа с Python"
        )
        return
    
    new_title = args[1].strip()
    
    if len(new_title) < 1:
        await message.answer("❌ Название не может быть пустым")
        return
    
    success = await rename_session(message.from_user.id, new_title)
    
    if success:
        await message.answer(f"✅ Чат переименован в: {new_title}")
    else:
        await message.answer("❌ Не удалось переименовать чат")


# Команда /system - установить системный промпт
@dp.message(Command("system"))
async def cmd_system_prompt(message: Message):
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "❌ Использование: /system [текст промпта]\n\n"
            "Пример: /system Ты опытный Python разработчик. Отвечай кратко с примерами кода.\n\n"
            "Другие команды:\n"
            "/system_show - показать текущий промпт\n"
            "/system_clear - удалить промпт"
        )
        return
    
    prompt = args[1].strip()
    success = await set_system_prompt(message.from_user.id, prompt)
    
    if success:
        await message.answer(
            f"✅ Системный промпт установлен!\n\n"
            f"Теперь все модели будут использовать этот промпт:\n\n"
            f"<i>{prompt[:200]}{'...' if len(prompt) > 200 else ''}</i>",
            parse_mode="HTML"
        )
    else:
        await message.answer("❌ Не удалось установить промпт")


# Команда /system_show - показать промпт
@dp.message(Command("system_show"))
async def cmd_system_show(message: Message):
    prompt = await get_system_prompt(message.from_user.id)
    
    if prompt:
        await message.answer(
            f"📋 Твой системный промпт:\n\n"
            f"<i>{prompt}</i>",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "❌ У тебя нет системного промпта\n\n"
            "Установи его командой:\n"
            "/system [текст]"
        )


# Команда /system_clear - очистить промпт
@dp.message(Command("system_clear"))
async def cmd_system_clear(message: Message):
    success = await clear_system_prompt(message.from_user.id)
    
    if success:
        await message.answer("✅ Системный промпт удален")
    else:
        await message.answer("❌ Не удалось удалить промпт")


# Команда /back - вернуться к предыдущему чату
@dp.message(Command("back"))
async def cmd_back_chat(message: Message):
    user = await get_user_info(message.from_user.id)
    
    if not user or not user.previous_session_id:
        await message.answer("❌ Нет предыдущего чата для возврата")
        return
    
    async with async_session() as session:
        from sqlalchemy import select
        
        result = await session.execute(
            select(ChatSession).where(ChatSession.session_id == user.previous_session_id)
        )
        prev_chat = result.scalar_one_or_none()
    
    if not prev_chat:
        await message.answer("❌ Предыдущий чат не найден")
        return
    
    await save_previous_session(message.from_user.id, user.current_session_id)
    await switch_session(message.from_user.id, user.previous_session_id)
    
    await message.answer(f"⬅️ Вернулись к чату: {prev_chat.title}")


# Команда /ask - разовый запрос к модели
@dp.message(Command("ask"))
async def cmd_ask_model(message: Message):
    args = message.text.split(maxsplit=2)
    
    if len(args) < 3:
        await message.answer(
            "❌ Использование: /ask [модель] [вопрос]\n\n"
            "Доступные модели:\n"
            "• gpt4, gpt - GPT-4o\n"
            "• claude - Claude Sonnet 4.5\n"
            "• gemini - Gemini 2.5 Flash\n"
            "• mimo - Xiaomi Mimo (бесплатная)\n"
            "• chimera, deepseek - DeepSeek (бесплатная)\n"
            "• devstral - Devstral (бесплатная)\n\n"
            "Пример: /ask gpt4 напиши функцию для парсинга JSON"
        )
        return
    
    model_alias = args[1].lower()
    question = args[2]
    
    MODEL_ALIASES = {
        "gpt4": "gpt4",
        "gpt": "gpt4",
        "claude": "claude",
        "gemini": "gemini",
        "mimo": "mimo",
        "chimera": "chimera",
        "deepseek": "chimera",
        "devstral": "devstral"
    }
    
    if model_alias not in MODEL_ALIASES:
        await message.answer(
            f"❌ Неизвестная модель: {model_alias}\n\n"
            "Используй: gpt4, claude, gemini, mimo, chimera, devstral"
        )
        return
    
    model_key = MODEL_ALIASES[model_alias]
    
    # Проверка доступа к модели
    has_access, error_msg = await check_model_access(message.from_user.id, model_key)
    if not has_access:
        await message.answer(
            f"{error_msg}\n\n"
            f"Доступные модели на твоем тарифе можешь посмотреть в /model"
        )
        return
    
    # Проверка лимита токенов
    estimated_tokens = estimate_tokens(question)
    can_request, remaining, tier = await check_token_limit(
        message.from_user.id,
        estimated_tokens
    )
    
    if not can_request:
        from config import SUBSCRIPTION_TIERS
        tier_info = SUBSCRIPTION_TIERS.get(tier, SUBSCRIPTION_TIERS["free"])
        
        await message.answer(
            f"❌ <b>Месячный лимит токенов исчерпан!</b>\n\n"
            f"Твой тариф: {tier_info['name']}\n"
            f"Попробуй в начале следующего месяца",
            parse_mode="HTML"
        )
        return
    
    # Получаем системный промпт
    system_prompt = await get_system_prompt(message.from_user.id)
    
    messages = []
    if system_prompt:
        messages.append({
            "role": "system",
            "content": system_prompt
        })
    
    messages.append({
        "role": "user",
        "content": question
    })
    
    model_name = get_model_name(model_key)
    await bot.send_chat_action(message.chat.id, "typing")
    
    result = await send_message(model_key, messages)
    
    if result["success"]:
        response_text = result["response"]
        tokens = result["tokens"]
        input_tokens = result.get("input_tokens", 0)
        output_tokens = result.get("output_tokens", 0)
        response_time = result.get("response_time", 0)
        
        # Подсчет стоимости и обновление токенов
        cost = calculate_cost(model_key, input_tokens, output_tokens)
        await update_token_usage(message.from_user.id, tokens, cost)
        
        response_text = markdown_to_html(response_text)
        
        # Добавляем метрику
        is_free = is_free_model(model_key)
        if is_free:
            footer = f"\n\n<i>🤖 {model_name} • 💰 {tokens:,} токенов • ⏱ {response_time:.1f}с</i>"
        else:
            footer = f"\n\n<i>🤖 {model_name} • 💰 {tokens:,} токенов • 💵 {format_cost(cost)} • ⏱ {response_time:.1f}с</i>"
        
        try:
            await message.answer(response_text + footer, parse_mode="HTML")
        except Exception as e:
            print(f"⚠️ Ошибка HTML парсинга: {e}")
            await message.answer(result["response"] + f"\n\n🤖 {model_name} • 💰 {tokens:,} токенов")
    else:
        error = result["error"]
        await message.answer(
            f"❌ Ошибка при запросе к {model_name}:\n\n"
            f"{error}"
        )


# Обработка выбора модели
@dp.callback_query(F.data.startswith("model_"))
async def callback_model_select(callback: CallbackQuery):
    model_key = callback.data.split("_")[1]
    
    if model_key not in MODELS:
        await callback.answer("❌ Неизвестная модель", show_alert=True)
        return
    
    await update_selected_model(callback.from_user.id, model_key)
    
    model_info = MODELS[model_key]
    await callback.answer(f"✅ Выбрана {model_info['name']}", show_alert=False)
    
    await callback.message.edit_text(
        f"✅ Модель изменена на: {model_info['name']}\n\n"
        f"{model_info['description']}\n\n"
        f"Теперь просто напиши свой вопрос!",
        reply_markup=None
    )


# Обработка переключения и удаления чатов
@dp.callback_query(F.data.startswith("chat_"))
async def callback_chat_select(callback: CallbackQuery):
    parts = callback.data.split("_")
    action = parts[1]
    
    if action == "new":
        session_id = await create_new_session(callback.from_user.id, "Новый чат")
        await callback.answer("✨ Новый чат создан!", show_alert=False)
        await callback.message.edit_text(
            "✨ Создан новый чат!\n\n"
            "Это твой активный чат. Можешь начинать диалог!"
        )
        return
    
    if action == "delete":
        session_id_prefix = parts[2]
        
        sessions = await get_user_sessions(callback.from_user.id)
        selected_session = None
        
        for session in sessions:
            if session.session_id.startswith(session_id_prefix):
                selected_session = session
                break
        
        if not selected_session:
            await callback.answer("❌ Чат не найден", show_alert=True)
            return
        
        success, message_text = await delete_session(
            callback.from_user.id,
            selected_session.session_id
        )
        
        if success:
            await callback.answer("✅ Чат удален", show_alert=False)
            
            sessions = await get_user_sessions(callback.from_user.id)
            current_session = await get_current_session(callback.from_user.id)
            
            buttons = []
            for session in sessions:
                is_current = current_session and session.session_id == current_session.session_id
                emoji = "✅ " if is_current else "💬 "
                title = session.title[:30]
                
                buttons.append([
                    InlineKeyboardButton(
                        text=f"{emoji}{title}",
                        callback_data=f"chat_{session.session_id[:8]}"
                    ),
                    InlineKeyboardButton(
                        text="🗑",
                        callback_data=f"chat_delete_{session.session_id[:8]}"
                    )
                ])
            
            buttons.append([
                InlineKeyboardButton(
                    text="➕ Создать новый чат",
                    callback_data="chat_new"
                )
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            
            await callback.message.edit_text(
                f"💬 Твои чаты ({len(sessions)}):\n\n"
                f"✅ - активный чат\n"
                f"💬 - другие чаты\n\n"
                f"Выбери чат для переключения:",
                reply_markup=keyboard
            )
        else:
            await callback.answer(f"❌ {message_text}", show_alert=True)
        
        return
    
    # Переключение на существующий чат
    sessions = await get_user_sessions(callback.from_user.id)
    selected_session = None
    
    for session in sessions:
        if session.session_id.startswith(action):
            selected_session = session
            break
    
    if not selected_session:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return
    
    await save_previous_session(callback.from_user.id, selected_session.session_id)
    await switch_session(callback.from_user.id, selected_session.session_id)
    await callback.answer(f"✅ Переключено на {selected_session.title}", show_alert=False)
    
    await callback.message.edit_text(
        f"✅ Активный чат: {selected_session.title}\n\n"
        f"Теперь можешь продолжить диалог в этом чате."
    )


# Обработка текстовых сообщений
@dp.message(F.text)
async def handle_message(message: Message):
    user = await get_user_info(message.from_user.id)
    if not user:
        await message.answer("❌ Используй /start для начала работы")
        return
    
    model_key = user.selected_model
    model_name = get_model_name(model_key)
    
    # Проверка доступа к модели
    has_access, error_msg = await check_model_access(message.from_user.id, model_key)
    if not has_access:
        await message.answer(
            f"{error_msg}\n\n"
            f"Измени модель через /model или обнови тариф"
        )
        return
    
    # Проверка лимита токенов
    estimated_tokens = estimate_tokens(message.text)
    can_request, remaining, tier = await check_token_limit(
        message.from_user.id,
        estimated_tokens
    )
    
    if not can_request:
        from config import SUBSCRIPTION_TIERS
        tier_info = SUBSCRIPTION_TIERS.get(tier, SUBSCRIPTION_TIERS["free"])
        
        await message.answer(
            f"❌ <b>Месячный лимит токенов исчерпан!</b>\n\n"
            f"Твой тариф: {tier_info['name']}\n"
            f"Лимит: {tier_info['monthly_tokens']:,} токенов/месяц\n\n"
            f"💡 Что можно сделать:\n"
            f"• Подожди до начала следующего месяца\n"
            f"• Используй бесплатные модели (если доступны)\n"
            f"• Обнови тариф (скоро)",
            parse_mode="HTML"
        )
        return
    
    # Сохраняем сообщение юзера
    await save_message(
        telegram_id=message.from_user.id,
        role="user",
        content=message.text
    )
    
    # Автоназвание чата
    await auto_title_session(message.from_user.id, message.text)
    
    # Получаем историю
    history = await get_conversation_history(message.from_user.id, limit=5)
    
    # Добавляем системный промпт
    system_prompt = await get_system_prompt(message.from_user.id)
    if system_prompt:
        history.insert(0, {
            "role": "system",
            "content": system_prompt
        })
    
    await bot.send_chat_action(message.chat.id, "typing")
    
    # Отправляем запрос
    result = await send_message(model_key, history)
    
    if result["success"]:
        response_text = result["response"]
        tokens = result["tokens"]
        input_tokens = result.get("input_tokens", 0)
        output_tokens = result.get("output_tokens", 0)
        response_time = result.get("response_time", 0)
        
        # Подсчет стоимости
        cost = calculate_cost(model_key, input_tokens, output_tokens)
        await update_token_usage(message.from_user.id, tokens, cost)
        
        # Сохраняем ответ AI
        await save_message(
            telegram_id=message.from_user.id,
            role="assistant",
            content=response_text,
            model_used=model_key
        )
        
        # Обновляем метрики последнего сообщения
        async with async_session() as session:
            from sqlalchemy import select, desc
            result_msg = await session.execute(
                select(DBMessage)
                .where(
                    DBMessage.telegram_id == message.from_user.id,
                    DBMessage.role == "assistant"
                )
                .order_by(desc(DBMessage.created_at))
                .limit(1)
            )
            last_message = result_msg.scalar_one_or_none()
            
            if last_message:
                last_message.tokens_used = tokens
                last_message.input_tokens = input_tokens
                last_message.output_tokens = output_tokens
                last_message.cost_usd = cost
                last_message.response_time = response_time
                await session.commit()
        
        # Форматируем ответ
        response_text = markdown_to_html(response_text)
        
        is_free = is_free_model(model_key)
        if is_free:
            footer = f"\n\n<i>🤖 {model_name} • 💰 {tokens:,} токенов • ⏱ {response_time:.1f}с</i>"
        else:
            footer = f"\n\n<i>🤖 {model_name} • 💰 {tokens:,} токенов • 💵 {format_cost(cost)} • ⏱ {response_time:.1f}с</i>"
        
        MAX_MESSAGE_LENGTH = 4096
        
        if len(response_text) <= MAX_MESSAGE_LENGTH - len(footer):
            try:
                await message.answer(response_text + footer, parse_mode="HTML")
            except Exception as e:
                print(f"⚠️ Ошибка HTML парсинга: {e}")
                await message.answer(result["response"] + f"\n\n🤖 {model_name} • 💰 {tokens:,} токенов")
        else:
            # Разбиваем на части
            parts = []
            while len(response_text) > 0:
                if len(response_text) <= MAX_MESSAGE_LENGTH:
                    parts.append(response_text)
                    break
                
                split_pos = response_text.rfind('\n', 0, MAX_MESSAGE_LENGTH)
                if split_pos == -1:
                    split_pos = MAX_MESSAGE_LENGTH
                
                parts.append(response_text[:split_pos])
                response_text = response_text[split_pos:].lstrip()
            
    # Отправляем по частям
    for i, part in enumerate(parts, 1):
        try:
            if i == len(parts):
                await message.answer(f"📄 Часть {i}/{len(parts)}:\n\n{part}{footer}", parse_mode="HTML")
            else:
                await message.answer(f"📄 Часть {i}/{len(parts)}:\n\n{part}", parse_mode="HTML")
        except Exception as e:
            print(f"⚠️ Ошибка при отправке части {i}: {e}")
            # Пробуем отправить без HTML парсинга
            try:
                # Берем оригинальную часть из исходного ответа (не HTML)
                original_parts = []
                temp_text = result["response"]
                while len(temp_text) > 0:
                    if len(temp_text) <= MAX_MESSAGE_LENGTH:
                        original_parts.append(temp_text)
                        break
                    split_pos = temp_text.rfind('\n', 0, MAX_MESSAGE_LENGTH)
                    if split_pos == -1:
                        split_pos = MAX_MESSAGE_LENGTH
                    original_parts.append(temp_text[:split_pos])
                    temp_text = temp_text[split_pos:].lstrip()
                
                # Отправляем соответствующую часть
                if i <= len(original_parts):
                    await message.answer(f"📄 Часть {i}/{len(parts)}:\n\n{original_parts[i-1]}")
                else:
                    await message.answer(f"⚠️ Ошибка отправки части {i}")
            except Exception as e2:
                print(f"❌ Критическая ошибка части {i}: {e2}")
                await message.answer(f"❌ Не удалось отправить часть {i}/{len(parts)}")
    else:
        error = result["error"]
        await message.answer(
            f"❌ Ошибка при запросе к AI:\n\n"
            f"{error}\n\n"
            f"Попробуй другую модель через /model"
        )


# Главная функция
async def main():
    print("🚀 Запуск бота...")
    await init_db()
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