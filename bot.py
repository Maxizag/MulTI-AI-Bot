print("🔍 Начинаю загрузку bot.py...")

import asyncio
import logging
import re
import html
import time
import sys

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

print("✅ Стандартные библиотеки загружены")

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.fsm.context import FSMContext

print("✅ aiogram и типы загружены")

# Импорты конфигурации
try:
    from config import TELEGRAM_BOT_TOKEN, MODELS, DAILY_LIMIT
    print("✅ config загружен")
except ImportError:
    logger.error("❌ Ошибка: Не найден файл config.py!")
    sys.exit(1)

# Импорты ценообразования
try:
    from pricing import calculate_cost, estimate_tokens, format_cost, is_free_model
    print("✅ pricing загружен")
except ImportError:
    logger.error("❌ Ошибка: Не найден файл pricing.py!")
    sys.exit(1)

# Импорты базы данных - ВОЗВРАЩАЕМ ПОЛНЫЙ СПИСОК
try:
    from database import (
        init_db, get_or_create_user, check_and_update_limit, 
        update_selected_model, get_user_info,
        save_message, get_conversation_history, clear_conversation_history,
        create_new_session, get_user_sessions, switch_session, get_current_session,
        rename_session, delete_session, auto_title_session,
        save_previous_session, set_system_prompt, clear_system_prompt, 
        get_system_prompt,
        async_session, ChatSession, Message as DBMessage,
        check_token_limit, update_token_usage, get_user_stats, check_model_access
    )
    print("✅ database загружен")
except ImportError:
    logger.error("❌ Ошибка: Не найден файл database.py!")
    sys.exit(1)

# Импорты OpenRouter
try:
    from openrouter import send_message, get_model_name
    print("✅ openrouter загружен")
except ImportError:
    logger.error("❌ Ошибка: Не найден файл openrouter.py!")
    sys.exit(1)

print("🚀 Все модули загружены успешно!")

# Инициализация бота
if not TELEGRAM_BOT_TOKEN:
    logger.error("❌ Ошибка: TELEGRAM_BOT_TOKEN не установлен!")
    sys.exit(1)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def markdown_to_html(text: str) -> str:
    """
    Превращает Markdown-код в красивые HTML-блоки для Telegram.
    Именно эта функция делает 'синюю плашку' с копированием.
    """
    if not text:
        return ""

    # 1. Сначала экранируем весь текст (защита от взлома HTML)
    # Это превращает < в &lt;, > в &gt; и т.д.
    text = html.escape(text)

    # Словарь для сохранения блоков кода
    code_blocks = {}
    
    def save_code_block(match):
        # Генерируем уникальный ключ-заглушку
        key = f"__CODE_BLOCK_{len(code_blocks)}__"
        
        # match.group(1) - это язык (например, python), match.group(2) - сам код
        lang = match.group(1).strip() if match.group(1) else ""
        code = match.group(2)
        
        # Если язык не указан, ставим 'text' (будет просто кнопка копировать)
        if not lang:
            lang = "text"
            
        # ВАЖНО: Формируем тег <pre><code class="language-...">
        # Именно class="language-..." заставляет Телеграм показать заголовок и подсветку
        code_blocks[key] = f'<pre><code class="language-{lang}">{code}</code></pre>'
        return key

    # 2. Ищем блоки кода ```язык ... ```
    # Регулярка ищет тройные кавычки, опциональное имя языка и содержимое
    # re.DOTALL нужен, чтобы точка захватывала и переносы строк
    text = re.sub(r'```(\w*)\n?(.*?)```', save_code_block, text, flags=re.DOTALL)

    # 3. Обрабатываем остальное форматирование (жирный, курсив)
    
    # Жирный (**текст**)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    
    # Курсив (*текст*)
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
    
    # Инлайн код (`код`) - это для маленьких кусочков внутри строки
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    
    # Заголовки (### Текст)
    text = re.sub(r'^(#{1,6})\s+(.+)$', r'<b>\2</b>', text, flags=re.MULTILINE)
    
    # Списки ( - Текст)
    text = re.sub(r'^\s*-\s+(.+)$', r'• \1', text, flags=re.MULTILINE)

    # 4. Возвращаем блоки кода на место
    for key, value in code_blocks.items():
        text = text.replace(key, value)
    
    return text


def get_models_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру выбора модели из конфига"""
    buttons = []
    for key, model in MODELS.items():
        # Добавляем эмодзи в зависимости от типа (бесплатная/платная)
        emoji = "🆓" if model.get("free") else "💎"
        btn_text = f"{emoji} {model['name']}"
        
        buttons.append([
            InlineKeyboardButton(
                text=btn_text,
                callback_data=f"model_{key}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- ХЕНДЛЕРЫ КОМАНД ---

@dp.message(Command("start"))
async def cmd_start(message: Message):
    try:
        await get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username
        )
        
        welcome_text = (
            f"👋 Привет, {message.from_user.first_name}!\n\n"
            f"Я твой AI-ассистент с доступом к GPT-4o, Claude 3.5, Gemini и другим моделям.\n\n"
        )
        
        for key, model in MODELS.items():
            free_label = " (Бесплатно)" if model.get("free") else ""
            welcome_text += f"🔹 <b>{model['name']}</b>{free_label} - {model['description']}\n"
        
        welcome_text += (
            f"\n🎯 <b>Как пользоваться:</b>\n"
            f"1. Выбери модель кнопкой ниже\n"
            f"2. Просто напиши свой вопрос\n"
            f"3. Я помню контекст диалога!\n\n"
            f"<b>Команды:</b>\n"
            f"/new - Начать новую тему (сброс памяти)\n"
            f"/model - Сменить нейросеть\n"
            f"/chats - Мои сохраненные чаты\n"
            f"/stats - Статистика и лимиты\n"
            f"/system - Задать роль (системный промпт)"
        )
        
        await message.answer(
            markdown_to_html(welcome_text),
            reply_markup=get_models_keyboard(),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка в /start: {e}")
        await message.answer("⚠️ Произошла ошибка при запуске. Попробуйте позже.")


@dp.message(Command("model"))
async def cmd_model(message: Message):
    user = await get_user_info(message.from_user.id)
    current_model = get_model_name(user.selected_model) if user else "Не выбрана"
    
    await message.answer(
        f"🤖 Текущая модель: <b>{current_model}</b>\n\nВыбери новую модель из списка:",
        reply_markup=get_models_keyboard(),
        parse_mode="HTML"
    )


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    stats = await get_user_stats(message.from_user.id)
    
    if not stats:
        await message.answer("❌ Сначала нажмите /start")
        return
    
    current_model = get_model_name(stats["selected_model"])
    
    # Форматируем прогресс-бар
    used = stats.get("tokens_used", 0)
    limit = stats.get("tokens_limit", 1)
    remaining = stats.get("tokens_remaining", 0)
    
    # Защита от деления на ноль
    if limit <= 0: limit = 1
        
    percentage = (used / limit * 100)
    percentage = min(percentage, 100) # Не больше 100%
    
    bar_length = 10
    filled = int(bar_length * percentage / 100)
    bar = "█" * filled + "░" * (bar_length - filled)
    
    if stats.get("is_admin"):
        stats_text = (
            f"📊 <b>Твоя статистика</b>\n\n"
            f"👑 Статус: <b>АДМИН</b> (Безлимит)\n"
            f"🤖 Модель: {current_model}\n\n"
            f"📝 Токенов всего: {used:,}\n"
            f"💰 Расход API: {format_cost(stats['total_spent'])}\n"
            f"📅 Регистрация: {stats['created_at'].strftime('%d.%m.%Y')}"
        )
    else:
        tier_name = stats.get('tier_name', 'Free')
        stats_text = (
            f"📊 <b>Твоя статистика</b>\n\n"
            f"🎯 Тариф: <b>{tier_name}</b>\n"
            f"🤖 Модель: {current_model}\n\n"
            f"📝 Лимит токенов (месяц):\n"
            f"<code>[{bar}] {percentage:.1f}%</code>\n"
            f"   Исп.: {used:,} / {limit:,}\n"
            f"   Ост.: <b>{remaining:,}</b>\n\n"
            f"💰 Потрачено (вирт.): {format_cost(stats['total_spent'])}\n"
        )
    
    await message.answer(stats_text, parse_mode="HTML")


@dp.message(Command("clear"))
async def cmd_clear(message: Message):
    await clear_conversation_history(message.from_user.id)
    await message.answer(
        "🗑 <b>Контекст текущего чата очищен!</b>\n\n"
        "Я забыл, о чем мы говорили последние 5 минут. Начинаем с чистого листа.",
        parse_mode="HTML"
    )


@dp.message(Command("new"))
async def cmd_new_chat(message: Message):
    # Создаем новую сессию
    await create_new_session(message.from_user.id, "Новый чат")
    
    await message.answer(
        f"✨ <b>Создан новый диалог!</b>\n\n"
        f"Старый диалог сохранен в архиве.\n"
        f"Используй /chats чтобы увидеть историю.",
        parse_mode="HTML"
    )


@dp.message(Command("chats"))
async def cmd_list_chats(message: Message):
    sessions = await get_user_sessions(message.from_user.id)
    current_session = await get_current_session(message.from_user.id)
    
    if not sessions:
        await message.answer("📭 У тебя пока нет сохраненных чатов.")
        return
    
    buttons = []
    # Показываем последние 8 чатов + кнопку создания
    # Сортировка должна быть уже из БД, но на всякий случай
    sessions_to_show = sessions[:8] 
    
    for session in sessions_to_show:
        is_current = current_session and session.session_id == current_session.session_id
        status_icon = "🟢" if is_current else "💭"
        
        # Обрезаем длинные названия
        title = session.title
        if len(title) > 20:
            title = title[:17] + "..."
            
        # Кнопка выбора чата
        btn_text = f"{status_icon} {title}"
        
        buttons.append([
            InlineKeyboardButton(
                text=btn_text,
                callback_data=f"chat_{session.session_id[:8]}" # Берем первые 8 символов UUID для краткости callback
            ),
            # Кнопка удаления (крестик)
            InlineKeyboardButton(
                text="❌",
                callback_data=f"chat_delete_{session.session_id[:8]}"
            )
        ])
    
    buttons.append([
        InlineKeyboardButton(
            text="➕ Новый чат",
            callback_data="chat_new"
        )
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await message.answer(
        f"🗂 <b>Твои диалоги</b> (Всего: {len(sessions)}):\n"
        f"Нажми, чтобы переключиться или удалить.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@dp.message(Command("rename"))
async def cmd_rename_chat(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("📝 Использование: `/rename Новое Название Чата`", parse_mode="Markdown")
        return
    
    new_title = args[1].strip()
    if len(new_title) > 50:
        await message.answer("❌ Слишком длинное название (макс 50 символов).")
        return

    if await rename_session(message.from_user.id, new_title):
        await message.answer(f"✅ Чат переименован в: <b>{new_title}</b>", parse_mode="HTML")
    else:
        await message.answer("❌ Не удалось переименовать чат.")


@dp.message(Command("system"))
async def cmd_system_prompt(message: Message):
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "⚙️ <b>Системная роль</b>\n\n"
            "Ты можешь задать боту роль. Она будет действовать <b>для текущего чата</b>.\n\n"
            "Пример:\n<code>/system Ты опытный Python-разработчик. Пиши только код.</code>\n\n"
            "Показать текущую: /system_show\n"
            "Сбросить: /system_clear",
            parse_mode="HTML"
        )
        return
    
    prompt = args[1].strip()
    if await set_system_prompt(message.from_user.id, prompt):
        await message.answer("✅ <b>Роль установлена!</b>\nТеперь я буду следовать этой инструкции.", parse_mode="HTML")
    else:
        await message.answer("❌ Ошибка при сохранении промпта.")


@dp.message(Command("system_show"))
async def cmd_system_show(message: Message):
    prompt = await get_system_prompt(message.from_user.id)
    if prompt:
        await message.answer(f"📋 <b>Текущая роль:</b>\n\n<code>{prompt}</code>", parse_mode="HTML")
    else:
        await message.answer("❌ Системный промпт не задан (я работаю как стандартный ассистент).")


@dp.message(Command("system_clear"))
async def cmd_system_clear(message: Message):
    if await clear_system_prompt(message.from_user.id):
        await message.answer("✅ Роль удалена. Я снова обычный ассистент.")
    else:
        await message.answer("❌ Ошибка при удалении.")


@dp.message(Command("ask"))
async def cmd_ask(message: Message):
    """Быстрый запрос к конкретной модели без переключения"""
    args = message.text.split(maxsplit=2)
    
    if len(args) < 3:
        await message.answer(
            "⚡️ <b>Быстрый запрос</b>\n\n"
            "Используй: `/ask [модель] [вопрос]`\n"
            "Пример: `/ask gpt4 Как варить борщ?`\n\n"
            "Алиасы: gpt4, claude, gemini, deepseek",
            parse_mode="Markdown"
        )
        return
        
    model_alias = args[1].lower()
    question = args[2]
    
    # Простой маппинг алиасов
    aliases = {
        "gpt": "gpt4", "gpt4": "gpt4",
        "claude": "claude", "sonnet": "claude",
        "gemini": "gemini", "google": "gemini",
        "deepseek": "deepseek", "r1": "deepseek"
    }
    
    model_key = aliases.get(model_alias)
    if not model_key or model_key not in MODELS:
        await message.answer(f"❌ Неизвестная модель: {model_alias}. Доступны: gpt4, claude, gemini, deepseek")
        return

    # Временная смена модели для этого запроса не меняет глобальную настройку
    # Но мы должны проверить доступ
    has_access, error_msg = await check_model_access(message.from_user.id, model_key)
    if not has_access:
        await message.answer(f"🚫 {error_msg}")
        return

    # Отправляем "Typing..."
    await bot.send_chat_action(message.chat.id, "typing")
    
    # Формируем разовый запрос
    messages = [{"role": "user", "content": question}]
    
    result = await send_message(model_key, messages)
    
    if result["success"]:
        # Считаем деньги и токены, но не сохраняем в историю чата (т.к. это разовый /ask)
        cost = calculate_cost(model_key, result.get("input_tokens", 0), result.get("output_tokens", 0))
        await update_token_usage(message.from_user.id, result["tokens"], cost)
        
        response = markdown_to_html(result["response"])
        model_name = get_model_name(model_key)
        
        await message.answer(
            f"{response}\n\n<i>⚡️ Ответ от {model_name} (One-shot)</i>",
            parse_mode="HTML"
        )
    else:
        await message.answer(f"❌ Ошибка: {result['error']}")


# --- CALLBACK ХЕНДЛЕРЫ ---

@dp.callback_query(F.data.startswith("model_"))
async def callback_model_select(callback: CallbackQuery):
    model_key = callback.data.split("_")[1]
    
    if model_key not in MODELS:
        await callback.answer("❌ Модель не найдена", show_alert=True)
        return
    
    await update_selected_model(callback.from_user.id, model_key)
    model_info = MODELS[model_key]
    
    await callback.message.edit_text(
        f"✅ <b>Модель изменена!</b>\n\n"
        f"Выбрана: <b>{model_info['name']}</b>\n"
        f"<i>{model_info['description']}</i>\n\n"
        f"👇 Теперь пиши вопрос:",
        reply_markup=None,
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("chat_"))
async def callback_chat_select(callback: CallbackQuery):
    parts = callback.data.split("_")
    action = parts[1] # new, delete или ID (если без действия)
    
    # 1. Создание нового
    if action == "new":
        await create_new_session(callback.from_user.id, "Новый чат")
        await callback.answer("✨ Чат создан!")
        await callback.message.edit_text("✨ Новый чат создан и активирован! Пиши сообщение.")
        return
    
    # 2. Удаление
    if action == "delete":
        # chat_delete_ID...
        if len(parts) < 3: return
        session_id_prefix = parts[2]
        
        sessions = await get_user_sessions(callback.from_user.id)
        target = next((s for s in sessions if s.session_id.startswith(session_id_prefix)), None)
        
        if target:
            success, msg = await delete_session(callback.from_user.id, target.session_id)
            if success:
                await callback.answer("🗑 Чат удален")
                await callback.message.edit_text(f"🗑 Чат <b>{target.title}</b> был удален.", parse_mode="HTML")
            else:
                await callback.answer("❌ Ошибка удаления", show_alert=True)
        return

    # 3. Переключение (если это просто chat_ID...)
    session_id_prefix = action
    sessions = await get_user_sessions(callback.from_user.id)
    target = next((s for s in sessions if s.session_id.startswith(session_id_prefix)), None)
    
    if target:
        await save_previous_session(callback.from_user.id, target.session_id)
        await switch_session(callback.from_user.id, target.session_id)
        await callback.answer(f"✅ Загружен: {target.title}")
        await callback.message.edit_text(
            f"📂 <b>Чат открыт:</b> {target.title}\n\n"
            f"Контекст восстановлен. Можешь продолжать общение.", 
            parse_mode="HTML"
        )
    else:
        await callback.answer("❌ Чат не найден (возможно, удален)", show_alert=True)


# --- ОСНОВНОЙ ОБРАБОТЧИК СООБЩЕНИЙ ---

@dp.message(F.text)
async def handle_message(message: Message):
    # 1. Получаем инфо о юзере
    user = await get_user_info(message.from_user.id)
    if not user:
        # Если юзер пишет, но его нет в базе (перезагрузка бота стерла кэш, но база на месте)
        user = await get_or_create_user(message.from_user.id, message.from_user.username)
    
    model_key = user.selected_model
    model_name = get_model_name(model_key)
    
    # 2. Проверка доступа (Tier)
    has_access, error_msg = await check_model_access(message.from_user.id, model_key)
    if not has_access:
        await message.answer(f"🚫 <b>Доступ запрещен</b>\n\n{error_msg}", parse_mode="HTML")
        return
    
    # 3. Проверка лимитов токенов
    estimated = estimate_tokens(message.text)
    can_request, remaining, tier = await check_token_limit(message.from_user.id, estimated)
    
    if not can_request:
        await message.answer(
            f"⏳ <b>Лимит исчерпан</b>\n\n"
            f"Вы достигли лимита токенов для тарифа <b>{tier}</b>.\n"
            f"Попробуйте бесплатные модели или ждите следующего месяца.",
            parse_mode="HTML"
        )
        return
    
    # 4. Сохраняем сообщение User
    await save_message(message.from_user.id, "user", message.text)
    
    # 5. Авто-название чата (если это первое сообщение)
    await auto_title_session(message.from_user.id, message.text)
    
    # 6. Собираем историю (Контекст)
    # Берем последние 15 сообщений для хорошего контекста
    history = await get_conversation_history(message.from_user.id, limit=15)
    
    # Добавляем системный промпт (если есть)
    system_prompt = await get_system_prompt(message.from_user.id)
    if system_prompt:
        history.insert(0, {"role": "system", "content": system_prompt})
    
    # Визуальный эффект "печатает..."
    await bot.send_chat_action(message.chat.id, "typing")
    
    # 7. Запрос к API
    result = await send_message(model_key, history)
    
    if result["success"]:
        response_text = result["response"]
        tokens_usage = result["tokens"]
        input_tokens = result.get("input_tokens", 0)
        output_tokens = result.get("output_tokens", 0)
        
        # Обновляем статистику
        cost = calculate_cost(model_key, input_tokens, output_tokens)
        await update_token_usage(message.from_user.id, tokens_usage, cost)
        
        # Сохраняем ответ Assistant
        await save_message(
            message.from_user.id, 
            "assistant", 
            response_text, 
            model_used=model_key
        )
        
        # 8. Отправка ответа
        html_response = markdown_to_html(response_text)
        
        # Инфо-футер
        is_free = is_free_model(model_key)
        time_spent = result.get("response_time", 0)
        
        if is_free:
            footer = f"\n\n<i>🤖 {model_name} • ⏱ {time_spent:.1f}s</i>"
        else:
            footer = f"\n\n<i>🤖 {model_name} • 💰 {tokens_usage} tok • 💵 {format_cost(cost)}</i>"
        
        MAX_MSG_LEN = 4000 # Чуть меньше 4096 для безопасности
        
        # Если сообщение короткое
        if len(html_response) <= MAX_MSG_LEN:
            try:
                await message.answer(html_response + footer, parse_mode="HTML")
            except TelegramBadRequest:
                # Если HTML битый, шлем plain text
                await message.answer(response_text + footer, parse_mode=None)
        else:
            # Разбиение длинного сообщения
            # Разбиваем ИСХОДНЫЙ текст (Markdown/Text), а не HTML, чтобы не рвать теги
            parts = []
            source_text = response_text
            
            while len(source_text) > 0:
                if len(source_text) <= MAX_MSG_LEN:
                    parts.append(source_text)
                    break
                
                # Ищем перенос строки
                split_idx = source_text.rfind('\n', 0, MAX_MSG_LEN)
                if split_idx == -1: split_idx = MAX_MSG_LEN
                
                parts.append(source_text[:split_idx])
                source_text = source_text[split_idx:].lstrip()
            
            # Отправляем куски
            for i, part in enumerate(parts):
                part_html = markdown_to_html(part)
                
                # Футер только в последнем
                current_footer = footer if (i == len(parts) - 1) else ""
                
                try:
                    await message.answer(part_html + current_footer, parse_mode="HTML")
                    await asyncio.sleep(0.3) # Анти-спам задержка
                except TelegramBadRequest:
                    await message.answer(part + current_footer, parse_mode=None)
                except TelegramRetryAfter as e:
                    await asyncio.sleep(e.retry_after)
                    await message.answer(part + current_footer, parse_mode=None)
                    
    else:
        # Ошибка API
        error_msg = result.get("error", "Неизвестная ошибка")
        logger.error(f"API Error for {message.from_user.id}: {error_msg}")
        
        await message.answer(
            f"❌ <b>Ошибка нейросети</b>\n\n"
            f"<code>{error_msg}</code>\n\n"
            f"Попробуйте сменить модель (/model) или повторите позже.",
            parse_mode="HTML"
        )


# --- ЗАПУСК ---

async def main():
    print("🚀 Запуск инициализации БД...")
    await init_db()
    
    print("🤖 Бот запускается...")
    # Удаляем вебхук, чтобы не было конфликтов с предыдущими запусками
    await bot.delete_webhook(drop_pending_updates=True)
    
    print("✅ Polling запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Бот остановлен (Ctrl+C)")
    except Exception as e:
        logger.critical(f"🔥 Критическая ошибка: {e}", exc_info=True)