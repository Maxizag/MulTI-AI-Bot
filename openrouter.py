from openai import OpenAI
from config import OPENROUTER_API_KEY, MODELS
import time
from pricing import calculate_cost, estimate_tokens, format_cost, is_free_model


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
        "input_tokens": int или None,  # НОВОЕ
        "output_tokens": int или None,  # НОВОЕ
        "response_time": float или None,  # НОВОЕ
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
                "input_tokens": None,
                "output_tokens": None,
                "response_time": None,
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
        
        # Засекаем время
        start_time = time.time()
        
        # Отправляем запрос с полной историей
        response = client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": "https://t.me/your_bot",
                "X-Title": "AI Multi Bot",
            },
            model=model_id,
            messages=messages,
            max_tokens=8192,
        )
        
        # Считаем время ответа
        response_time = time.time() - start_time
        
        # Извлекаем ответ с проверкой
        if not response.choices or not response.choices[0].message.content:
            return {
                "success": False,
                "response": None,
                "tokens": None,
                "input_tokens": None,
                "output_tokens": None,
                "response_time": response_time,
                "error": "Модель вернула пустой ответ (возможно таймаут)"
            }
        
        answer = response.choices[0].message.content
        
        # Извлекаем метрики токенов
        if response.usage:
            total_tokens = response.usage.total_tokens
            input_tokens = response.usage.prompt_tokens if hasattr(response.usage, 'prompt_tokens') else 0
            output_tokens = response.usage.completion_tokens if hasattr(response.usage, 'completion_tokens') else 0
            
            # Если input/output не разделены - делаем примерную оценку
            if input_tokens == 0 and output_tokens == 0:
                # Примерно 70% на input, 30% на output
                input_tokens = int(total_tokens * 0.7)
                output_tokens = int(total_tokens * 0.3)
        else:
            total_tokens = 0
            input_tokens = 0
            output_tokens = 0
        
        print(f"✅ Ответ получен за {response_time:.1f}с | Токены: {total_tokens} (in: {input_tokens}, out: {output_tokens})")
        
        return {
            "success": True,
            "response": answer,
            "tokens": total_tokens,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "response_time": response_time,
            "error": None
        }
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Ошибка OpenRouter: {error_msg}")
        
        return {
            "success": False,
            "response": None,
            "tokens": None,
            "input_tokens": None,
            "output_tokens": None,
            "response_time": None,
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