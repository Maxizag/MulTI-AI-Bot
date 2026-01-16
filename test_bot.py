try:
    import bot
except Exception as e:
    print(f"❌ Ошибка: {e}")
    import traceback
    traceback.print_exc()