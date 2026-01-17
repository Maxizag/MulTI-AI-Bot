"""
Модуль для подсчета стоимости запросов к AI моделям
"""

# Pricing в USD за 1 миллион токенов
# Данные актуальны на январь 2025
MODEL_PRICING = {
    "mimo": {
        "input": 0.0,
        "output": 0.0,
        "description": "Бесплатная модель"
    },
    "chimera": {
        "input": 0.0,
        "output": 0.0,
        "description": "Бесплатная модель"
    },
    "devstral": {
        "input": 0.0,
        "output": 0.0,
        "description": "Бесплатная модель"
    },
    "gemini": {
        "input": 0.075,    # $0.075 за 1M input токенов
        "output": 0.30,    # $0.30 за 1M output токенов
        "description": "Gemini 2.5 Flash"
    },
    "claude": {
        "input": 3.0,      # $3 за 1M input токенов
        "output": 15.0,    # $15 за 1M output токенов
        "description": "Claude Sonnet 4.5"
    },
    "gpt4": {
        "input": 2.5,      # $2.5 за 1M input токенов
        "output": 10.0,    # $10 за 1M output токенов
        "description": "GPT-4o"
    }
}


def calculate_cost(model_key: str, input_tokens: int, output_tokens: int) -> float:
    """
    Рассчитывает стоимость запроса в USD
    
    Args:
        model_key: Ключ модели (mimo, claude, gpt4, etc.)
        input_tokens: Количество входных токенов
        output_tokens: Количество выходных токенов
        
    Returns:
        float: Стоимость в USD
    """
    if model_key not in MODEL_PRICING:
        return 0.0
    
    pricing = MODEL_PRICING[model_key]
    
    # Стоимость = (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    
    total_cost = input_cost + output_cost
    
    return round(total_cost, 6)  # Округляем до 6 знаков


def estimate_tokens(text: str) -> int:
    """
    Приблизительная оценка количества токенов в тексте
    Правило: ~1 токен = 4 символа (для английского) или ~1 токен = 2 символа (для русского)
    
    Args:
        text: Текст для оценки
        
    Returns:
        int: Примерное количество токенов
    """
    # Простая эвристика: считаем среднее между английским и русским
    # 1 токен ≈ 3 символа
    return len(text) // 3


def is_free_model(model_key: str) -> bool:
    """
    Проверяет, является ли модель бесплатной
    
    Args:
        model_key: Ключ модели
        
    Returns:
        bool: True если модель бесплатная
    """
    if model_key not in MODEL_PRICING:
        return False
    
    pricing = MODEL_PRICING[model_key]
    return pricing["input"] == 0.0 and pricing["output"] == 0.0


def format_cost(cost: float) -> str:
    """
    Форматирует стоимость для отображения
    
    Args:
        cost: Стоимость в USD
        
    Returns:
        str: Отформатированная строка
    """
    if cost == 0.0:
        return "Бесплатно"
    elif cost < 0.001:
        return f"${cost:.6f}"
    elif cost < 0.01:
        return f"${cost:.4f}"
    else:
        return f"${cost:.3f}"


def get_model_info(model_key: str) -> dict:
    """
    Возвращает информацию о ценах на модель
    
    Args:
        model_key: Ключ модели
        
    Returns:
        dict: Словарь с информацией о ценах
    """
    if model_key not in MODEL_PRICING:
        return {
            "input": 0.0,
            "output": 0.0,
            "description": "Неизвестная модель",
            "is_free": True
        }
    
    pricing = MODEL_PRICING[model_key]
    return {
        "input": pricing["input"],
        "output": pricing["output"],
        "description": pricing["description"],
        "is_free": is_free_model(model_key)
    }