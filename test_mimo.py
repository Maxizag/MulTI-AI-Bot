import time
from openai import OpenAI
from config import OPENROUTER_API_KEY

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    timeout=30.0
)

print("🧪 Тестирую Xiaomi Mimo V2 Flash...\n")

test_messages = [
    "Привет, как дела?",
    "Расскажи короткий анекдот про роботов",
    "Объясни что такое квантовая физика за 20 слов"
]

for i, msg in enumerate(test_messages, 1):
    print(f"{'='*60}")
    print(f"📝 Тест {i}: {msg}")
    print(f"{'='*60}")
    
    try:
        start = time.time()
        response = client.chat.completions.create(
            model="mistralai/devstral-2512:free",
            messages=[{"role": "user", "content": msg}]
        )
        duration = time.time() - start
        
        answer = response.choices[0].message.content
        tokens = response.usage.total_tokens if response.usage else 0
        
        print(f"⏱️  Время: {duration:.1f} сек")
        print(f"💰 Токены: {tokens}")
        print(f"💬 Ответ:\n{answer}\n")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}\n")

print("✅ Тесты завершены!")