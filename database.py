from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, JSON
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from datetime import datetime, timedelta
import uuid
from config import DATABASE_URL
from sqlalchemy import JSON


Base = declarative_base()
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String, nullable=True)
    selected_model = Column(String, default="mimo")
    current_session_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Этап 1
    system_prompt = Column(String, nullable=True)
    previous_session_id = Column(String, nullable=True)
    
    # ===== ЭТАП 2: МОНЕТИЗАЦИЯ =====
    subscription_tier = Column(String, default="free")  # free, pro, unlimited
    tokens_used_month = Column(Integer, default=0)      # использовано токенов в текущем месяце
    tokens_limit_month = Column(Integer, default=100_000)  # лимит токенов в месяц
    last_token_reset = Column(DateTime, default=datetime.utcnow)  # дата последнего сброса
    total_spent_usd = Column(Float, default=0.0)        # всего потрачено USD (для аналитики)
    
    # Старые поля (пока оставляем для совместимости)
    requests_today = Column(Integer, default=0)
    last_request_date = Column(DateTime, default=datetime.utcnow)


class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, nullable=False)
    role = Column(String, nullable=False)
    content = Column(String, nullable=False)
    model_used = Column(String, nullable=True)
    session_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # ===== ЭТАП 2: МЕТРИКИ =====
    tokens_used = Column(Integer, default=0)         # всего токенов
    input_tokens = Column(Integer, default=0)        # входных токенов
    output_tokens = Column(Integer, default=0)       # выходных токенов
    cost_usd = Column(Float, default=0.0)            # стоимость запроса
    response_time = Column(Float, default=0.0)       # время ответа в секундах

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    session_id = Column(String, unique=True, nullable=False)
    title = Column(String, default="Новый чат")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    is_auto_titled = Column(Boolean, default=True)  # Автоматическое название



# Инициализация БД
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ База данных инициализирована")


# Получить или создать юзера
async def get_or_create_user(telegram_id: int, username: str = None):
    async with async_session() as session:
        from sqlalchemy import select
        
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            user = User(telegram_id=telegram_id, username=username)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            print(f"✅ Новый юзер создан: {telegram_id}")
        
        return user


# Проверить лимит и обновить счетчик
async def check_and_update_limit(telegram_id: int) -> tuple[bool, int]:
    """
    Возвращает (можно_ли_запрос, осталось_запросов)
    """
    from config import DAILY_LIMIT, ADMIN_IDS
    
    # Админы имеют безлимит
    if telegram_id in ADMIN_IDS:
        return True, 999
    
    async with async_session() as session:
        from sqlalchemy import select
        
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            return False, 0
        
        # Проверяем дату
        today = datetime.utcnow().date()
        last_date = user.last_request_date.date() if user.last_request_date else None
        
        # Если новый день - сбрасываем счетчик
        if last_date != today:
            user.requests_today = 0
            user.last_request_date = datetime.utcnow()
        
        # Проверяем лимит
        if user.requests_today >= DAILY_LIMIT:
            remaining = 0
            can_request = False
        else:
            user.requests_today += 1
            user.last_request_date = datetime.utcnow()
            remaining = DAILY_LIMIT - user.requests_today
            can_request = True
        
        await session.commit()
        return can_request, remaining


# Обновить выбранную модель
async def update_selected_model(telegram_id: int, model_key: str):
    async with async_session() as session:
        from sqlalchemy import select
        
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        
        if user:
            user.selected_model = model_key
            await session.commit()
            print(f"✅ Модель обновлена для {telegram_id}: {model_key}")


# Получить инфо о юзере
async def get_user_info(telegram_id: int):
    async with async_session() as session:
        from sqlalchemy import select
        
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()


# Сохранить сообщение в историю
async def save_message(telegram_id: int, role: str, content: str, model_used: str = None):
    async with async_session() as session:
        # Получаем текущую сессию пользователя
        user = await get_user_info(telegram_id)
        
        # Если у юзера нет активной сессии - создаем первую
        if not user.current_session_id:
            session_id = await create_new_session(telegram_id, "Чат 1")
        else:
            session_id = user.current_session_id
        
        message = Message(
            telegram_id=telegram_id,
            role=role,
            content=content,
            model_used=model_used,
            session_id=session_id  # Привязываем к чату!
        )
        session.add(message)
        await session.commit()

# Получить последние N сообщений юзера из ТЕКУЩЕГО чата
async def get_conversation_history(telegram_id: int, limit: int = 10):
    """
    Возвращает последние N пар сообщений (user + assistant) из текущего чата
    """
    async with async_session() as session:
        from sqlalchemy import select
        
        # Получаем текущую сессию
        user = await get_user_info(telegram_id)
        if not user or not user.current_session_id:
            return []
        
        result = await session.execute(
            select(Message)
            .where(
                Message.telegram_id == telegram_id,
                Message.session_id == user.current_session_id  # Только текущий чат!
            )
            .order_by(Message.created_at.desc())
            .limit(limit * 2)
        )
        messages = result.scalars().all()
        
        # Переворачиваем (от старых к новым) и форматируем
        history = []
        for msg in reversed(messages):
            history.append({
                "role": msg.role,
                "content": msg.content
            })
        
        return history


# Очистить историю текущего чата
async def clear_conversation_history(telegram_id: int):
    async with async_session() as session:
        from sqlalchemy import delete
        
        # Получаем текущую сессию
        user = await get_user_info(telegram_id)
        if not user or not user.current_session_id:
            return
        
        await session.execute(
            delete(Message).where(
                Message.telegram_id == telegram_id,
                Message.session_id == user.current_session_id  # Только текущий чат!
            )
        )
        await session.commit()
        print(f"✅ История чата {user.current_session_id} очищена для {telegram_id}")

# === ФУНКЦИИ ДЛЯ РАБОТЫ С ЧАТАМИ ===

# Создать новую сессию (чат)
async def create_new_session(telegram_id: int, title: str = "Новый чат"):
    async with async_session() as session:
        from sqlalchemy import select
        
        # Генерируем уникальный ID
        new_session_id = str(uuid.uuid4())
        
        # Создаем сессию
        chat_session = ChatSession(
            user_id=telegram_id,
            session_id=new_session_id,
            title=title
        )
        session.add(chat_session)
        
        # Делаем её активной для пользователя
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user:
            user.current_session_id = new_session_id
        
        await session.commit()
        print(f"✅ Создан новый чат для {telegram_id}: {new_session_id}")
        return new_session_id


# Получить список всех чатов пользователя
async def get_user_sessions(telegram_id: int):
    async with async_session() as session:
        from sqlalchemy import select
        
        result = await session.execute(
            select(ChatSession)
            .where(ChatSession.user_id == telegram_id)
            .order_by(ChatSession.updated_at.desc())
        )
        return result.scalars().all()


# Переключиться на другой чат
async def switch_session(telegram_id: int, session_id: str):
    async with async_session() as session_obj:
        from sqlalchemy import select
        
        result = await session_obj.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        
        if user:
            user.current_session_id = session_id
            await session_obj.commit()
            print(f"✅ Юзер {telegram_id} переключился на чат {session_id}")


# Получить текущий активный чат
async def get_current_session(telegram_id: int):
    user = await get_user_info(telegram_id)
    if user and user.current_session_id:
        async with async_session() as session:
            from sqlalchemy import select
            
            result = await session.execute(
                select(ChatSession).where(ChatSession.session_id == user.current_session_id)
            )
            return result.scalar_one_or_none()
    return None

# ===== НОВЫЕ ФУНКЦИИ ДЛЯ ЭТАПА 1 =====

# Переименовать чат
async def rename_session(telegram_id: int, new_title: str):
    """Переименовывает текущий активный чат"""
    async with async_session() as session:
        from sqlalchemy import select
        
        user = await get_user_info(telegram_id)
        if not user or not user.current_session_id:
            return False
        
        result = await session.execute(
            select(ChatSession).where(ChatSession.session_id == user.current_session_id)
        )
        chat_session = result.scalar_one_or_none()
        
        if chat_session:
            chat_session.title = new_title[:100]  # Ограничение 100 символов
            chat_session.is_auto_titled = False  # Теперь название ручное
            chat_session.updated_at = datetime.utcnow()
            await session.commit()
            print(f"✅ Чат переименован: {new_title}")
            return True
        
        return False


# Удалить чат
async def delete_session(telegram_id: int, session_id: str):
    """Удаляет чат и все его сообщения"""
    async with async_session() as session_obj:
        from sqlalchemy import select, delete
        
        # Проверяем что это не последний чат
        sessions = await get_user_sessions(telegram_id)
        if len(sessions) <= 1:
            return False, "Нельзя удалить последний чат"
        
        # Удаляем все сообщения чата
        await session_obj.execute(
            delete(Message).where(Message.session_id == session_id)
        )
        
        # Удаляем сам чат
        await session_obj.execute(
            delete(ChatSession).where(ChatSession.session_id == session_id)
        )
        
        # Если это был активный чат - переключаемся на другой
        user = await get_user_info(telegram_id)
        if user and user.current_session_id == session_id:
            # Берем первый доступный чат
            remaining_sessions = await get_user_sessions(telegram_id)
            if remaining_sessions:
                result = await session_obj.execute(
                    select(User).where(User.telegram_id == telegram_id)
                )
                user_obj = result.scalar_one_or_none()
                if user_obj:
                    user_obj.current_session_id = remaining_sessions[0].session_id
        
        await session_obj.commit()
        print(f"✅ Чат {session_id} удален")
        return True, "Чат удален"


# Автоназвание чата по первому сообщению
async def auto_title_session(telegram_id: int, first_message: str):
    """Автоматически называет чат по первому сообщению"""
    async with async_session() as session:
        from sqlalchemy import select
        
        user = await get_user_info(telegram_id)
        if not user or not user.current_session_id:
            return
        
        result = await session.execute(
            select(ChatSession).where(ChatSession.session_id == user.current_session_id)
        )
        chat_session = result.scalar_one_or_none()
        
        if chat_session and chat_session.is_auto_titled:
            # Берем первые 30 символов
            auto_title = first_message[:30]
            if len(first_message) > 30:
                auto_title += "..."
            
            chat_session.title = auto_title
            chat_session.updated_at = datetime.utcnow()
            await session.commit()
            print(f"✅ Чат автоматически назван: {auto_title}")


# Сохранить previous_session для /back
async def save_previous_session(telegram_id: int, session_id: str):
    """Сохраняет предыдущий чат для команды /back"""
    async with async_session() as session:
        from sqlalchemy import select
        
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        
        if user and user.current_session_id != session_id:
            user.previous_session_id = user.current_session_id
            await session.commit()


# Установить системный промпт
async def set_system_prompt(telegram_id: int, prompt: str):
    """Устанавливает системный промпт для пользователя"""
    async with async_session() as session:
        from sqlalchemy import select
        
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        
        if user:
            user.system_prompt = prompt[:1000]  # Ограничение 1000 символов
            await session.commit()
            print(f"✅ Системный промпт установлен для {telegram_id}")
            return True
        return False


# Очистить системный промпт
async def clear_system_prompt(telegram_id: int):
    """Очищает системный промпт"""
    async with async_session() as session:
        from sqlalchemy import select
        
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        
        if user:
            user.system_prompt = None
            await session.commit()
            print(f"✅ Системный промпт очищен для {telegram_id}")
            return True
        return False


# Получить системный промпт
async def get_system_prompt(telegram_id: int):
    """Возвращает системный промпт пользователя"""
    user = await get_user_info(telegram_id)
    return user.system_prompt if user else None

# ===== ФУНКЦИИ ДЛЯ РАБОТЫ С ТОКЕНАМИ (ЭТАП 2) =====

async def check_token_limit(telegram_id: int, estimated_tokens: int = 0) -> tuple[bool, int, str]:
    """
    Проверяет лимит токенов и возвращает (можно_ли_запрос, осталось_токенов, tier)
    
    Args:
        telegram_id: ID пользователя
        estimated_tokens: Примерная оценка токенов для запроса
        
    Returns:
        tuple: (can_request, remaining_tokens, subscription_tier)
    """
    from config import ADMIN_IDS, SUBSCRIPTION_TIERS
    
    # Админы имеют безлимит
    if telegram_id in ADMIN_IDS:
        return True, 999_999_999, "unlimited"
    
    async with async_session() as session:
        from sqlalchemy import select
        
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            return False, 0, "free"
        
        # Проверяем нужно ли сбросить счетчик (новый месяц)
        now = datetime.utcnow()
        last_reset = user.last_token_reset
        
        # Если прошел месяц - сбрасываем
        if last_reset.month != now.month or last_reset.year != now.year:
            user.tokens_used_month = 0
            user.last_token_reset = now
            await session.commit()
            print(f"✅ Токены сброшены для {telegram_id} (новый месяц)")
        
        # Проверяем лимит
        remaining = user.tokens_limit_month - user.tokens_used_month
        
        if remaining < estimated_tokens:
            return False, remaining, user.subscription_tier
        
        return True, remaining, user.subscription_tier


async def update_token_usage(telegram_id: int, tokens_used: int, cost_usd: float):
    """
    Обновляет использование токенов и стоимость
    
    Args:
        telegram_id: ID пользователя
        tokens_used: Количество использованных токенов
        cost_usd: Стоимость запроса в USD
    """
    async with async_session() as session:
        from sqlalchemy import select
        
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        
        if user:
            user.tokens_used_month += tokens_used
            user.total_spent_usd += cost_usd
            await session.commit()
            print(f"✅ Токены обновлены для {telegram_id}: +{tokens_used} (всего: {user.tokens_used_month})")


async def get_user_stats(telegram_id: int) -> dict:
    """
    Возвращает статистику пользователя для отображения
    
    Returns:
        dict: Словарь со статистикой
    """
    from config import ADMIN_IDS, SUBSCRIPTION_TIERS
    
    user = await get_user_info(telegram_id)
    
    if not user:
        return None
    
    is_admin = telegram_id in ADMIN_IDS
    tier = user.subscription_tier
    tier_info = SUBSCRIPTION_TIERS.get(tier, SUBSCRIPTION_TIERS["free"])
    
    return {
        "is_admin": is_admin,
        "tier": tier,
        "tier_name": tier_info["name"],
        "tokens_used": user.tokens_used_month,
        "tokens_limit": user.tokens_limit_month,
        "tokens_remaining": user.tokens_limit_month - user.tokens_used_month,
        "total_spent": user.total_spent_usd,
        "selected_model": user.selected_model,
        "created_at": user.created_at
    }


async def check_model_access(telegram_id: int, model_key: str) -> tuple[bool, str]:
    """
    Проверяет есть ли доступ к модели на текущем тарифе
    
    Returns:
        tuple: (has_access, error_message)
    """
    from config import ADMIN_IDS, SUBSCRIPTION_TIERS
    
    # Админы имеют доступ ко всем моделям
    if telegram_id in ADMIN_IDS:
        return True, ""
    
    user = await get_user_info(telegram_id)
    
    if not user:
        return False, "Пользователь не найден"
    
    tier = user.subscription_tier
    tier_info = SUBSCRIPTION_TIERS.get(tier, SUBSCRIPTION_TIERS["free"])
    
    allowed_models = tier_info["allowed_models"]
    
    # Если "all" - доступны все модели
    if allowed_models == "all":
        return True, ""
    
    # Если список - проверяем вхождение
    if isinstance(allowed_models, list):
        if model_key in allowed_models:
            return True, ""
        else:
            tier_name = tier_info["name"]
            return False, f"❌ Модель недоступна на тарифе {tier_name}\n\nДоступные модели: {', '.join(allowed_models)}"
    
    return False, "Неизвестная ошибка доступа"