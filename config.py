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

MODELS = {
    "mimo": {
        "id": "xiaomi/mimo-v2-flash:free",
        "name": "🆓 Xiaomi Mimo",
        "description": "Быстрая бесплатная модель от Xiaomi",
        "free": True
    },
    "chimera": {
        "id": "tngtech/deepseek-r1t2-chimera:free",
        "name": "🆓 DeepSeek Chimera",
        "description": "Бесплатная reasoning модель",
        "free": True
    },
    "devstral": {
        "id": "mistralai/devstral-2512:free",
        "name": "🆓 Devstral",
        "description": "Бесплатная модель Mistral для кода",
        "free": True
    },
    "gemini": {
        "id": "google/gemini-2.5-flash",
        "name": "⚡ Gemini 2.5 Flash",
        "description": "Быстрая и дешевая ($0.003)",
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

# ===== ТАРИФНЫЕ ПЛАНЫ =====

SUBSCRIPTION_TIERS = {
    "free": {
        "name": "🆓 Free",
        "monthly_tokens": 100_000,      # ~30-50 запросов средней длины
        "allowed_models": ["mimo", "chimera", "devstral"],  # только бесплатные
        "price_rub": 0,
        "description": "Базовый тариф с доступом к бесплатным моделям"
    },
    "pro": {
        "name": "⭐ Pro", 
        "monthly_tokens": 2_000_000,   # ~600-1000 запросов
        "allowed_models": "all",        # все модели
        "price_rub": 299,
        "description": "Доступ ко всем моделям с большим лимитом"
    },
    "unlimited": {
        "name": "👑 Unlimited",
        "monthly_tokens": 50_000_000,  # практически безлимит
        "allowed_models": "all",
        "price_rub": 999,
        "description": "Максимальный тариф для профессионалов"
    }
}

# Админы автоматически получают unlimited
# (уже есть ADMIN_IDS выше)