from openai import OpenAI
from config import OPENROUTER_API_KEY, MODELS

# Инициализация клиента с timeout
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    timeout=60.0  # 60 секунд максимум
)


async def send_message(model_key: str, messages: list) -> dict:
    """
    Отправляет массив сообщений в выбранную модель
    
    messages: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]
    
    Возвращает:
    {
        "success": bool,
        "response": str или None,
        "tokens": int или None,
        "error": str или None
    }
    """
    try:
        # Получаем ID модели из конфига
        if model_key not in MODELS:
            return {
                "success": False,
                "response": None,
                "tokens": None,
                "error": "Неизвестная модель"
            }
        
        model_id = MODELS[model_key]["id"]

        # 🔍 ОТЛАДКА: Показываем что отправляем в API
        print(f"\n{'='*60}")
        print(f"📤 Отправляем в {model_id}:")
        print(f"📝 Количество сообщений: {len(messages)}")
        for i, msg in enumerate(messages):
            print(f"  {i+1}. [{msg['role']}]: {msg['content'][:80]}...")
        print(f"{'='*60}\n")
        
        # Отправляем запрос с полной историей
        response = client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": "https://t.me/your_bot",
                "X-Title": "AI Multi Bot",
            },
            model=model_id,
            messages=messages,  # Теперь передаем весь массив!
            max_tokens=8192,  # ← УВЕЛИЧИЛ С 2000 ДО 8192 для длинных ответов
        )
        
        # Извлекаем ответ с проверкой
        if not response.choices or not response.choices[0].message.content:
            return {
                "success": False,
                "response": None,
                "tokens": None,
                "error": "Модель вернула пустой ответ (возможно таймаут)"
            }
        
        answer = response.choices[0].message.content
        tokens_used = response.usage.total_tokens if response.usage else 0
        
        return {
            "success": True,
            "response": answer,
            "tokens": tokens_used,
            "error": None
        }
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Ошибка OpenRouter: {error_msg}")
        
        return {
            "success": False,
            "response": None,
            "tokens": None,
            "error": error_msg
        }


def get_model_name(model_key: str) -> str:
    """Получить красивое имя модели"""
    if model_key in MODELS:
        return MODELS[model_key]["name"]
    return "Неизвестная модель"


def get_model_description(model_key: str) -> str:
    """Получить описание модели"""
    if model_key in MODELS:
        return MODELS[model_key]["description"]
    return ""


def is_model_free(model_key: str) -> bool:
    """Проверить бесплатная ли модель"""
    if model_key in MODELS:
        return MODELS[model_key].get("free", False)
    return False