from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from datetime import datetime, timedelta
import uuid
from config import DATABASE_URL

Base = declarative_base()
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String, nullable=True)
    selected_model = Column(String, default="deepseek")
    current_session_id = Column(String, nullable=True)  # Текущий активный чат
    requests_today = Column(Integer, default=0)
    last_request_date = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, nullable=False)
    role = Column(String, nullable=False)
    content = Column(String, nullable=False)
    model_used = Column(String, nullable=True)
    session_id = Column(String, nullable=True)  # К какому чату относится
    created_at = Column(DateTime, default=datetime.utcnow)

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    session_id = Column(String, unique=True, nullable=False)  # UUID чата
    title = Column(String, default="Новый чат")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


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