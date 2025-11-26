import os
import logging

logging.basicConfig(level=logging.DEBUG)

print("🚀 بدء اختبار البوت...")
print(f"BOT_TOKEN: {os.environ.get('BOT_TOKEN', 'NOT FOUND')}")

if os.environ.get('BOT_TOKEN'):
    print("✅ الاختبار ناجح!")
else:
    print("❌ الاختبار فاشل - BOT_TOKEN غير موجود")