import os
from dotenv import load_dotenv

import os
from dotenv import load_dotenv

load_dotenv()

# --- Читаем админов из .env ---
admin_ids_str = os.getenv("ADMIN_IDS", "")

# Превращаем строку "123,456" в список чисел [123, 456]
# Конструкция проверяет, чтобы id был числом, чтобы код не упал от ошибки
ADMIN_IDS = [
    int(x.strip()) 
    for x in admin_ids_str.split(",") 
    if x.strip().isdigit()
]

# Если список пуст, можно добавить заглушку или вывести предупреждение
if not ADMIN_IDS:
    print("⚠️ Внимание: Список админов пуст! Проверь .env")

# ... остальной код ...

# API ключи
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")

# API ключи
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "YOUR_OPENROUTER_KEY")

# База данных
DATABASE_URL = "sqlite+aiosqlite:///./ai_bot.db"

# Лимиты
DAILY_LIMIT = 5  # Запросов в день для бесплатных юзеров

# Модели
MODELS = {
    "deepseek": {
        "id": "deepseek/deepseek-r1-0528:free",
        "name": "🆓 DeepSeek R1",
        "description": "Бесплатная reasoning модель",
        "free": True
    },
    "gemini": {
        "id": "google/gemini-2.5-flash",
        "name": "⚡ Gemini 2.5 Flash",
        "description": "Быстрая и дешевая",
        "free": False
    },
    "claude": {
        "id": "anthropic/claude-sonnet-4.5",
        "name": "🧠 Claude Sonnet 4.5",
        "description": "Баланс качества и цены",
        "free": False
    },
    "gpt4": {
        "id": "openai/gpt-4o",
        "name": "🚀 GPT-4o",
        "description": "Топовая модель OpenAI",
        "free": False
    }
}
