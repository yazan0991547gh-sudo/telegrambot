import sqlite3
import logging
import asyncio
import signal
import sys
import re
import io
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# ⚙️ الإعدادات - عدل هذه فقط
BOT_TOKEN = "8184908585:AAEyVjm_-EZxhHGcTm9hchDDXXxIEybBNXI"
ADMIN_USERNAMES = ["Qh321a","A_y_g278","yazan_14op90"]  # ضع يوزر الأدمن هنا بدون @ (يمكن إضافة أكثر من أدمن)

# ⚡ إعدادات القناة الإلزامية - ضع يوزر القناة هنا (بدون @)
REQUIRED_CHANNEL = "elitesportexpectations"  # اتركه فارغاً الآن، يمكنك إضافته لاحقاً مثال: "predictions_channel"

# إعدادات الاشتراك والدفع - يمكن تعديلها بسهولة
SUBSCRIPTION_SETTINGS = {
    "monthly_price": 75000,  # 75,000 ليرة للاشتراك الشهري
    "prediction_price": 25000,  # 25,000 ليرة للتوقع الخاص
}

# إعدادات النظام التجريبي
TRIAL_SETTINGS = {
    "enabled": True,  # تفعيل/تعطيل النظام التجريبي
    "days": 3,        # عدد أيام التجربة
    "one_time": True  # لمرة واحدة فقط لكل مستخدم
}

# إعدادات بوابات الدفع - عدل الأرقام
PAYMENT_SETTINGS = {
    "syriatel": {
        "name": "📱 سيرتل كاش",
        "account_number": "+963123456710",  # ضع رقم حساب السيرتل كاش الحقيقي
    },
    "sham": {
        "name": "📲 شام كاش", 
        "account_number": "+963987654321",  # ضع رقم حساب الشام كاش الحقيقي
    },
    "mtn": {
        "name": "📞 ام تي ان كاش",
        "account_number": "+963555555555",  # ضع رقم حساب الام تي ان كاش الحقيقي
    }
}

# إعدادات اللوجر
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 🗄️ نظام قاعدة البيانات المحسن
def init_db():
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        
        # جدول المستخدمين
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                subscription_expiry DATE,
                is_banned BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # جدول الأدمن
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                username TEXT UNIQUE,
                first_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # جدول الاشتراكات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                transaction_number TEXT,
                amount REAL,
                payment_method TEXT,
                status TEXT DEFAULT 'pending',
                type TEXT DEFAULT 'subscription',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # جدول التوقعات المشتراة - تم التعديل لإضافة prediction_id
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS purchased_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                transaction_number TEXT,
                amount REAL,
                payment_method TEXT,
                status TEXT DEFAULT 'pending',
                prediction_request TEXT,
                prediction_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # جدول التوقعات اليومية - تم التعديل لتخزين file_id
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prediction_text TEXT,
                image_file_id TEXT,
                prediction_date DATE,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # جدول إعلانات التوقعات الخاصة - تم التعديل لتخزين file_id
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS special_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prediction_title TEXT,
                prediction_description TEXT,
                prediction_content TEXT,
                image_file_id TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # جدول الإعدادات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                setting_key TEXT UNIQUE,
                setting_value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # جدول الإعلانات المعلقة - جديد
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pending_announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                announcement_text TEXT,
                image_file_id TEXT,
                announcement_type TEXT,
                target_users TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sent_count INTEGER DEFAULT 0,
                total_count INTEGER DEFAULT 0
            )
        ''')
        
        # جدول الإعلانات المرسلة - جديد
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sent_announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                announcement_id INTEGER,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                FOREIGN KEY (announcement_id) REFERENCES pending_announcements (id),
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # جدول التجارب المجانية - جديد
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS free_trials (
                user_id INTEGER PRIMARY KEY,
                used_trial BOOLEAN DEFAULT FALSE,
                trial_start DATE,
                trial_end DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # التحقق من الأعمدة المفقودة وإضافتها
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'is_banned' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN is_banned BOOLEAN DEFAULT FALSE')
            logger.info("✅ تم إضافة عمود is_banned إلى جدول users")
        
        if 'subscription_expiry' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN subscription_expiry DATE')
            logger.info("✅ تم إضافة عمود subscription_expiry إلى جدول users")
        
        # التحقق من أعمدة special_predictions
        cursor.execute("PRAGMA table_info(special_predictions)")
        sp_columns = [column[1] for column in cursor.fetchall()]
        
        if 'prediction_title' not in sp_columns:
            cursor.execute('ALTER TABLE special_predictions ADD COLUMN prediction_title TEXT')
            logger.info("✅ تم إضافة عمود prediction_title إلى جدول special_predictions")
        
        if 'prediction_description' not in sp_columns:
            cursor.execute('ALTER TABLE special_predictions ADD COLUMN prediction_description TEXT')
            logger.info("✅ تم إضافة عمود prediction_description إلى جدول special_predictions")
        
        if 'prediction_content' not in sp_columns:
            cursor.execute('ALTER TABLE special_predictions ADD COLUMN prediction_content TEXT')
            logger.info("✅ تم إضافة عمود prediction_content إلى جدول special_predictions")
        
        if 'image_file_id' not in sp_columns:
            cursor.execute('ALTER TABLE special_predictions ADD COLUMN image_file_id TEXT')
            logger.info("✅ تم إضافة عمود image_file_id إلى جدول special_predictions")
        
        # التحقق من أعمدة purchased_predictions
        cursor.execute("PRAGMA table_info(purchased_predictions)")
        pp_columns = [column[1] for column in cursor.fetchall()]
        
        if 'prediction_id' not in pp_columns:
            cursor.execute('ALTER TABLE purchased_predictions ADD COLUMN prediction_id INTEGER')
            logger.info("✅ تم إضافة عمود prediction_id إلى جدول purchased_predictions")
        
        if 'prediction_request' not in pp_columns:
            cursor.execute('ALTER TABLE purchased_predictions ADD COLUMN prediction_request TEXT')
            logger.info("✅ تم إضافة عمود prediction_request إلى جدول purchased_predictions")
        
        # التحقق من أعمدة daily_predictions
        cursor.execute("PRAGMA table_info(daily_predictions)")
        dp_columns = [column[1] for column in cursor.fetchall()]
        
        if 'image_file_id' not in dp_columns:
            cursor.execute('ALTER TABLE daily_predictions ADD COLUMN image_file_id TEXT')
            logger.info("✅ تم إضافة عمود image_file_id إلى جدول daily_predictions")
        
        # إضافة الأدمن من الإعدادات إلى قاعدة البيانات
        for admin_username in ADMIN_USERNAMES:
            cursor.execute('SELECT * FROM admins WHERE username = ?', (admin_username,))
            existing_admin = cursor.fetchone()
            if not existing_admin:
                cursor.execute(
                    'INSERT OR IGNORE INTO admins (username, first_name) VALUES (?, ?)',
                    (admin_username, 'Admin')
                )
                logger.info(f"✅ تم إضافة الأدمن {admin_username} إلى قاعدة البيانات")
        
        # حفظ الإعدادات الحالية في قاعدة البيانات
        cursor.execute('INSERT OR REPLACE INTO bot_settings (setting_key, setting_value) VALUES (?, ?)', 
                      ('monthly_price', str(SUBSCRIPTION_SETTINGS['monthly_price'])))
        cursor.execute('INSERT OR REPLACE INTO bot_settings (setting_key, setting_value) VALUES (?, ?)', 
                      ('prediction_price', str(SUBSCRIPTION_SETTINGS['prediction_price'])))
        
        # حفظ إعدادات النظام التجريبي
        cursor.execute('INSERT OR REPLACE INTO bot_settings (setting_key, setting_value) VALUES (?, ?)', 
                      ('trial_enabled', str(TRIAL_SETTINGS['enabled']).lower()))
        cursor.execute('INSERT OR REPLACE INTO bot_settings (setting_key, setting_value) VALUES (?, ?)', 
                      ('trial_days', str(TRIAL_SETTINGS['days'])))
        cursor.execute('INSERT OR REPLACE INTO bot_settings (setting_key, setting_value) VALUES (?, ?)', 
                      ('trial_one_time', str(TRIAL_SETTINGS['one_time']).lower()))
        
        conn.commit()
        conn.close()
        logger.info("✅ قاعدة البيانات مهيأة بنجاح مع جميع التعديلات")
    except Exception as e:
        logger.error(f"❌ خطأ في تهيئة قاعدة البيانات: {e}")

def update_database_schema():
    """تحديث مخطط قاعدة البيانات لإضافة الأعمدة المفقودة"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        
        # التحقق وإضافة الأعمدة المفقودة
        cursor.execute("PRAGMA table_info(purchased_predictions)")
        existing_columns = [column[1] for column in cursor.fetchall()]
        
        columns_to_add = [
            ('prediction_id', 'INTEGER'),
            ('prediction_request', 'TEXT')
        ]
        
        for column_name, column_type in columns_to_add:
            if column_name not in existing_columns:
                cursor.execute(f'ALTER TABLE purchased_predictions ADD COLUMN {column_name} {column_type}')
                logger.info(f"✅ تم إضافة عمود {column_name} إلى جدول purchased_predictions")
        
        conn.commit()
        conn.close()
        logger.info("✅ تم تحديث مخطط قاعدة البيانات بنجاح")
    except Exception as e:
        logger.error(f"❌ خطأ في تحديث مخطط قاعدة البيانات: {e}")

def load_settings_from_db():
    """تحميل الإعدادات من قاعدة البيانات"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        
        cursor.execute('SELECT setting_key, setting_value FROM bot_settings')
        settings = cursor.fetchall()
        conn.close()
        
        for key, value in settings:
            if key == 'monthly_price':
                SUBSCRIPTION_SETTINGS['monthly_price'] = int(value)
            elif key == 'prediction_price':
                SUBSCRIPTION_SETTINGS['prediction_price'] = int(value)
        
        logger.info("✅ تم تحميل الإعدادات من قاعدة البيانات")
    except Exception as e:
        logger.error(f"❌ خطأ في تحميل الإعدادات: {e}")

def update_setting(key: str, value: str):
    """تحديث إعداد في قاعدة البيانات"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO bot_settings (setting_key, setting_value) VALUES (?, ?)', 
                      (key, value))
        conn.commit()
        conn.close()
        
        # تحديث الإعدادات في الذاكرة
        if key == 'monthly_price':
            SUBSCRIPTION_SETTINGS['monthly_price'] = int(value)
        elif key == 'prediction_price':
            SUBSCRIPTION_SETTINGS['prediction_price'] = int(value)
        
        logger.info(f"✅ تم تحديث الإعداد {key} إلى {value}")
    except Exception as e:
        logger.error(f"❌ خطأ في تحديث الإعداد: {e}")

def get_trial_settings():
    """الحصول على إعدادات النظام التجريبي من قاعدة البيانات"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        
        cursor.execute('SELECT setting_key, setting_value FROM bot_settings WHERE setting_key LIKE "trial_%"')
        settings = cursor.fetchall()
        conn.close()
        
        trial_settings = TRIAL_SETTINGS.copy()
        
        for key, value in settings:
            if key == 'trial_enabled':
                trial_settings['enabled'] = value.lower() == 'true'
            elif key == 'trial_days':
                trial_settings['days'] = int(value)
            elif key == 'trial_one_time':
                trial_settings['one_time'] = value.lower() == 'true'
        
        return trial_settings
    except Exception as e:
        logger.error(f"❌ خطأ في get_trial_settings: {e}")
        return TRIAL_SETTINGS

def update_trial_setting(key: str, value: str):
    """تحديث إعداد التجربة في قاعدة البيانات"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO bot_settings (setting_key, setting_value) VALUES (?, ?)', 
                      (f"trial_{key}", value))
        conn.commit()
        conn.close()
        
        logger.info(f"✅ تم تحديث إعداد التجربة {key} إلى {value}")
    except Exception as e:
        logger.error(f"❌ خطأ في update_trial_setting: {e}")

def has_used_trial(user_id: int):
    """التحقق إذا كان المستخدم استخدم التجربة مسبقاً"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        cursor.execute('SELECT used_trial FROM free_trials WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        return result is not None and result[0]
    except Exception as e:
        logger.error(f"❌ خطأ في has_used_trial: {e}")
        return False

def activate_trial(user_id: int):
    """تفعيل التجربة المجانية للمستخدم - معدلة"""
    try:
        trial_settings = get_trial_settings()
        days = trial_settings['days']
        
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        
        # إضافة أو تحديث سجل التجربة
        trial_end = datetime.now().date() + timedelta(days=days)
        cursor.execute('''
            INSERT OR REPLACE INTO free_trials 
            (user_id, used_trial, trial_start, trial_end) 
            VALUES (?, TRUE, ?, ?)
        ''', (user_id, datetime.now().date(), trial_end))
        
        conn.commit()
        conn.close()
        
        # تحديث اشتراك المستخدم - بشكل منفصل
        update_success = update_subscription(user_id, days)
        
        if update_success:
            logger.info(f"✅ تم تفعيل تجربة مجانية للمستخدم {user_id} لمدة {days} أيام")
            return True
        else:
            logger.error(f"❌ فشل في تحديث اشتراك المستخدم {user_id}")
            return False
            
    except Exception as e:
        logger.error(f"❌ خطأ في activate_trial: {e}")
        return False

def get_user(user_id: int):
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        conn.close()
        return user
    except Exception as e:
        logger.error(f"❌ خطأ في get_user: {e}")
        return None

def create_user(user_id: int, username: str, first_name: str):
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        cursor.execute('INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)', 
                      (user_id, username, first_name))
        conn.commit()
        conn.close()
        logger.info(f"✅ تم إنشاء مستخدم جديد: {user_id}")
    except Exception as e:
        logger.error(f"❌ خطأ في create_user: {e}")

def update_subscription(user_id: int, days: int):
    """تحديث أو إضافة اشتراك للمستخدم - معدلة لمنع database lock"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        
        # إذا كان للمستخدم اشتراك حالي، نضيف الأيام إليه
        cursor.execute('SELECT subscription_expiry FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if result and result[0]:
            # إذا كان هناك تاريخ انتهاء موجود، نضيف الأيام إليه
            try:
                current_expiry = datetime.strptime(result[0], '%Y-%m-%d').date()
                new_expiry = current_expiry + timedelta(days=days)
            except Exception as date_error:
                # في حالة خطأ في التاريخ، نبدأ من اليوم
                logger.error(f"⚠️ خطأ في تحويل التاريخ، البدء من اليوم: {date_error}")
                new_expiry = datetime.now().date() + timedelta(days=days)
        else:
            # إذا لم يكن هناك اشتراك، نبدأ من اليوم
            new_expiry = datetime.now().date() + timedelta(days=days)
        
        cursor.execute('UPDATE users SET subscription_expiry = ? WHERE user_id = ?', 
                      (new_expiry.strftime('%Y-%m-%d'), user_id))
        
        conn.commit()
        conn.close()
        logger.info(f"✅ تم تحديث اشتراك المستخدم {user_id} لمدة {days} يوم - ينتهي في {new_expiry}")
        return True
    except Exception as e:
        logger.error(f"❌ خطأ في update_subscription: {e}")
        return False

def ban_user(user_id: int):
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET is_banned = TRUE WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        logger.info(f"✅ تم حظر المستخدم {user_id}")
    except Exception as e:
        logger.error(f"❌ خطأ في ban_user: {e}")

def unban_user(user_id: int):
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET is_banned = FALSE WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        logger.info(f"✅ تم فك حظر المستخدم {user_id}")
    except Exception as e:
        logger.error(f"❌ خطأ في unban_user: {e}")

def get_all_users(limit: int = 50, offset: int = 0):
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id, username, first_name, subscription_expiry, is_banned, created_at 
            FROM users 
            ORDER BY created_at DESC 
            LIMIT ? OFFSET ?
        ''', (limit, offset))
        users = cursor.fetchall()
        conn.close()
        return users
    except Exception as e:
        logger.error(f"❌ خطأ في get_all_users: {e}")
        return []

def search_users_by_username(username: str):
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id, username, first_name, subscription_expiry, is_banned, created_at 
            FROM users 
            WHERE username LIKE ? OR first_name LIKE ?
            ORDER BY created_at DESC
        ''', (f'%{username}%', f'%{username}%'))
        users = cursor.fetchall()
        conn.close()
        return users
    except Exception as e:
        logger.error(f"❌ خطأ في search_users_by_username: {e}")
        return []

def add_subscription_transaction(user_id: int, transaction_number: str, amount: float, payment_method: str):
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO subscriptions (user_id, transaction_number, amount, payment_method) 
            VALUES (?, ?, ?, ?)
        ''', (user_id, transaction_number, amount, payment_method))
        transaction_id = cursor.lastrowid
        conn.commit()
        conn.close()
        logger.info(f"✅ تم إضافة معاملة اشتراك: {transaction_id}")
        return transaction_id
    except Exception as e:
        logger.error(f"❌ خطأ في add_subscription_transaction: {e}")
        return None

def add_prediction_transaction(user_id: int, transaction_number: str, amount: float, payment_method: str, prediction_id: int = None):
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        
        # ✅ الإصلاح: استخدام الاستعلام الصحيح مع جميع الأعمدة المطلوبة
        cursor.execute('''
            INSERT INTO purchased_predictions 
            (user_id, transaction_number, amount, payment_method, prediction_id, status) 
            VALUES (?, ?, ?, ?, ?, 'pending')
        ''', (user_id, transaction_number, amount, payment_method, prediction_id))
        
        transaction_id = cursor.lastrowid
        conn.commit()
        conn.close()
        logger.info(f"✅ تم إضافة معاملة توقع: {transaction_id} للتوقع الخاص: {prediction_id}")
        return transaction_id
    except Exception as e:
        logger.error(f"❌ خطأ في add_prediction_transaction: {e}")
        return None

def add_daily_prediction(prediction_text: str, image_file_id: str = None):
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        
        # تعطيل جميع التوقعات اليومية السابقة
        cursor.execute('UPDATE daily_predictions SET is_active = FALSE')
        
        # إضافة التوقع الجديد باستخدام file_id
        cursor.execute('''
            INSERT INTO daily_predictions (prediction_text, image_file_id, prediction_date, is_active) 
            VALUES (?, ?, ?, TRUE)
        ''', (prediction_text, image_file_id, datetime.now().date()))
        
        conn.commit()
        conn.close()
        logger.info("✅ تم إضافة توقعات يومية جديدة باستخدام file_id")
    except Exception as e:
        logger.error(f"❌ خطأ في add_daily_prediction: {e}")

def add_special_prediction(prediction_title: str, prediction_description: str, prediction_content: str, image_file_id: str = None):
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        
        # إضافة التوقع الجديد باستخدام file_id
        cursor.execute('''
            INSERT INTO special_predictions (prediction_title, prediction_description, prediction_content, image_file_id, is_active) 
            VALUES (?, ?, ?, ?, TRUE)
        ''', (prediction_title, prediction_description, prediction_content, image_file_id))
        
        conn.commit()
        conn.close()
        logger.info(f"✅ تم إضافة توقع خاص جديد: {prediction_title}")
    except Exception as e:
        logger.error(f"❌ خطأ في add_special_prediction: {e}")

def get_active_daily_prediction():
    """الحصول على التوقعات اليومية النشطة في آخر 24 ساعة"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        
        # الحصول على التوقعات النشطة في آخر 24 ساعة فقط
        yesterday = datetime.now() - timedelta(hours=24)
        cursor.execute('''
            SELECT id, prediction_text, image_file_id 
            FROM daily_predictions 
            WHERE created_at >= ? AND is_active = TRUE 
            ORDER BY created_at DESC LIMIT 1
        ''', (yesterday,))
        prediction = cursor.fetchone()
        conn.close()
        return prediction
    except Exception as e:
        logger.error(f"❌ خطأ في get_active_daily_prediction: {e}")
        return None

def get_active_special_predictions():
    """الحصول على جميع التوقعات الخاصة النشطة"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, prediction_title, prediction_description, prediction_content, image_file_id 
            FROM special_predictions 
            WHERE is_active = TRUE 
            ORDER BY created_at DESC
        ''')
        predictions = cursor.fetchall()
        conn.close()
        return predictions
    except Exception as e:
        logger.error(f"❌ خطأ في get_active_special_predictions: {e}")
        return []

def get_special_prediction_by_id(prediction_id: int):
    """الحصول على توقع خاص محدد بالرقم"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, prediction_title, prediction_description, prediction_content, image_file_id 
            FROM special_predictions 
            WHERE id = ? AND is_active = TRUE
        ''', (prediction_id,))
        prediction = cursor.fetchone()
        conn.close()
        return prediction
    except Exception as e:
        logger.error(f"❌ خطأ في get_special_prediction_by_id: {e}")
        return None

def get_recent_special_predictions():
    """الحصول على التوقعات الخاصة في آخر 24 ساعة"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        yesterday = datetime.now() - timedelta(hours=24)
        cursor.execute('''
            SELECT id, prediction_title, prediction_description, prediction_content, image_file_id 
            FROM special_predictions 
            WHERE created_at >= ? AND is_active = TRUE 
            ORDER BY created_at DESC
        ''', (yesterday,))
        predictions = cursor.fetchall()
        conn.close()
        return predictions
    except Exception as e:
        logger.error(f"❌ خطأ في get_recent_special_predictions: {e}")
        return []

def get_recent_daily_predictions():
    """الحصول على التوقعات اليومية في آخر 24 ساعة"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        yesterday = datetime.now() - timedelta(hours=24)
        cursor.execute('''
            SELECT id, prediction_text, image_file_id, created_at 
            FROM daily_predictions 
            WHERE created_at >= ? 
            ORDER BY created_at DESC
        ''', (yesterday,))
        predictions = cursor.fetchall()
        conn.close()
        return predictions
    except Exception as e:
        logger.error(f"❌ خطأ في get_recent_daily_predictions: {e}")
        return []

def delete_special_prediction(prediction_id: int):
    """تعطيل التوقع الخاص بدلاً من حذفه"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        cursor.execute('UPDATE special_predictions SET is_active = FALSE WHERE id = ?', (prediction_id,))
        conn.commit()
        conn.close()
        logger.info(f"✅ تم تعطيل التوقع الخاص: {prediction_id}")
        return True
    except Exception as e:
        logger.error(f"❌ خطأ في delete_special_prediction: {e}")
        return False

def delete_daily_prediction(prediction_id: int):
    """تعطيل التوقع اليومي بدلاً من حذفه"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        cursor.execute('UPDATE daily_predictions SET is_active = FALSE WHERE id = ?', (prediction_id,))
        conn.commit()
        conn.close()
        logger.info(f"✅ تم تعطيل التوقع اليومي: {prediction_id}")
        return True
    except Exception as e:
        logger.error(f"❌ خطأ في delete_daily_prediction: {e}")
        return False

def get_subscription_transaction(transaction_id: int):
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM subscriptions WHERE id = ?', (transaction_id,))
        transaction = cursor.fetchone()
        conn.close()
        return transaction
    except Exception as e:
        logger.error(f"❌ خطأ في get_subscription_transaction: {e}")
        return None

def get_prediction_transaction(transaction_id: int):
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, user_id, transaction_number, amount, payment_method, status, 
                   prediction_request, prediction_id, created_at 
            FROM purchased_predictions WHERE id = ?
        ''', (transaction_id,))
        transaction = cursor.fetchone()
        conn.close()
        return transaction
    except Exception as e:
        logger.error(f"❌ خطأ في get_prediction_transaction: {e}")
        return None

def update_subscription_status(transaction_id: int, status: str):
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        cursor.execute('UPDATE subscriptions SET status = ? WHERE id = ?', (status, transaction_id))
        conn.commit()
        conn.close()
        logger.info(f"✅ تم تحديث حالة الاشتراك {transaction_id} إلى {status}")
    except Exception as e:
        logger.error(f"❌ خطأ في update_subscription_status: {e}")

def update_prediction_status(transaction_id: int, status: str):
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        cursor.execute('UPDATE purchased_predictions SET status = ? WHERE id = ?', (status, transaction_id))
        conn.commit()
        conn.close()
        logger.info(f"✅ تم تحديث حالة التوقع {transaction_id} إلى {status}")
    except Exception as e:
        logger.error(f"❌ خطأ في update_prediction_status: {e}")

def get_pending_subscriptions():
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.*, u.username, u.first_name 
            FROM subscriptions s 
            JOIN users u ON s.user_id = u.user_id 
            WHERE s.status = 'pending'
        ''')
        transactions = cursor.fetchall()
        conn.close()
        return transactions
    except Exception as e:
        logger.error(f"❌ خطأ في get_pending_subscriptions: {e}")
        return []

def get_pending_predictions():
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT p.id, p.user_id, p.transaction_number, p.amount, p.payment_method, 
                   p.status, p.prediction_request, p.prediction_id, p.created_at,
                   u.username, u.first_name, sp.prediction_title
            FROM purchased_predictions p 
            JOIN users u ON p.user_id = u.user_id 
            LEFT JOIN special_predictions sp ON p.prediction_id = sp.id
            WHERE p.status = 'pending'
        ''')
        transactions = cursor.fetchall()
        conn.close()
        return transactions
    except Exception as e:
        logger.error(f"❌ خطأ في get_pending_predictions: {e}")
        return []

def get_bot_stats():
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE subscription_expiry >= ?', (datetime.now().date(),))
        active_subscribers = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_banned = TRUE')
        banned_users = cursor.fetchone()[0]
        
        cursor.execute('SELECT SUM(amount) FROM subscriptions WHERE status = "approved"')
        subscription_revenue = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT SUM(amount) FROM purchased_predictions WHERE status = "approved"')
        predictions_revenue = cursor.fetchone()[0] or 0
        
        conn.close()
        
        return {
            'total_users': total_users,
            'active_subscribers': active_subscribers,
            'banned_users': banned_users,
            'subscription_revenue': subscription_revenue,
            'predictions_revenue': predictions_revenue
        }
    except Exception as e:
        logger.error(f"❌ خطأ في get_bot_stats: {e}")
        return {
            'total_users': 0,
            'active_subscribers': 0,
            'banned_users': 0,
            'subscription_revenue': 0,
            'predictions_revenue': 0
        }

def reset_revenue():
    """إعادة تعيين جميع الإيرادات إلى الصفر"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        
        # تحديث حالة جميع المعاملات إلى "reset" بدلاً من حذفها
        cursor.execute('UPDATE subscriptions SET status = "reset" WHERE status = "approved"')
        cursor.execute('UPDATE purchased_predictions SET status = "reset" WHERE status = "approved"')
        
        conn.commit()
        conn.close()
        
        logger.info("🔄 تم إعادة تعيين جميع الإيرادات إلى الصفر")
        return True
    except Exception as e:
        logger.error(f"❌ خطأ في reset_revenue: {e}")
        return False

def get_user_subscription_status(user_id: int):
    """
    تحديد حالة اشتراك المستخدم (محدث لدعم التجارب):
    - 'new': مستخدم جديد بدون اشتراك
    - 'trial_eligible': مؤهل للتجربة المجانية
    - 'trial_active': في فترة تجريبية نشطة  
    - 'trial_used': استخدم التجربة مسبقاً
    - 'active': مشترك نشط
    - 'expired': اشتراك منتهي
    - 'banned': محظور
    """
    try:
        user = get_user(user_id)
        if not user:
            return 'new'
        
        # التحقق من الحظر أولاً
        if len(user) > 4 and user[4]:  # is_banned
            return 'banned'
        
        # التحقق من الاشتراك المدفوع أولاً - الإصلاح هنا
        if len(user) > 3 and user[3] is not None:  # subscription_expiry is not None
            try:
                expiry_date = datetime.strptime(user[3], '%Y-%m-%d').date()
                if expiry_date >= datetime.now().date():
                    # تحقق إذا كان هذا اشتراكاً تجريبياً
                    if has_used_trial(user_id):
                        return 'trial_active'
                    else:
                        return 'active'
                else:
                    # الاشتراك منتهي
                    pass
            except Exception as date_error:
                logger.error(f"❌ خطأ في تحويل التاريخ: {date_error}")
        
        # التحقق من التجارب المجانية
        trial_settings = get_trial_settings()
        if trial_settings['enabled']:
            if has_used_trial(user_id):
                return 'trial_used'
            else:
                return 'trial_eligible'
        
        return 'expired'
    except Exception as e:
        logger.error(f"❌ خطأ في get_user_subscription_status: {e}")
        return 'new'

def is_user_subscribed(user_id: int):
    """التحقق إذا كان المستخدم مشتركاً نشطاً (يشمل التجارب النشطة)"""
    status = get_user_subscription_status(user_id)
    return status in ['active', 'trial_active']

def is_admin(user_id: int, username: str = None):
    """التحقق إذا كان المستخدم أدمن"""
    try:
        # التحقق من اليوزرنيم المحدد في الإعدادات
        if username and any(admin_username.lower() == username.lower() for admin_username in ADMIN_USERNAMES if admin_username):
            return True
        
        # في حالة عدم وجود يوزرنيم، نتحقق من قاعدة البيانات
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM admins WHERE user_id = ?', (user_id,))
        admin = cursor.fetchone()
        conn.close()
        
        return admin is not None
    except Exception as e:
        logger.error(f"❌ خطأ في is_admin: {e}")
        return False

def add_admin(user_id: int, username: str, first_name: str):
    """إضافة أدمن"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO admins (user_id, username, first_name) VALUES (?, ?, ?)', 
                      (user_id, username, first_name))
        conn.commit()
        conn.close()
        logger.info(f"✅ تم إضافة/تحديث أدمن: {user_id} - {username}")
    except Exception as e:
        logger.error(f"❌ خطأ في add_admin: {e}")

def extract_prediction_number(text_value):
    """
    دالة محسنة لاستخراج رقم التوقع من النص
    """
    try:
        if not text_value or not isinstance(text_value, str):
            return None
        
        text_value = text_value.strip()
        
        # تحويل الأرقام العربية إلى إنجليزية
        arabic_to_english = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
        normalized_text = text_value.translate(arabic_to_english)
        
        # البحث عن الأرقام بعد النص مباشرة
        patterns = [
            r"حذف التوقع اليومي\s*(\d+)",
            r"حذف التوقع\s*(\d+)",
            r"حذف الإعلان\s*(\d+)",
            r"(\d+)"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, normalized_text)
            if match:
                return int(match.group(1))
        
        return None
        
    except (ValueError, Exception) as e:
        logger.error(f"❌ خطأ في extract_prediction_number: {e}")
        return None

# ✅ نظام الإعلانات الذكية باستخدام file_id
async def send_message_with_photo(context, user_id: int, text: str, image_file_id: str = None, message_type: str = "رسالة"):
    """إرسال رسالة مع صورة باستخدام file_id - الطريقة الصحيحة"""
    try:
        if image_file_id:
            await context.bot.send_photo(
                chat_id=user_id,
                photo=image_file_id,
                caption=f"**{message_type}**\n\n{text}",
                parse_mode='Markdown'
            )
        else:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"**{message_type}**\n\n{text}",
                parse_mode='Markdown'
            )
        return True
    except Exception as e:
        logger.error(f"❌ فشل في إرسال {message_type} إلى {user_id}: {e}")
        return False

async def send_message_to_all_users_with_fallback(context, message_text: str, image_file_id: str = None, message_type: str = "رسالة"):
    """إرسال رسالة لجميع المستخدمين باستخدام file_id - معدلة"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        
        # الحصول على جميع المستخدمين غير المحظورين
        cursor.execute('SELECT user_id, created_at FROM users WHERE is_banned = FALSE')
        all_users = cursor.fetchall()
        total_users = len(all_users)
        
        # حفظ الإعلان في قاعدة البيانات
        announcement_id = save_pending_announcement(message_text, image_file_id, message_type, 'all', total_users)
        
        sent_count = 0
        failed_count = 0
        
        logger.info(f"📤 محاولة إرسال {message_type} لـ {total_users} مستخدم")
        
        for user in all_users:
            user_id, user_created_at = user
            
            # إرسال الإعلان فوراً للمستخدمين الحاليين
            success = await send_message_with_photo(context, user_id, message_text, image_file_id, message_type)
            
            if success:
                sent_count += 1
                mark_announcement_sent(announcement_id, user_id)
            else:
                failed_count += 1
            
            await asyncio.sleep(0.05)
        
        update_announcement_stats(announcement_id, sent_count)
        
        logger.info(f"✅ تم إرسال {message_type} بنجاح لـ {sent_count} مستخدم، فشل لـ {failed_count}")
        return sent_count
        
    except Exception as e:
        logger.error(f"❌ خطأ في send_message_to_all_users_with_fallback: {e}")
        return 0

async def send_message_to_active_users(context, message_text: str, image_file_id: str = None, message_type: str = "رسالة"):
    """إرسال رسالة للمستخدمين النشطين فقط"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        
        cursor.execute('SELECT user_id FROM users WHERE subscription_expiry >= ? AND is_banned = FALSE', 
                      (datetime.now().date(),))
        users = cursor.fetchall()
        conn.close()
        
        sent_count = 0
        failed_count = 0
        
        logger.info(f"📤 محاولة إرسال {message_type} لـ {len(users)} مستخدم نشط")
        
        for user in users:
            success = await send_message_with_photo(context, user[0], message_text, image_file_id, message_type)
            
            if success:
                sent_count += 1
            else:
                failed_count += 1
            
            await asyncio.sleep(0.05)
        
        logger.info(f"✅ تم إرسال {message_type} بنجاح لـ {sent_count} مستخدم نشط، فشل لـ {failed_count}")
        return sent_count
    except Exception as e:
        logger.error(f"❌ خطأ في send_message_to_active_users: {e}")
        return 0

def save_pending_announcement(message_text: str, image_file_id: str, announcement_type: str, target_users: str, total_users: int):
    """حفظ الإعلان في قاعدة البيانات باستخدام file_id"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO pending_announcements 
            (announcement_text, image_file_id, announcement_type, target_users, total_count) 
            VALUES (?, ?, ?, ?, ?)
        ''', (message_text, image_file_id, announcement_type, target_users, total_users))
        
        announcement_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"💾 تم حفظ الإعلان {announcement_id} للمستخدمين غير المتصلين")
        return announcement_id
    except Exception as e:
        logger.error(f"❌ خطأ في save_pending_announcement: {e}")
        return None

def mark_announcement_sent(announcement_id: int, user_id: int):
    """تسجيل أن الإعلان تم إرساله للمستخدم"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO sent_announcements (user_id, announcement_id, status) 
            VALUES (?, ?, 'sent')
        ''', (user_id, announcement_id))
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"❌ خطأ في mark_announcement_sent: {e}")

def update_announcement_stats(announcement_id: int, sent_count: int):
    """تحديث إحصائيات الإعلان"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE pending_announcements 
            SET sent_count = ? 
            WHERE id = ?
        ''', (sent_count, announcement_id))
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"❌ خطأ في update_announcement_stats: {e}")

def get_pending_announcements_for_user(user_id: int):
    """الحصول على الإعلانات المعلقة للمستخدم - معدلة لتراعي تاريخ انضمام المستخدم"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        
        # الحصول على تاريخ انضمام المستخدم
        cursor.execute('SELECT created_at FROM users WHERE user_id = ?', (user_id,))
        user_result = cursor.fetchone()
        
        if not user_result:
            conn.close()
            return []
        
        user_created_at = user_result[0]
        
        # الحصول على الإعلانات التي تم إنشاؤها بعد انضمام المستخدم
        cursor.execute('''
            SELECT pa.id, pa.announcement_text, pa.image_file_id, pa.announcement_type
            FROM pending_announcements pa
            WHERE pa.id NOT IN (
                SELECT sa.announcement_id 
                FROM sent_announcements sa 
                WHERE sa.user_id = ?
            )
            AND pa.target_users = 'all'
            AND pa.created_at >= ?
            ORDER BY pa.created_at DESC
        ''', (user_id, user_created_at))
        
        announcements = cursor.fetchall()
        conn.close()
        return announcements
    except Exception as e:
        logger.error(f"❌ خطأ في get_pending_announcements_for_user: {e}")
        return []

async def send_pending_announcements_to_user(context, user_id: int):
    """إرسال الإعلانات المعلقة للمستخدم عندما يعود للاتصال"""
    try:
        pending_announcements = get_pending_announcements_for_user(user_id)
        
        if not pending_announcements:
            return 0
        
        sent_count = 0
        
        for announcement in pending_announcements:
            ann_id, text, image_file_id, ann_type = announcement
            
            success = await send_message_with_photo(context, user_id, text, image_file_id, ann_type)
            
            if success:
                mark_announcement_sent(ann_id, user_id)
                sent_count += 1
            
            await asyncio.sleep(0.1)
        
        if sent_count > 0:
            logger.info(f"📨 تم إرسال {sent_count} إعلان معلق للمستخدم {user_id}")
        
        return sent_count
    except Exception as e:
        logger.error(f"❌ خطأ في send_pending_announcements_to_user: {e}")
        return 0

def get_total_active_users():
    """الحصول على عدد المستخدمين النشطين غير المحظورين"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_banned = FALSE')
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        logger.error(f"❌ خطأ في get_total_active_users: {e}")
        return 0

# وظائف جديدة لإدارة الإعلانات
def delete_announcement(announcement_id: int):
    """حذف إعلان محدد"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        
        # حذف الإعلان من جدول الإعلانات المرسلة أولاً
        cursor.execute('DELETE FROM sent_announcements WHERE announcement_id = ?', (announcement_id,))
        
        # ثم حذف الإعلان من جدول الإعلانات المعلقة
        cursor.execute('DELETE FROM pending_announcements WHERE id = ?', (announcement_id,))
        
        conn.commit()
        conn.close()
        logger.info(f"✅ تم حذف الإعلان {announcement_id} بنجاح")
        return True
    except Exception as e:
        logger.error(f"❌ خطأ في delete_announcement: {e}")
        return False

def get_recent_announcements(limit: int = 10):
    """الحصول على أحدث الإعلانات"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, announcement_text, announcement_type, sent_count, total_count, created_at
            FROM pending_announcements 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (limit,))
        
        announcements = cursor.fetchall()
        conn.close()
        return announcements
    except Exception as e:
        logger.error(f"❌ خطأ في get_recent_announcements: {e}")
        return []

# 🎮 نظام البوت الرئيسي المحسن
def get_main_keyboard(user_id: int, username: str = None):
    try:
        if is_admin(user_id, username):
            # واجهة الأدمن
            keyboard = [
                ["📊 الإحصائيات", "📋 الطلبات المعلقة"],
                ["🎯 إرسال توقعات اليوم", "🔮 إرسال توقع خاص"],
                ["📢 إرسال إعلان", "📈 إحصائيات الإعلانات"],
                ["🗑️ حذف توقعات خاصة", "🗑️ حذف توقعات اليوم"],
                ["🗑️ حذف إعلانات", "👥 إدارة المستخدمين"],
                ["🔍 بحث عن مستخدم", "💰 تعديل الأسعار"],
                ["🎁 هدايا الاشتراكات", "🔄 إعادة تعيين الإيرادات"],
                ["🆓 إدارة التجارب المجانية"],  # ⬅️ زر جديد
                ["🏠 START"]
            ]
        else:
            # واجهة المستخدم العادي
            status = get_user_subscription_status(user_id)
            
            if status in ['new', 'trial_eligible']:
                keyboard = [
                    ["🆓 تجربة مجانية 3 أيام", "💳 اشترك الآن"],
                    ["🏠 START", "👨‍💼 خدمة العملاء"]
                ]
            elif status in ['trial_active', 'active']:
                keyboard = [
                    ["🎯 توقعات اليوم", "🔮 التوقعات الخاصة"],
                    ["ℹ️ معلومات اشتراكي", "🏠 START"],
                    ["👨‍💼 خدمة العملاء"]
                ]
            else:  # expired or trial_used or banned
                keyboard = [
                    ["💳 اشترك الآن", "🏠 START"],
                    ["👨‍💼 خدمة العملاء"]
                ]
        
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    except Exception as e:
        logger.error(f"❌ خطأ في get_main_keyboard: {e}")
        # لوحة مفاتيح افتراضية في حالة الخطأ
        return ReplyKeyboardMarkup([["🏠 START"]], resize_keyboard=True)

def get_admin_keyboard():
    """لوحة مفاتيح خاصة للأدمن - معدلة"""
    keyboard = [
        ["📊 الإحصائيات", "📋 الطلبات المعلقة"],
        ["🎯 إرسال توقعات اليوم", "🔮 إرسال توقع خاص"],
        ["📢 إرسال إعلان", "📈 إحصائيات الإعلانات"],
        ["🗑️ حذف توقعات خاصة", "🗑️ حذف توقعات اليوم"],
        ["🗑️ حذف إعلانات", "👥 إدارة المستخدمين"],
        ["🔍 بحث عن مستخدم", "💰 تعديل الأسعار"],
        ["🎁 هدايا الاشتراكات", "🔄 إعادة تعيين الإيرادات"],
        ["🆓 إدارة التجارب المجانية"],  # ⬅️ زر جديد
        ["🏠 START"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_trial_management_keyboard():
    """لوحة مفاتيح إدارة النظام التجريبي"""
    trial_settings = get_trial_settings()
    status = "✅ مفعل" if trial_settings['enabled'] else "❌ معطل"
    
    keyboard = [
        [f"🔄 {'تعطيل' if trial_settings['enabled'] else 'تفعيل'} النظام التجريبي"],
        ["✏️ تعديل مدة التجربة"],
        ["🔄 تعديل نظام المرّة الواحدة"],
        ["📊 إحصائيات التجارب"],
        ["🔙 رجوع للوحة الأدمن"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_gift_subscription_keyboard():
    """لوحة مفاتيح هدايا الاشتراكات"""
    keyboard = [
        ["🎁 إضافة أيام اشتراك", "🎁 3 أيام تجريبية"],
        ["🔙 رجوع للوحة الأدمن"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_confirmation_keyboard():
    """لوحة مفاتيح التأكيد"""
    keyboard = [
        ["✅ نعم، تأكيد الإرسال", "❌ لا، إلغاء الإرسال"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_revenue_reset_confirmation_keyboard():
    """لوحة مفاتيح تأكيد إعادة تعيين الإيرادات"""
    keyboard = [
        ["⚠️ نعم، إعادة تعيين الإيرادات ⚠️", "❌ إلغاء العملية"],
        ["🔙 رجوع للوحة الأدمن"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_subscription_keyboard():
    """لوحة مفاتيح الاشتراك"""
    keyboard = [
        ["📱 سيريتل كاش"],
        ["📲 شام كاش"], 
        ["📞 ام تي ان كاش"],
        ["🏠 START"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_special_prediction_keyboard():
    """لوحة مفاتيح الدفع للتوقعات الخاصة"""
    keyboard = [
        ["🎯 اشترِ التوقع الخاص - سيريتل كاش"],
        ["🎯 اشترِ التوقع الخاص - شام كاش"], 
        ["🎯 اشترِ التوقع الخاص - ام تي ان كاش"],
        ["🏠 START"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def check_channel_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """
    التحقق من اشتراك المستخدم في القناة المطلوبة
    """
    try:
        if not REQUIRED_CHANNEL:
            return True
            
        channel_username = REQUIRED_CHANNEL.replace('@', '')
        
        try:
            # محاولة الحصول على معلومات العضو في القناة
            chat_member = await context.bot.get_chat_member(f"@{channel_username}", user_id)
            
            # التحقق من حالة العضو
            if chat_member.status in ['member', 'administrator', 'creator']:
                return True
            else:
                # إذا لم يكن مشتركاً، نعرض له رسالة طلب الاشتراك
                keyboard = [
                    [InlineKeyboardButton("📢 انضم للقناة", url=f"https://t.me/{channel_username}")],
                    [InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_subscription")]
                ]
                
                await update.message.reply_text(
                    f"📢 **يشترط الاشتراك في القناة**\n\n"
                    f"عذراً عزيزي، يجب الانضمام إلى قناتنا أولاً لاستخدام البوت:\n"
                    f"@{channel_username}\n\n"
                    f"✅ بعد الانضمام، اضغط على زر 'تحقق من الاشتراك'",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
                return False
                
        except Exception as e:
            logger.error(f"❌ خطأ في التحقق من الاشتراك: {e}")
            # في حالة الخطأ، نسمح للمستخدم بالمتابعة لتجنب حظر البوت
            return True
            
    except Exception as e:
        logger.error(f"❌ خطأ في check_channel_subscription: {e}")
        return True

async def check_channel_subscription_callback(query, context, user_id: int) -> bool:
    """
    التحقق من الاشتراك عند الضغط على زر التحقق
    """
    try:
        if not REQUIRED_CHANNEL:
            return True
            
        channel_username = REQUIRED_CHANNEL.replace('@', '')
        
        try:
            chat_member = await context.bot.get_chat_member(f"@{channel_username}", user_id)
            
            if chat_member.status in ['member', 'administrator', 'creator']:
                await query.edit_message_text(
                    "✅ **تم التحقق بنجاح!**\n\n"
                    "شكراً لانضمامك إلى قناتنا. يمكنك الآن استخدام البوت.",
                    parse_mode='Markdown'
                )
                return True
            else:
                keyboard = [
                    [InlineKeyboardButton("📢 انضم للقناة", url=f"https://t.me/{channel_username}")],
                    [InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_subscription")]
                ]
                
                await query.edit_message_text(
                    f"❌ **لم يتم العثور على اشتراكك**\n\n"
                    f"يبدو أنك لم تنضم بعد إلى قناتنا:\n"
                    f"@{channel_username}\n\n"
                    f"✅ بعد الانضمام، اضغط على زر 'تحقق من الاشتراك' مرة أخرى",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
                return False
                
        except Exception as e:
            logger.error(f"❌ خطأ في التحقق من الاشتراك: {e}")
            await query.edit_message_text(
                "❌ **حدث خطأ في التحقق**\n\n"
                "يرجى المحاولة مرة أخرى لاحقاً.",
                parse_mode='Markdown'
            )
            return False
            
    except Exception as e:
        logger.error(f"❌ خطأ في check_channel_subscription_callback: {e}")
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        user_id = user.id
        username = user.username
        
        # ✅ التحقق من الاشتراك في القناة إذا كانت محددة
        if REQUIRED_CHANNEL and not await check_channel_subscription(update, context, user_id):
            return
        
        if not get_user(user_id):
            create_user(user_id, username, user.first_name)
        
        # ✅ إرسال الإعلانات المعلقة للمستخدم عند عودته
        pending_sent = await send_pending_announcements_to_user(context, user_id)
        
        # التحقق إذا كان أدمن
        if is_admin(user_id, username):
            add_admin(user_id, username, user.first_name)
            await show_admin_dashboard(update, context)
            return
        
        status = get_user_subscription_status(user_id)
        
        if status == 'banned':
            await update.message.reply_text("❌ **تم حظر حسابك من استخدام البوت**")
            return
        
        # النص الترحيبي حسب الحالة
        if status in ['new', 'trial_eligible']:
            trial_settings = get_trial_settings()
            if trial_settings['enabled']:
                welcome_text = f"""
⚽ **أهلاً بك في بوت توقعات المباريات الاحترافية** 🎯

🌟 **جرب البوت مجاناً لمدة {trial_settings['days']} أيام!**
• توقعات يومية دقيقة للمباريات
• تحليلات احترافية من خبراء  
• تجربة كاملة بدون أي تكلفة

🆓 **الميزات المتاحة في التجربة:**
• مشاهدة جميع التوقعات اليومية 📊
• الوصول للتوقعات الخاصة 🔮
• تحديثات مستمرة 🚀

💰 **بعد انتهاء التجربة:**
اشتراك شهري بـ {SUBSCRIPTION_SETTINGS['monthly_price']:,} ليرة سورية فقط

🎁 **ابدأ رحلتك مع التوقعات الآن!**
                """
            else:
                welcome_text = f"""
⚽ **أهلاً بك في بوت توقعات المباريات الاحترافية** 🎯

🌟 **ماذا نقدم لك؟**
• توقعات يومية دقيقة للمباريات
• تحليلات احترافية من خبراء
• نتائج مضمونة وموثوقة

💰 **اشترك الآن:**
اشتراك شهري بـ {SUBSCRIPTION_SETTINGS['monthly_price']:,} ليرة سورية فقط

🎁 **ابدأ رحلتك مع التوقعات الآن!**
                """
                
        elif status == 'trial_active':
            user_data = get_user(user_id)
            if user_data and user_data[3]:
                expiry_date = datetime.strptime(user_data[3], '%Y-%m-%d').date()
                remaining_days = (expiry_date - datetime.now().date()).days
                
                welcome_text = f"""
🎉 **أهلاً بك في الفترة التجريبية المجانية!**

🆓 **أنت حالياً في فترة تجريبية مجانية**
✅ **تنتهي في:** {expiry_date.strftime('%Y-%m-%d')}
⏰ **متبقي:** {remaining_days} يوم

🎯 **استمتع بجميع الميزات خلال الفترة التجريبية!**

💡 **بعد انتهاء التجربة، يمكنك الاشتراك للاستمرار.**
                """
            else:
                welcome_text = """
🎉 **أهلاً بك في الفترة التجريبية المجانية!**

🆓 **أنت حالياً في فترة تجريبية مجانية**
✅ **تم تفعيل 3 أيام مجانية لحسابك**

🎯 **استمتع بجميع الميزات خلال الفترة التجريبية!**

💡 **بعد انتهاء التجربة، يمكنك الاشتراك للاستمرار.**
                """
            
        elif status == 'active':
            user_data = get_user(user_id)
            if user_data and user_data[3]:
                expiry_date = datetime.strptime(user_data[3], '%Y-%m-%d').date()
                remaining_days = (expiry_date - datetime.now().date()).days
                
                welcome_text = f"""
🎉 **أهلاً بعودتك!**

✅ **اشتراكك نشط حتى:** {expiry_date.strftime('%Y-%m-%d')}
⏰ **متبقي:** {remaining_days} يوم

🎯 **استمتع بتوقعاتنا اليومية والتوقعات الخاصة!**
                """
            else:
                welcome_text = """
🎉 **أهلاً بعودتك!**

✅ **اشتراكك نشط**

🎯 **استمتع بتوقعاتنا اليومية والتوقعات الخاصة!**
                """
            
        else:  # expired or trial_used
            welcome_text = f"""
❌ **انتهى اشتراكك**

💡 **للاستمرار في مشاهدة التوقعات:**
جدد اشتراكك الآن واستعد للربح!

💰 **سعر التجديد:** {SUBSCRIPTION_SETTINGS['monthly_price']:,} ليرة سورية

⚠️ **تنويه:** لا يمكنك مشاهدة التوقعات حتى تجدد اشتراكك
            """
        
        # إضافة إشعار بالإعلانات المعلقة إذا تم إرسالها
        if pending_sent > 0:
            welcome_text = f"📨 **تم استلام {pending_sent} إعلان أثناء غيابك**\n\n" + welcome_text
        
        await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard(user_id, username))
    except Exception as e:
        logger.error(f"❌ خطأ في start: {e}")
        await update.message.reply_text("❌ حدث خطأ غير متوقع. يرجى المحاولة مرة أخرى.")

async def show_admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض لوحة تحكم الأدمن"""
    try:
        stats = get_bot_stats()
        
        dashboard_text = f"""
👑 **لوحة تحكم الأدمن**

📊 **الإحصائيات:**
👥 إجمالي المستخدمين: {stats['total_users']}
✅ المشتركين النشطين: {stats['active_subscribers']}
🚫 المستخدمين المحظورين: {stats['banned_users']}
💰 إيرادات الاشتراكات: {stats['subscription_revenue']:,.0f} ليرة
🎯 إيرادات التوقعات: {stats['predictions_revenue']:,.0f} ليرة
💵 الإجمالي: {stats['subscription_revenue'] + stats['predictions_revenue']:,.0f} ليرة

🛠️ **اختر من الأزرار أدناه:**
        """
        
        await update.message.reply_text(dashboard_text, reply_markup=get_admin_keyboard())
    except Exception as e:
        logger.error(f"❌ خطأ في show_admin_dashboard: {e}")
        await update.message.reply_text("❌ حدث خطأ في عرض لوحة التحكم.")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        
        callback_data = query.data
        
        # ✅ معالجة زر التحقق من الاشتراك في القناة
        if callback_data == "check_subscription":
            user_id = query.from_user.id
            
            if await check_channel_subscription_callback(query, context, user_id):
                # إذا كان مشتركاً، نعيد توجيهه لبدء استخدام البوت
                await start(update, context)
            return
        
        if callback_data.startswith("view_special_"):
            prediction_id = int(callback_data.replace("view_special_", ""))
            await show_special_prediction_details(query, context, prediction_id)
        elif callback_data.startswith("buy_special_"):
            prediction_id = int(callback_data.replace("buy_special_", ""))
            await show_special_predictions_payment(query, context, prediction_id)
        elif callback_data == "back_to_special_list":
            await show_special_predictions_list(query, context)
        elif callback_data == "back_to_main":
            await start(update, context)
        elif callback_data in ["show_terms", "show_support"]:
            await handle_special_prediction_callbacks(update, context)
        elif callback_data.startswith("approve_sub_"):
            transaction_id = int(callback_data.replace("approve_sub_", ""))
            await approve_subscription_callback(query, context, transaction_id)
        elif callback_data.startswith("reject_sub_"):
            transaction_id = int(callback_data.replace("reject_sub_", ""))
            await reject_subscription_callback(query, context, transaction_id)
        elif callback_data.startswith("approve_pred_"):
            transaction_id = int(callback_data.replace("approve_pred_", ""))
            await approve_prediction_callback(query, context, transaction_id)
        elif callback_data.startswith("reject_pred_"):
            transaction_id = int(callback_data.replace("reject_pred_", ""))
            await reject_prediction_callback(query, context, transaction_id)
            
    except Exception as e:
        logger.error(f"❌ خطأ في handle_callback: {e}")

async def show_special_prediction_details(query, context, prediction_id):
    """عرض تفاصيل التوقع الخاص"""
    try:
        prediction = get_special_prediction_by_id(prediction_id)
        if not prediction:
            await query.edit_message_text("❌ **لم يتم العثور على التوقع**")
            return
        
        pred_id, title, description, content, image_file_id = prediction
        
        details_text = f"""
🔮 **{title}**

📝 **الوصف:**
{description}

💰 **سعر التوقع الخاص:** {SUBSCRIPTION_SETTINGS['prediction_price']:,} ليرة

⚠️ **تنويه هام:** المحتوى الحقيقي للتوقع سيظهر بعد الشراء والموافقة من الإدارة
        """
        
        keyboard = [
            [InlineKeyboardButton("🛒 اشترِ هذا التوقع 🎯", callback_data=f"buy_special_{pred_id}")],
            [InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_to_special_list")]
        ]
        
        if image_file_id:
            await query.edit_message_media(
                media=InputMediaPhoto(
                    media=image_file_id,
                    caption=details_text,
                    parse_mode='Markdown'
                ),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.edit_message_text(
                details_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"❌ خطأ في show_special_prediction_details: {e}")

async def show_special_predictions_list(query, context):
    """عرض قائمة التوقعات الخاصة"""
    try:
        user_id = query.from_user.id
        
        special_predictions = get_active_special_predictions()
        if not special_predictions:
            await query.edit_message_text(
                "📭 **لا توجد توقعات خاصة متاحة حالياً**\n\n"
                "🔔 سنقوم بإعلامك فور توفر توقعات خاصة جديدة\n"
                "💫 ترقبوا العروض الحصرية القادمة!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 START", callback_data="back_to_main")]])
            )
            return
        
        list_text = "🔮 **قائمة التوقعات الخاصة المتاحة**\n\n"
        keyboard = []
        
        for pred in special_predictions[:10]:
            pred_id, title, description, content, image_file_id = pred
            list_text += f"• **{title}**\n"
            keyboard.append([InlineKeyboardButton(f"📊 {title}", callback_data=f"view_special_{pred_id}")])
        
        keyboard.append([InlineKeyboardButton("🏠 START", callback_data="back_to_main")])
        
        await query.edit_message_text(
            list_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"❌ خطأ في show_special_predictions_list: {e}")

async def show_special_predictions_payment(query, context, prediction_id):
    """عرض خيارات الدفع لتوقع خاص محدد"""
    try:
        prediction = get_special_prediction_by_id(prediction_id)
        if not prediction:
            await query.edit_message_text("❌ **لم يتم العثور على التوقع**")
            return
        
        pred_id, title, description, content, image_file_id = prediction
        
        text = f"🎯 **شراء التوقع الخاص: {title}** 🎯\n\n"
        text += "💰 **سعر التوقع الخاص:** {:,} ليرة سورية\n\n".format(SUBSCRIPTION_SETTINGS['prediction_price'])
        text += "**اختر طريقة الدفع:**"
        
        context.user_data['selected_prediction_id'] = prediction_id
        context.user_data['payment_type'] = 'special_prediction'
        
        keyboard = [
            ["📱 سيريتل كاش"],
            ["📲 شام كاش"], 
            ["📞 ام تي ان كاش"],
            ["🔙 رجوع"]
        ]
        
        await query.message.reply_text(
            text, 
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        
    except Exception as e:
        logger.error(f"❌ خطأ في show_special_predictions_payment: {e}")
        await query.message.reply_text("❌ حدث خطأ في عرض خيارات الدفع.")

async def handle_special_prediction_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة callbacks التوقعات الخاصة"""
    try:
        query = update.callback_query
        await query.answer()
        
        callback_data = query.data
        
        if callback_data == "show_terms":
            terms_text = """
📋 **شروط شراء التوقعات الخاصة:**

✅ **الشروط والأحكام:**
• التوقعات خاصة بحاملها ولا يسمح بمشاركتها
• لا تتحمل الإدارة مسؤولية الخسائر
• التوقعات تستند لتحليلات واحتمالات
• يمنع استخدام المحتوى لأغراض تجارية

⚖️ **سياسة الاسترجاع:**
• لا يوجد استرجاع للمبالغ بعد الشراء
• في حال وجود مشكلة، يرجى التواصل مع الدعم

🔒 **خصوصية البيانات:**
• نحن نحافظ على خصوصية معلوماتك
• بيانات الدفع محفوظة بشكل آمن
            """
            await query.edit_message_text(
                terms_text,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 الرجوع", callback_data="back_to_special")
                ]])
            )
            
        elif callback_data == "show_support":
            support_text = """
👨‍💼 **دعم التوقعات الخاصة:**

📞 **للتواصل والدعم:**
• الدعم الفني: @username
• استفسارات الدفع: @username
• الشكاوى والمقترحات: @username

⏰ **أوقات الدعم:**
• متواجدون على مدار الساعة ءً
• الاستجابة خلال 24 ساعة كحد أقصى

            """
            await query.edit_message_text(
                support_text,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 الرجوع", callback_data="back_to_special")
                ]])
            )
            
    except Exception as e:
        logger.error(f"❌ خطأ في handle_special_prediction_callbacks: {e}")

async def approve_subscription_callback(query, context, transaction_id):
    """معالجة الموافقة على الاشتراك من الكallback"""
    try:
        transaction = get_subscription_transaction(transaction_id)
        if not transaction:
            await query.edit_message_text("❌ **لم يتم العثور على المعاملة**")
            return
        
        user_id = transaction[1]
        update_subscription_status(transaction_id, 'approved')
        update_subscription(user_id, 30)  # 30 يوم
        
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="🎉 **تم تفعيل اشتراكك بنجاح!**\n\n"
                     "✅ **يمكنك الآن مشاهدة التوقعات اليومية والتوقعات الخاصة.**\n\n"
                     "💡 **استخدم زر 🏠 START لمشاهدة آخر التوقعات!**\n\n"
                     "استمتع بتوقعاتنا وربحاً موفقاً! 🏆"
            )
        except Exception as e:
            logger.error(f"❌ فشل في إعلام المستخدم {user_id}: {e}")
        
        await query.edit_message_text(
            f"✅ **تم تفعيل الاشتراك بنجاح**\n\n"
            f"🆔 معاملة: {transaction_id}\n"
            f"👤 مستخدم: {user_id}\n"
            f"⏰ تمت الإضافة: 30 يوم"
        )
    except Exception as e:
        logger.error(f"❌ خطأ في approve_subscription_callback: {e}")
        await query.edit_message_text("❌ حدث خطأ في تفعيل الاشتراك.")

async def reject_subscription_callback(query, context, transaction_id):
    """معالجة رفض الاشتراك من الكallback"""
    try:
        transaction = get_subscription_transaction(transaction_id)
        if not transaction:
            await query.edit_message_text("❌ **لم يتم العثور على المعاملة**")
            return
        
        update_subscription_status(transaction_id, 'rejected')
        
        try:
            await context.bot.send_message(
                chat_id=transaction[1],
                text="❌ **تم رفض طلب الاشتراك**\n\n"
                     "يرجى التواصل مع خدمة العملاء للاستفسار عن السبب."
            )
        except Exception as e:
            logger.error(f"❌ فشل في إعلام المستخدم {transaction[1]}: {e}")
        
        await query.edit_message_text(
            f"❌ **تم رفض طلب الاشتراك**\n\n"
            f"🆔 معاملة: {transaction_id}\n"
            f"👤 مستخدم: {transaction[1]}"
        )
    except Exception as e:
        logger.error(f"❌ خطأ في reject_subscription_callback: {e}")
        await query.edit_message_text("❌ حدث خطأ في رفض الاشتراك.")

async def approve_prediction_callback(query, context, transaction_id):
    """معالجة الموافقة على التوقع الخاص من الكallback"""
    try:
        transaction = get_prediction_transaction(transaction_id)
        if not transaction:
            await query.edit_message_text("❌ **لم يتم العثور على المعاملة**")
            return
        
        update_prediction_status(transaction_id, 'approved')
        
        # الحصول على معرف التوقع الخاص من المعاملة
        prediction_id = transaction[7] if len(transaction) > 7 else None
        
        try:
            if prediction_id:
                # إرسال المحتوى الحقيقي للتوقع الخاص للمستخدم
                special_prediction = get_special_prediction_by_id(prediction_id)
                if special_prediction:
                    pred_id, title, description, content, image_file_id = special_prediction
                    
                    # إرسال المحتوى الحقيقي
                    if image_file_id:
                        await context.bot.send_photo(
                            chat_id=transaction[1],
                            photo=image_file_id,
                            caption=f"🔮 **{title}**\n\n{content}\n\n💫 *نتمنى لك ربحاً موفقاً*"
                        )
                    else:
                        await context.bot.send_message(
                            chat_id=transaction[1],
                            text=f"🔮 **{title}**\n\n{content}\n\n💫 *نتمنى لك ربحاً موفقاً*"
                        )
                else:
                    await context.bot.send_message(
                        chat_id=transaction[1],
                        text="✅ **تمت الموافقة على طلبك!**\n\n"
                             "📭 **عذراً، لم نتمكن من العثور على التوقع الخاص المطلوب.**\n\n"
                             "يرجى التواصل مع خدمة العملاء."
                    )
            else:
                await context.bot.send_message(
                    chat_id=transaction[1],
                    text="✅ **تمت الموافقة على طلبك!**\n\n"
                         "📭 **عذراً، لم نتمكن من العثور على التوقع الخاص المطلوب.**\n\n"
                         "يرجى التواصل مع خدمة العملاء."
                )
        except Exception as e:
            logger.error(f"❌ خطأ في إرسال التوقع إلى {transaction[1]}: {e}")
            await context.bot.send_message(
                chat_id=transaction[1],
                text="✅ **تمت الموافقة على طلبك!**\n\n"
                     "⚠️ **حدث خطأ في إرسال التوقع، يرجى التواصل مع خدمة العملاء.**"
            )
        
        await query.edit_message_text(
            f"✅ **تمت موافقة على التوقع الخاص وتم إرساله للمستخدم**\n\n"
            f"🆔 معاملة: {transaction_id}\n"
            f"👤 مستخدم: {transaction[1]}"
        )
    except Exception as e:
        logger.error(f"❌ خطأ في approve_prediction_callback: {e}")
        await query.edit_message_text("❌ حدث خطأ في موافقة التوقع.")

async def reject_prediction_callback(query, context, transaction_id):
    """معالجة رفض التوقع الخاص من الكallback"""
    try:
        transaction = get_prediction_transaction(transaction_id)
        if not transaction:
            await query.edit_message_text("❌ **لم يتم العثور على المعاملة**")
            return
        
        update_prediction_status(transaction_id, 'rejected')
        
        try:
            await context.bot.send_message(
                chat_id=transaction[1],
                text="❌ **تم رفض طلب التوقع الخاص**\n\n"
                     "يرجى التواصل مع خدمة العملاء للاستفسار عن السبب."
            )
        except Exception as e:
            logger.error(f"❌ فشل في إعلام المستخدم {transaction[1]}: {e}")
        
        await query.edit_message_text(
            f"❌ **تم رفض طلب التوقع الخاص**\n\n"
            f"🆔 معاملة: {transaction_id}\n"
            f"👤 مستخدم: {transaction[1]}"
        )
    except Exception as e:
        logger.error(f"❌ خطأ في reject_prediction_callback: {e}")
        await query.edit_message_text("❌ حدث خطأ في رفض التوقع.")

async def handle_free_trial_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة طلب التجربة المجانية - معدلة"""
    try:
        user = update.effective_user
        user_id = user.id
        username = user.username
        
        # ✅ التحقق من الاشتراك في القناة إذا كانت محددة
        if REQUIRED_CHANNEL and not await check_channel_subscription(update, context, user_id):
            return
        
        status = get_user_subscription_status(user_id)
        trial_settings = get_trial_settings()
        
        if not trial_settings['enabled']:
            await update.message.reply_text(
                "❌ **النظام التجريبي غير مفعل حالياً**\n\n"
                "💳 يمكنك الاشتراك مباشرة للاستمتاع بجميع الميزات.",
                reply_markup=get_main_keyboard(user_id, username)
            )
            return
        
        if status != 'trial_eligible':
            if status == 'trial_active':
                user_data = get_user(user_id)
                if user_data and user_data[3]:
                    expiry_date = datetime.strptime(user_data[3], '%Y-%m-%d').date()
                    remaining_days = (expiry_date - datetime.now().date()).days
                    await update.message.reply_text(
                        f"⚠️ **لديك تجربة مجانية نشطة بالفعل**\n\n"
                        f"📅 تنتهي في: {expiry_date.strftime('%Y-%m-%d')}\n"
                        f"⏰ متبقي: {remaining_days} يوم\n\n"
                        f"استمتع بالتجربة! 🎉",
                        reply_markup=get_main_keyboard(user_id, username)
                    )
                else:
                    await update.message.reply_text(
                        "⚠️ **لديك تجربة مجانية نشطة بالفعل**\n\n"
                        "استمتع بالتجربة! 🎉",
                        reply_markup=get_main_keyboard(user_id, username)
                    )
            elif status == 'trial_used':
                await update.message.reply_text(
                    "❌ **سبق واستخدمت التجربة المجانية**\n\n"
                    "⚠️ التجربة المجانية متاحة لمرة واحدة فقط لكل مستخدم.\n\n"
                    "💳 يمكنك الاشتراك الآن للاستمرار في استخدام البوت.",
                    reply_markup=get_main_keyboard(user_id, username)
                )
            elif status == 'active':
                await update.message.reply_text(
                    "✅ **لديك اشتراك نشط بالفعل**\n\n"
                    "لا تحتاج لتجربة مجانية.",
                    reply_markup=get_main_keyboard(user_id, username)
                )
            else:
                await update.message.reply_text(
                    "❌ **لا يمكنك استخدام التجربة المجانية**\n\n"
                    "💳 يمكنك الاشتراك للاستمرار في استخدام البوت.",
                    reply_markup=get_main_keyboard(user_id, username)
                )
            return
        
        # تفعيل التجربة
        success = activate_trial(user_id)
        
        if success:
            user_data = get_user(user_id)
            if user_data and user_data[3]:
                expiry_date = datetime.strptime(user_data[3], '%Y-%m-%d').date()
                
                await update.message.reply_text(
                    f"🎉 **تم تفعيل التجربة المجانية بنجاح!**\n\n"
                    f"🆓 **مدة التجربة:** {trial_settings['days']} أيام\n"
                    f"✅ **تنتهي في:** {expiry_date.strftime('%Y-%m-%d')}\n\n"
                    f"🎯 **الآن يمكنك:**\n"
                    f"• مشاهدة جميع التوقعات اليومية 📊\n"
                    f"• الوصول للتوقعات الخاصة 🔮\n"
                    f"• الاستفادة من جميع الميزات 🚀\n\n"
                    f"💡 **استخدم زر 🏠 START لبدء مشاهدة التوقعات!**\n\n"
                    f"⚠️ **تنويه:** هذه التجربة لمرة واحدة فقط لكل مستخدم",
                    reply_markup=get_main_keyboard(user_id, username)
                )
            else:
                await update.message.reply_text(
                    f"🎉 **تم تفعيل التجربة المجانية بنجاح!**\n\n"
                    f"🆓 **مدة التجربة:** {trial_settings['days']} أيام\n\n"
                    f"🎯 **الآن يمكنك:**\n"
                    f"• مشاهدة جميع التوقعات اليومية 📊\n"
                    f"• الوصول للتوقعات الخاصة 🔮\n"
                    f"• الاستفادة من جميع الميزات 🚀\n\n"
                    f"💡 **استخدم زر 🏠 START لبدء مشاهدة التوقعات!**",
                    reply_markup=get_main_keyboard(user_id, username)
                )
            
            # إشعار الأدمن
            admin_text = f"""
🆓 **تفعيل تجربة مجانية جديدة**

👤 **المستخدم:** {user.first_name}
📧 **اليوزر:** @{username if username else 'بدون يوزر'}
🆔 **ID:** {user_id}
📅 **المدة:** {trial_settings['days']} أيام
⏰ **التاريخ:** {datetime.now().strftime('%Y-%m-%d %H:%M')}
            """
            
            await notify_admins(context, admin_text, None, "trial")
            
        else:
            await update.message.reply_text(
                "❌ **فشل في تفعيل التجربة المجانية**\n\n"
                "يرجى المحاولة مرة أخرى أو التواصل مع خدمة العملاء.",
                reply_markup=get_main_keyboard(user_id, username)
            )
            
    except Exception as e:
        logger.error(f"❌ خطأ في handle_free_trial_request: {e}")
        await update.message.reply_text("❌ حدث خطأ في تفعيل التجربة المجانية.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        user_id = user.id
        username = user.username
        text = update.message.text
        
        # ✅ التحقق من الاشتراك في القناة إذا كانت محددة
        if REQUIRED_CHANNEL and not await check_channel_subscription(update, context, user_id):
            return
        
        if text is None:
            if update.message.photo:
                if is_admin(user_id, username):
                    await handle_admin_conversation(update, context, "")
                    return
                else:
                    await update.message.reply_text(
                        "❌ **يرجى استخدام الأزرار الموجودة في القائمة للتنقل**",
                        reply_markup=get_main_keyboard(user_id, username)
                    )
                    return
            else:
                await update.message.reply_text(
                    "❌ **يرجى استخدام الأزرار الموجودة في القائمة**",
                    reply_markup=get_main_keyboard(user_id, username)
                )
                return
        
        # ✅ معالجة زر START
        if text == "🏠 START":
            await start(update, context)
            return
        
        # التحقق من الحظر
        if get_user_subscription_status(user_id) == 'banned':
            await update.message.reply_text("❌ **تم حظر حسابك من استخدام البوت**")
            return
        
        # معالجة أزرار التوقعات الخاصة بشكل صحيح
        if text in ["🎯 اشترِ التوقع الخاص - سيريتل كاش", "🎯 اشترِ التوقع الخاص - شام كاش", "🎯 اشترِ التوقع الخاص - ام تي ان كاش"]:
            # استخراج طريقة الدفع من النص
            if "سيريتل" in text:
                method_text = "📱 سيريتل كاش"
            elif "شام" in text:
                method_text = "📲 شام كاش"
            else:
                method_text = "📞 ام تي ان كاش"
            
            await handle_payment_method_selection(update, context, method_text)
            return
        
        # التحقق إذا كان أدمن
        if is_admin(user_id, username):
            await handle_admin_buttons(update, context, text)
            return
        
        # معالجة المستخدمين العاديين
        if text == "🆓 تجربة مجانية 3 أيام":
            await handle_free_trial_request(update, context)
        elif text == "💳 اشترك الآن":
            await show_subscription_options(update, context)
        elif text == "💳 تجديد الاشتراك":
            await show_subscription_options(update, context)
        elif text == "🎯 توقعات اليوم":
            await show_today_predictions(update, context)
        elif text == "🔮 التوقعات الخاصة":
            await show_special_predictions(update, context)
        elif text == "ℹ️ معلومات اشتراكي":
            await show_subscription_info(update, context)
        elif text == "👨‍💼 خدمة العملاء":
            await customer_service(update, context)
        elif text in ["📱 سيريتل كاش", "📲 شام كاش", "📞 ام تي ان كاش"]:
            await handle_payment_method_selection(update, context, text)
        elif text == "🔙 رجوع":
            await start(update, context)
        else:
            await handle_conversation_state(update, context, text)
    except Exception as e:
        logger.error(f"❌ خطأ في handle_message: {e}")
        await update.message.reply_text("❌ حدث خطأ غير متوقع. يرجى المحاولة مرة أخرى.")

async def handle_admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """معالجة أزرار الأدمن - معدلة"""
    try:
        user = update.effective_user
        
        if text == "📊 الإحصائيات":
            await show_admin_stats(update, context)
        elif text == "📋 الطلبات المعلقة":
            await show_admin_pending_requests(update, context)
        elif text == "🎯 إرسال توقعات اليوم":
            await admin_add_daily_predictions(update, context)
        elif text == "🔮 إرسال توقع خاص":
            await admin_add_special_prediction(update, context)
        elif text == "📢 إرسال إعلان":
            await admin_send_announcement(update, context)
        elif text == "📈 إحصائيات الإعلانات":
            await admin_announcement_stats(update, context)
        elif text == "🗑️ حذف توقعات خاصة":
            await admin_delete_special_predictions(update, context)
        elif text == "🗑️ حذف توقعات اليوم":
            await admin_delete_daily_predictions(update, context)
        elif text == "🗑️ حذف إعلانات":
            await admin_delete_announcements(update, context)
        elif text == "👥 إدارة المستخدمين":
            await admin_manage_users(update, context)
        elif text == "🔍 بحث عن مستخدم":
            await admin_search_user(update, context)
        elif text == "💰 تعديل الأسعار":
            await admin_edit_prices(update, context)
        elif text == "🎁 هدايا الاشتراكات":
            await admin_gift_subscriptions(update, context)
        elif text == "🔄 إعادة تعيين الإيرادات":
            await admin_reset_revenue(update, context)
        elif text == "🆓 إدارة التجارب المجانية":
            await admin_manage_trials(update, context)
        elif text in ["🔄 تفعيل النظام التجريبي", "🔄 تعطيل النظام التجريبي", 
                     "✏️ تعديل مدة التجربة", "🔄 تعديل نظام المرّة الواحدة",
                     "📊 إحصائيات التجارب"]:
            await handle_trial_management(update, context, text)
        elif text == "🎁 إضافة أيام اشتراك":
            await admin_add_subscription_days(update, context)
        elif text == "🎁 3 أيام تجريبية":
            await admin_give_trial_days(update, context)
        elif text == "🔙 رجوع للوحة الأدمن":
            await show_admin_dashboard(update, context)
        elif text == "🏠 START":
            await show_admin_dashboard(update, context)
        elif text in ["✅ نعم، تأكيد الإرسال", "❌ لا، إلغاء الإرسال"]:
            await handle_admin_confirmation(update, context, text)
        elif text in ["⚠️ نعم، إعادة تعيين الإيرادات ⚠️", "❌ إلغاء العملية"]:
            await handle_revenue_reset_confirmation(update, context, text)
        else:
            # معالجة أزرار إدارة المستخدمين والإعلانات
            if text == "📊 تحديث القائمة":
                await admin_manage_users(update, context)
            elif text.startswith("🗑️ حذف التوقع "):
                await handle_delete_special_prediction(update, context, text)
            elif text.startswith("🗑️ حذف التوقع اليومي "):
                await handle_delete_daily_prediction(update, context, text)
            elif text.startswith("🗑️ حذف الإعلان "):
                await handle_delete_announcement(update, context, text)
            else:
                await handle_admin_conversation(update, context, text)
    except Exception as e:
        logger.error(f"❌ خطأ في handle_admin_buttons: {e}")
        await update.message.reply_text("❌ حدث خطأ في معالجة الأمر.")

async def admin_manage_trials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض واجهة إدارة النظام التجريبي"""
    try:
        trial_settings = get_trial_settings()
        status = "✅ مفعل" if trial_settings['enabled'] else "❌ معطل"
        one_time = "✅ نعم" if trial_settings['one_time'] else "❌ لا"
        
        # إحصائيات التجارب
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM free_trials WHERE used_trial = TRUE')
        total_trials = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM free_trials WHERE trial_end >= ?', (datetime.now().date(),))
        active_trials = cursor.fetchone()[0]
        conn.close()
        
        text = f"""
🆓 **إدارة النظام التجريبي المجاني**

⚙️ **الإعدادات الحالية:**
• الحالة: {status}
• المدة: {trial_settings['days']} أيام
• لمرة واحدة: {one_time}

📊 **الإحصائيات:**
• إجمالي التجارب المستخدمة: {total_trials}
• التجارب النشطة حالياً: {active_trials}

🛠️ **اختر الإعداد الذي تريد تعديله:**
        """
        
        await update.message.reply_text(text, reply_markup=get_trial_management_keyboard())
    except Exception as e:
        logger.error(f"❌ خطأ في admin_manage_trials: {e}")
        await update.message.reply_text("❌ حدث خطأ في عرض إدارة النظام التجريبي.")

async def handle_trial_management(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """معالجة إدارة النظام التجريبي"""
    try:
        trial_settings = get_trial_settings()
        
        if text == "🔄 تفعيل النظام التجريبي":
            update_trial_setting('enabled', 'true')
            await update.message.reply_text(
                "✅ **تم تفعيل النظام التجريبي بنجاح**\n\n"
                "سيتمكن المستخدمون الجدد الآن من طلب تجربة مجانية.",
                reply_markup=get_trial_management_keyboard()
            )
            
        elif text == "🔄 تعطيل النظام التجريبي":
            update_trial_setting('enabled', 'false')
            await update.message.reply_text(
                "✅ **تم تعطيل النظام التجريبي بنجاح**\n\n"
                "لن يتمكن المستخدمون الجدد من طلب تجربة مجانية.",
                reply_markup=get_trial_management_keyboard()
            )
            
        elif text == "✏️ تعديل مدة التجربة":
            context.user_data['admin_action'] = 'edit_trial_days'
            await update.message.reply_text(
                "✏️ **تعديل مدة التجربة**\n\n"
                f"المدة الحالية: {trial_settings['days']} أيام\n\n"
                "أرسل عدد الأيام الجديدة (رقم فقط):\n"
                "❌ للإلغاء: /cancel"
            )
            
        elif text == "🔄 تعديل نظام المرّة الواحدة":
            new_value = not trial_settings['one_time']
            update_trial_setting('one_time', str(new_value).lower())
            status = "✅ مفعل" if new_value else "❌ معطل"
            
            await update.message.reply_text(
                f"✅ **تم {'تفعيل' if new_value else 'تعطيل'} نظام المرّة الواحدة**\n\n"
                f"الحالة: {status}\n\n"
                f"سي{'تمكن' if new_value else 'لا يتمكن'} المستخدمون من استخدام التجربة مرة واحدة فقط.",
                reply_markup=get_trial_management_keyboard()
            )
            
        elif text == "📊 إحصائيات التجارب":
            await show_trial_stats(update, context)
            
        elif text == "🔙 رجوع للوحة الأدمن":
            await show_admin_dashboard(update, context)
            
    except Exception as e:
        logger.error(f"❌ خطأ في handle_trial_management: {e}")
        await update.message.reply_text("❌ حدث خطأ في معالجة الأمر.")

async def show_trial_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إحصائيات مفصلة للتجارب"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        
        # إحصائيات عامة
        cursor.execute('SELECT COUNT(*) FROM free_trials WHERE used_trial = TRUE')
        total_trials = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM free_trials WHERE trial_end >= ?', (datetime.now().date(),))
        active_trials = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM free_trials WHERE trial_end < ?', (datetime.now().date(),))
        expired_trials = cursor.fetchone()[0]
        
        # آخر 10 تجارب
        cursor.execute('''
            SELECT ft.user_id, u.username, u.first_name, ft.trial_start, ft.trial_end 
            FROM free_trials ft 
            JOIN users u ON ft.user_id = u.user_id 
            ORDER BY ft.created_at DESC 
            LIMIT 10
        ''')
        recent_trials = cursor.fetchall()
        conn.close()
        
        trial_settings = get_trial_settings()
        
        text = f"""
📊 **إحصائيات مفصلة للنظام التجريبي**

⚙️ **الإعدادات:**
• الحالة: {'✅ مفعل' if trial_settings['enabled'] else '❌ معطل'}
• المدة: {trial_settings['days']} أيام
• لمرة واحدة: {'✅ نعم' if trial_settings['one_time'] else '❌ لا'}

📈 **الإحصائيات:**
• إجمالي التجارب: {total_trials}
• التجارب النشطة: {active_trials}
• التجارب المنتهية: {expired_trials}

📋 **آخر 10 تجارب:**
"""
        
        for trial in recent_trials:
            user_id, username, first_name, start_date, end_date = trial
            status = "✅ نشط" if datetime.strptime(end_date, '%Y-%m-%d').date() >= datetime.now().date() else "❌ منتهي"
            username_display = f"@{username}" if username else "بدون يوزر"
            
            text += f"• {first_name} ({username_display}) - {start_date} إلى {end_date} - {status}\n"
        
        await update.message.reply_text(text, reply_markup=get_trial_management_keyboard())
        
    except Exception as e:
        logger.error(f"❌ خطأ في show_trial_stats: {e}")
        await update.message.reply_text("❌ حدث خطأ في عرض الإحصائيات.")

async def admin_reset_revenue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """طلب تأكيد إعادة تعيين الإيرادات"""
    try:
        stats = get_bot_stats()
        
        text = f"""
🔄 **إعادة تعيين الإيرادات**

⚠️ **تحذير:** هذه العملية لا يمكن التراجع عنها!
سيتم إعادة تعيين إيرادات البوت إلى الصفر وستبدأ الإحصائيات من جديد.

📊 **الإيرادات الحالية:**
• الاشتراكات: {stats['subscription_revenue']:,.0f} ليرة
• التوقعات: {stats['predictions_revenue']:,.0f} ليرة
• الإجمالي: {stats['subscription_revenue'] + stats['predictions_revenue']:,.0f} ليرة

❌ **بعد الإعادة:**
• ستصبح جميع الإيرادات السابقة صفراً
• سيتم احتساب الإيرادات الجديدة من الآن فصاعداً
• لا يمكن استعادة الإيرادات المحذوفة

🔒 **هل أنت متأكد من أنك تريد المتابعة؟**
        """
        
        await update.message.reply_text(
            text,
            reply_markup=get_revenue_reset_confirmation_keyboard()
        )
    except Exception as e:
        logger.error(f"❌ خطأ في admin_reset_revenue: {e}")
        await update.message.reply_text("❌ حدث خطأ في إعداد إعادة التعيين.")

async def handle_revenue_reset_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """معالجة تأكيد إعادة تعيين الإيرادات"""
    try:
        if text == "❌ إلغاء العملية":
            await update.message.reply_text(
                "✅ **تم إلغاء عملية إعادة تعيين الإيرادات**",
                reply_markup=get_admin_keyboard()
            )
            return
        
        elif text == "⚠️ نعم، إعادة تعيين الإيرادات ⚠️":
            # تنفيذ إعادة التعيين
            success = reset_revenue()
            
            if success:
                stats = get_bot_stats()
                
                await update.message.reply_text(
                    f"✅ **تم إعادة تعيين الإيرادات بنجاح!**\n\n"
                    f"🔄 **جميع الإيرادات السابقة تم مسحها:**\n"
                    f"• إيرادات الاشتراكات: {stats['subscription_revenue']:,.0f} ليرة\n"
                    f"• إيرادات التوقعات: {stats['predictions_revenue']:,.0f} ليرة\n"
                    f"• الإجمالي: {stats['subscription_revenue'] + stats['predictions_revenue']:,.0f} ليرة\n\n"
                    f"📊 **الإحصائيات الجديدة تبدأ من الصفر**\n"
                    f"⏰ **التاريخ:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                    reply_markup=get_admin_keyboard()
                )
                
                logger.info("🔄 تم إعادة تعيين الإيرادات بنجاح بواسطة الأدمن")
                
                # إرسال إشعار لجميع الأدمن
                admin_notification = f"""
🔔 **إشعار نظام:** إعادة تعيين الإيرادات

✅ **تم إعادة تعيين إيرادات البوت إلى الصفر**
👤 **بواسطة الأدمن:** {update.effective_user.first_name}
🆔 **User ID:** {update.effective_user.id}
⏰ **الوقت:** {datetime.now().strftime('%Y-%m-%d %H:%M')}

📊 **جميع الإيرادات السابقة تم مسحها وبدأت الإحصائيات من جديد.**
                """
                
                await notify_admins(context, admin_notification, None, "system")
                
            else:
                await update.message.reply_text(
                    "❌ **فشل في إعادة تعيين الإيرادات**\n\n"
                    "يرجى المحاولة مرة أخرى أو التحقق من سجلات النظام.",
                    reply_markup=get_admin_keyboard()
                )
        
    except Exception as e:
        logger.error(f"❌ خطأ في handle_revenue_reset_confirmation: {e}")
        await update.message.reply_text(
            "❌ حدث خطأ أثناء إعادة تعيين الإيرادات",
            reply_markup=get_admin_keyboard()
        )

async def admin_gift_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض واجهة هدايا الاشتراكات"""
    try:
        text = """
🎁 **نظام هدايا الاشتراكات**

اختر نوع الهدية التي تريد منحها:

• 🎁 **إضافة أيام اشتراك**: أضف أيام اشتراك محددة لأي مستخدم
• 🎁 **3 أيام تجريبية**: امنح 3 أيام تجريبية لمستخدم غير مشترك

⚠️ **ملاحظة:** يمكنك استخدام هذه الميزة لمكافأة المستخدمين المميزين أو تجربة جديدة.
        """
        
        await update.message.reply_text(text, reply_markup=get_gift_subscription_keyboard())
    except Exception as e:
        logger.error(f"❌ خطأ في admin_gift_subscriptions: {e}")
        await update.message.reply_text("❌ حدث خطأ في عرض واجهة الهدايا.")

async def admin_add_subscription_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء عملية إضافة أيام اشتراك"""
    try:
        context.user_data['admin_action'] = 'add_subscription_days_user'
        await update.message.reply_text(
            "🎁 **إضافة أيام اشتراك**\n\n"
            "أرسل معرف المستخدم (User ID) الذي تريد إضافة أيام له:\n"
            "• يمكنك الحصول على الـ ID من قائمة إدارة المستخدمين\n"
            "• أو استخدام الأمر /info_123 لمعلومات المستخدم\n\n"
            "❌ للإلغاء: /cancel",
            reply_markup=ReplyKeyboardMarkup([["🏠 START"]], resize_keyboard=True)
        )
    except Exception as e:
        logger.error(f"❌ خطأ في admin_add_subscription_days: {e}")
        await update.message.reply_text("❌ حدث خطأ في إعداد إضافة الأيام.")

async def admin_give_trial_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء عملية منح 3 أيام تجريبية"""
    try:
        context.user_data['admin_action'] = 'give_trial_days_user'
        await update.message.reply_text(
            "🎁 **3 أيام تجريبية**\n\n"
            "أرسل معرف المستخدم (User ID) الذي تريد منحه 3 أيام تجريبية:\n"
            "• يمكنك الحصول على الـ ID من قائمة إدارة المستخدمين\n"
            "• هذه الهدية للمستخدمين الجدد أو غير المشتركين\n\n"
            "❌ للإلغاء: /cancel",
            reply_markup=ReplyKeyboardMarkup([["🏠 START"]], resize_keyboard=True)
        )
    except Exception as e:
        logger.error(f"❌ خطأ في admin_give_trial_days: {e}")
        await update.message.reply_text("❌ حدث خطأ في إعداد الهدية التجريبية.")

async def handle_delete_special_prediction(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """معالجة حذف التوقع الخاص"""
    try:
        # استخراج الرقم من النص
        pred_id_text = text.replace("🗑️ حذف التوقع ", "").strip()
        
        # استخدام دالة استخراج الأرقام الآمنة
        pred_id = extract_prediction_number(pred_id_text)
        
        if pred_id is None:
            await update.message.reply_text(
                "❌ **رقم التوقع غير صحيح**\n\n"
                "يجب أن يحتوي الزر على رقم صحيح صالح.\n"
                "مثال: `🗑️ حذف التوقع 123`",
                reply_markup=get_admin_keyboard()
            )
            return
        
        # تنفيذ عملية الحذف
        success = delete_special_prediction(pred_id)
        
        if success:
            await update.message.reply_text(
                f"✅ **تم حذف التوقع الخاص رقم {pred_id} بنجاح**",
                reply_markup=get_admin_keyboard()
            )
            logger.info(f"✅ تم حذف التوقع الخاص رقم {pred_id}")
        else:
            await update.message.reply_text(
                f"❌ **فشل في حذف التوقع الخاص رقم {pred_id}**\n"
                "قد يكون الرقم غير موجود.",
                reply_markup=get_admin_keyboard()
            )
            
    except Exception as e:
        logger.error(f"❌ خطأ في handle_delete_special_prediction: {e}")
        await update.message.reply_text(
            "❌ حدث خطأ أثناء حذف التوقع الخاص",
            reply_markup=get_admin_keyboard()
        )

async def handle_delete_daily_prediction(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """معالجة حذف التوقع اليومي"""
    try:
        # استخراج الرقم من النص
        pred_id_text = text.replace("🗑️ حذف التوقع اليومي ", "").strip()
        
        # استخدام دالة استخراج الأرقام الآمنة
        pred_id = extract_prediction_number(pred_id_text)
        
        if pred_id is None:
            await update.message.reply_text(
                "❌ **رقم التوقع اليومي غير صحيح**\n\n"
                "يجب أن يحتوي الزر على رقم صحيح صالح.\n"
                "مثال: `🗑️ حذف التوقع اليومي 456`",
                reply_markup=get_admin_keyboard()
            )
            return
        
        # تنفيذ عملية الحذف
        success = delete_daily_prediction(pred_id)
        
        if success:
            await update.message.reply_text(
                f"✅ **تم حذف التوقع اليومي رقم {pred_id} بنجاح**",
                reply_markup=get_admin_keyboard()
            )
            logger.info(f"✅ تم حذف التوقع اليومي رقم {pred_id}")
        else:
            await update.message.reply_text(
                f"❌ **فشل في حذف التوقع اليومي رقم {pred_id}**\n"
                "قد يكون الرقم غير موجود.",
                reply_markup=get_admin_keyboard()
            )
            
    except Exception as e:
        logger.error(f"❌ خطأ في handle_delete_daily_prediction: {e}")
        await update.message.reply_text(
            "❌ حدث خطأ أثناء حذف التوقع اليومي",
            reply_markup=get_admin_keyboard()
        )

async def admin_delete_announcements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض واجهة حذف الإعلانات"""
    try:
        announcements = get_recent_announcements(10)
        
        if not announcements:
            await update.message.reply_text("📭 **لا توجد إعلانات متاحة للحذف**", reply_markup=get_admin_keyboard())
            return
        
        text = "🗑️ **اختر الإعلان الذي تريد حذفه:**\n\n"
        keyboard = []
        
        for ann in announcements:
            ann_id, ann_text, ann_type, sent_count, total_count, created_at = ann
            
            # تقصير النص للمعاينة
            preview = ann_text[:50] + "..." if len(ann_text) > 50 else ann_text
            date_str = created_at.split()[0] if created_at else "غير معروف"
            
            text += f"• {ann_id}: {preview}\n"
            text += f"  📊 {sent_count}/{total_count} | {ann_type} | {date_str}\n\n"
            
            keyboard.append([f"🗑️ حذف الإعلان {ann_id}"])
        
        keyboard.append(["🔙 رجوع للوحة الأدمن"])
        
        await update.message.reply_text(
            text,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
    except Exception as e:
        logger.error(f"❌ خطأ في admin_delete_announcements: {e}")
        await update.message.reply_text("❌ حدث خطأ في عرض الإعلانات للحذف.")

async def handle_delete_announcement(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """معالجة حذف الإعلان"""
    try:
        # استخراج الرقم من النص
        ann_id_text = text.replace("🗑️ حذف الإعلان ", "").strip()
        
        # استخدام دالة استخراج الأرقام الآمنة
        ann_id = extract_prediction_number(ann_id_text)
        
        if ann_id is None:
            await update.message.reply_text(
                "❌ **رقم الإعلان غير صحيح**\n\n"
                "يجب أن يحتوي الزر على رقم صحيح صالح.\n"
                "مثال: `🗑️ حذف الإعلان 123`",
                reply_markup=get_admin_keyboard()
            )
            return
        
        # تنفيذ عملية الحذف
        success = delete_announcement(ann_id)
        
        if success:
            await update.message.reply_text(
                f"✅ **تم حذف الإعلان رقم {ann_id} بنجاح**\n\n"
                f"📝 **ملاحظة:** تم حذف الإعلان من قاعدة البيانات ولن يتم إرساله لأي مستخدم جديد.",
                reply_markup=get_admin_keyboard()
            )
            logger.info(f"✅ تم حذف الإعلان رقم {ann_id}")
        else:
            await update.message.reply_text(
                f"❌ **فشل في حذف الإعلان رقم {ann_id}**\n"
                "قد يكون الرقم غير موجود.",
                reply_markup=get_admin_keyboard()
            )
            
    except Exception as e:
        logger.error(f"❌ خطأ في handle_delete_announcement: {e}")
        await update.message.reply_text(
            "❌ حدث خطأ أثناء حذف الإعلان",
            reply_markup=get_admin_keyboard()
        )

async def admin_edit_prices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعديل الأسعار من قبل الأدمن"""
    try:
        text = f"""
💰 **تعديل الأسعار الحالية**

📊 **الأسعار الحالية:**
• الاشتراك الشهري: {SUBSCRIPTION_SETTINGS['monthly_price']:,} ليرة
• التوقع الخاص: {SUBSCRIPTION_SETTINGS['prediction_price']:,} ليرة

📝 **لتعديل الأسعار، استخدم الأوامر التالية:**

• لتعديل سعر الاشتراك:
  `/set_monthly_price 80000`

• لتعديل سعر التوقع الخاص:
  `/set_prediction_price 30000`

⚠️ **ملاحظة:** استبدل الأرقام بالأرقام الجديدة التي تريدها (بدون فواصل)
        """
        
        await update.message.reply_text(text, reply_markup=get_admin_keyboard())
    except Exception as e:
        logger.error(f"❌ خطأ في admin_edit_prices: {e}")
        await update.message.reply_text("❌ حدث خطأ في عرض تعديل الأسعار.")

async def admin_delete_daily_predictions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف التوقعات اليومية"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, prediction_text, image_file_id, created_at 
            FROM daily_predictions 
            ORDER BY created_at DESC LIMIT 10
        ''')
        daily_predictions = cursor.fetchall()
        conn.close()
        
        if not daily_predictions:
            await update.message.reply_text("📭 **لا توجد توقعات يومية لحذفها**", reply_markup=get_admin_keyboard())
            return
        
        text = "🗑️ **اختر التوقع اليومي لحذفه:**\n\n"
        keyboard = []
        
        for pred in daily_predictions:
            pred_id, pred_text, _, created_at = pred
            preview = pred_text[:50] + "..." if pred_text and len(pred_text) > 50 else (pred_text or "بدون نص")
            time_str = created_at.split()[1][:5] if created_at and ' ' in str(created_at) else str(created_at)[:10]
            text += f"• {pred_id}: {preview} ({time_str})\n"
            keyboard.append([f"🗑️ حذف التوقع اليومي {pred_id}"])
        
        keyboard.append(["🏠 START"])
        
        await update.message.reply_text(
            text,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
    except Exception as e:
        logger.error(f"❌ خطأ في admin_delete_daily_predictions: {e}")
        await update.message.reply_text("❌ حدث خطأ في عرض التوقعات اليومية للحذف.")

async def handle_admin_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """معالجة تأكيد الإرسال من الأدمن - النسخة المحسنة"""
    try:
        admin_action = context.user_data.get('pending_admin_action')
        
        if not admin_action:
            await update.message.reply_text("❌ **لا توجد عملية إرسال معلقة**", reply_markup=get_admin_keyboard())
            return
        
        if text == "❌ لا، إلغاء الإرسال":
            context.user_data.pop('pending_admin_action', None)
            context.user_data.pop('pending_message_data', None)
            await update.message.reply_text("✅ **تم إلغاء عملية الإرسال**", reply_markup=get_admin_keyboard())
            return
        
        # إذا كان التأكيد بنعم
        message_data = context.user_data.get('pending_message_data', {})
        message_text = message_data.get('text', '')
        image_file_id = message_data.get('image_file_id')
        action_type = admin_action
        
        if action_type == 'daily_pred':
            # إرسال التوقعات اليومية للمستخدمين النشطين فقط
            add_daily_prediction(message_text, image_file_id)
            sent_count = await send_message_to_active_users(context, message_text, image_file_id, "🎯 توقعات اليوم")
            
            await update.message.reply_text(
                f"✅ **تم إرسال التوقعات اليومية**\n\n"
                f"📤 **تم الإرسال لـ {sent_count} مستخدم نشط**\n"
                f"💡 *ملاحظة: التوقعات اليومية ترسل للمشتركين النشطين فقط*",
                reply_markup=get_admin_keyboard()
            )
            
        elif action_type == 'special_pred':
            # إضافة التوقع الخاص الجديد إلى قاعدة البيانات
            title = message_data.get('title', '')
            description = message_data.get('description', '')
            content = message_data.get('content', '')
            image_file_id = message_data.get('image_file_id')
            
            add_special_prediction(title, description, content, image_file_id)
            
            await update.message.reply_text(
                f"✅ **تم إضافة التوقع الخاص بنجاح**\n\n"
                f"🏷️ **العنوان:** {title}\n"
                f"📝 **الوصف:** {description}\n"
                f"📄 **تم حفظ المحتوى في قاعدة البيانات**\n\n"
                f"📋 **سيظهر التوقع في قائمة التوقعات الخاصة للمستخدمين**",
                reply_markup=get_admin_keyboard()
            )
            
        elif action_type == 'announcement':
            # ✅ استخدام النظام الجديد الذي يحفظ الإعلانات للمستخدمين غير المتصلين
            sent_count = await send_message_to_all_users_with_fallback(context, message_text, image_file_id, "📢 إعلان")
            
            # الحصول على إحصائيات الإعلان
            total_users = get_total_active_users()
            
            await update.message.reply_text(
                f"✅ **تم إرسال وحفظ الإعلان**\n\n"
                f"📤 **تم الإرسال الفوري لـ {sent_count} مستخدم**\n"
                f"💾 **تم حفظ الإعلان لـ {total_users - sent_count} مستخدم غير متصل**\n"
                f"👥 **الإجمالي:** {total_users} مستخدم\n\n"
                f"📨 **سيتم إرسال الإعلان تلقائياً للمستخدمين عندما يعودون للاتصال**",
                reply_markup=get_admin_keyboard()
            )
        
        # تنظيف البيانات المؤقتة
        context.user_data.pop('pending_admin_action', None)
        context.user_data.pop('pending_message_data', None)
        
    except Exception as e:
        logger.error(f"❌ خطأ في handle_admin_confirmation: {e}")
        await update.message.reply_text("❌ حدث خطأ في معالجة التأكيد.", reply_markup=get_admin_keyboard())

async def show_admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إحصائيات مفصلة للأدمن"""
    try:
        stats = get_bot_stats()
        pending_subs = len(get_pending_subscriptions())
        pending_preds = len(get_pending_predictions())
        
        stats_text = f"""
📊 **التقارير التفصيلية**

👥 **المستخدمين:**
• الإجمالي: {stats['total_users']}
• النشطين: {stats['active_subscribers']}
• المحظورين: {stats['banned_users']}
• النسبة: {(stats['active_subscribers']/stats['total_users']*100) if stats['total_users'] > 0 else 0:.1f}%

💰 **الإيرادات:**
• الاشتراكات: {stats['subscription_revenue']:,.0f} ليرة
• التوقعات: {stats['predictions_revenue']:,.0f} ليرة
• الإجمالي: {stats['subscription_revenue'] + stats['predictions_revenue']:,.0f} ليرة

📋 **الطلبات المعلقة:**
• اشتراكات: {pending_subs}
• توقعات: {pending_preds}

⏰ **آخر تحديث:** {datetime.now().strftime('%Y-%m-%d %H:%M')}
        """
        
        await update.message.reply_text(stats_text, reply_markup=get_admin_keyboard())
    except Exception as e:
        logger.error(f"❌ خطأ في show_admin_stats: {e}")
        await update.message.reply_text("❌ حدث خطأ في عرض الإحصائيات.")

async def show_admin_pending_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض الطلبات المعلقة للأدمن"""
    try:
        pending_subs = get_pending_subscriptions()
        pending_preds = get_pending_predictions()
        
        if not pending_subs and not pending_preds:
            await update.message.reply_text("✅ **لا توجد طلبات معلقة**", reply_markup=get_admin_keyboard())
            return
        
        text = "📋 **الطلبات المعلقة**\n\n"
        
        if pending_subs:
            text += "🔔 **الاشتراكات المعلقة:**\n"
            for transaction in pending_subs[:5]:
                method_info = PAYMENT_SETTINGS.get(transaction[4], {'name': transaction[4]})
                text += f"• ID: {transaction[0]} | {transaction[7]} | {transaction[3]:,} ليرة\n"
                text += f"  👤 @{transaction[8]} | {transaction[9]}\n"
                text += f"  📱 {method_info['name']} | 🔢 {transaction[2]}\n\n"
        
        if pending_preds:
            text += "🎯 **التوقعات المعلقة:**\n"
            for transaction in pending_preds[:5]:
                text += f"• ID: {transaction[0]} | {transaction[7]} | {transaction[3]:,} ليرة\n"
                text += f"  👤 @{transaction[8]} | {transaction[9]}\n"
                text += f"  📝 {transaction[6] or 'بدون طلب'}\n\n"
        
        if len(pending_subs) > 5 or len(pending_preds) > 5:
            text += f"📎 *عرض {min(5, len(pending_subs))} من {len(pending_subs)} اشتراك، و {min(5, len(pending_preds))} من {len(pending_preds)} توقع*"
        
        await update.message.reply_text(text, reply_markup=get_admin_keyboard())
    except Exception as e:
        logger.error(f"❌ خطأ في show_admin_pending_requests: {e}")
        await update.message.reply_text("❌ حدث خطأ في عرض الطلبات المعلقة.")

async def admin_add_daily_predictions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة توقعات يومية من الأدمن"""
    try:
        context.user_data['admin_action'] = 'add_daily_pred'
        await update.message.reply_text(
            "📝 **إرسال توقعات اليوم**\n\n"
            "أرسل نص التوقعات اليومية:\n"
            "• يمكنك إرسال صورة مع التوقعات كـ caption\n"
            "• أو إرسال النص فقط\n\n"
            "⚠️ **ملاحظة:** سيتم إرسال التوقعات للمستخدمين النشطين فقط\n\n"
            "❌ للإلغاء: /cancel",
            reply_markup=ReplyKeyboardMarkup([["🏠 START"]], resize_keyboard=True)
        )
    except Exception as e:
        logger.error(f"❌ خطأ في admin_add_daily_predictions: {e}")
        await update.message.reply_text("❌ حدث خطأ في إعداد إرسال التوقعات.")

async def admin_add_special_prediction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة توقع خاص من الأدمن"""
    try:
        context.user_data['admin_action'] = 'add_special_pred_title'
        await update.message.reply_text(
            "🔮 **إرسال توقع خاص جديد**\n\n"
            "📝 **الخطوة 1/3:** أرسل عنوان التوقع الخاص:\n"
            "• مثال: 'توقع مباراة ريال مدريد ضد برشلونة'\n"
            "• يجب أن يكون العنوان واضحاً وجذاباً\n\n"
            "❌ للإلغاء: /cancel",
            reply_markup=ReplyKeyboardMarkup([["🏠 START"]], resize_keyboard=True)
        )
    except Exception as e:
        logger.error(f"❌ خطأ في admin_add_special_prediction: {e}")
        await update.message.reply_text("❌ حدث خطأ في إعداد إرسال التوقع الخاص.")

async def admin_send_announcement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إرسال إعلان لجميع المستخدمين"""
    try:
        context.user_data['admin_action'] = 'send_announcement'
        await update.message.reply_text(
            "📢 **إرسال إعلان لجميع المستخدمين**\n\n"
            "أرسل نص الإعلان:\n"
            "• يمكنك إرسال صورة مع الإعلان كـ caption\n"
            "• أو إرسال النص فقط\n\n"
            "⚠️ **ملاحظة:** سيتم إرسال هذا الإعلان لجميع المستخدمين (بما فيهم غير النشطين)\n\n"
            "❌ للإلغاء: /cancel",
            reply_markup=ReplyKeyboardMarkup([["🏠 START"]], resize_keyboard=True)
        )
    except Exception as e:
        logger.error(f"❌ خطأ في admin_send_announcement: {e}")
        await update.message.reply_text("❌ حدث خطأ في إعداد إرسال الإعلان.")

async def admin_delete_special_predictions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف التوقعات الخاصة"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, prediction_title, prediction_description, created_at 
            FROM special_predictions 
            ORDER BY created_at DESC LIMIT 10
        ''')
        special_predictions = cursor.fetchall()
        conn.close()
        
        if not special_predictions:
            await update.message.reply_text("📭 **لا توجد توقعات خاصة لحذفها**", reply_markup=get_admin_keyboard())
            return
        
        text = "🗑️ **اختر التوقع الخاص لحذفه:**\n\n"
        keyboard = []
        
        for pred in special_predictions:
            pred_id, title, description, created_at = pred
            preview = title[:50] + "..." if title and len(title) > 50 else (title or "بدون عنوان")
            time_str = created_at.split()[0] if created_at else "غير معروف"
            text += f"• {pred_id}: {preview} ({time_str})\n"
            keyboard.append([f"🗑️ حذف التوقع {pred_id}"])
        
        keyboard.append(["🏠 START"])
        
        await update.message.reply_text(
            text,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
    except Exception as e:
        logger.error(f"❌ خطأ في admin_delete_special_predictions: {e}")
        await update.message.reply_text("❌ حدث خطأ في عرض التوقعات للحذف.")

async def admin_manage_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إدارة المستخدمين"""
    try:
        users = get_all_users(limit=20)
        
        if not users:
            await update.message.reply_text("📭 **لا يوجد مستخدمين**", reply_markup=get_admin_keyboard())
            return
        
        text = "👥 **قائمة المستخدمين**\n\n"
        
        for user in users:
            user_id, username, first_name, expiry, is_banned, created_at = user
            status = "🚫" if is_banned else "✅"
            username_display = f"@{username}" if username else "بدون يوزر"
            
            text += f"{status} **{first_name}** ({username_display})\n"
            text += f"🆔: {user_id} | 📅: {created_at.split()[0]}\n"
            
            if expiry:
                expiry_date = datetime.strptime(expiry, '%Y-%m-%d').date()
                remaining = (expiry_date - datetime.now().date()).days
                text += f"📅 ينتهي بعد: {remaining} يوم\n"
            
            text += f"🔧 `/ban_{user_id}` | `/unban_{user_id}` | `/info_{user_id}`\n\n"
        
        text += "📝 **استخدم الأوامر:**\n"
        text += "• `/ban_123` - حظر المستخدم\n"
        text += "• `/unban_123` - فك حظر المستخدم\n"
        text += "• `/info_123` - معلومات المستخدم\n"
        text += "• **🔍 بحث عن مستخدم** - للبحث بالاسم أو اليوزرنيم"
        
        keyboard = [
            ["🔍 بحث عن مستخدم", "📊 تحديث القائمة"],
            ["🏠 START"]
        ]
        
        await update.message.reply_text(
            text,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
    except Exception as e:
        logger.error(f"❌ خطأ في admin_manage_users: {e}")
        await update.message.reply_text("❌ حدث خطأ في إدارة المستخدمين.")

async def admin_search_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بحث عن مستخدم"""
    try:
        context.user_data['admin_action'] = 'search_user'
        await update.message.reply_text(
            "🔍 **بحث عن مستخدم**\n\n"
            "أرسل اسم المستخدم أو اليوزرنيم للبحث:\n"
            "• يمكنك البحث بالاسم الأول\n"
            "• أو البحث باليوزرنيم (مع أو بدون @)\n\n"
            "❌ للإلغاء: /cancel",
            reply_markup=ReplyKeyboardMarkup([["🏠 START"]], resize_keyboard=True)
        )
    except Exception as e:
        logger.error(f"❌ خطأ في admin_search_user: {e}")
        await update.message.reply_text("❌ حدث خطأ في إعداد البحث.")

async def admin_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إعدادات الأدمن"""
    try:
        settings_text = f"""
⚙️ **إعدادات البوت**

💰 **الأسعار الحالية:**
• الاشتراك الشهري: {SUBSCRIPTION_SETTINGS['monthly_price']:,} ليرة
• التوقع الخاص: {SUBSCRIPTION_SETTINGS['prediction_price']:,} ليرة

📱 **بوابات الدفع:**
• سيرتل كاش: {PAYMENT_SETTINGS['syriatel']['account_number']}
• شام كاش: {PAYMENT_SETTINGS['sham']['account_number']}
• ام تي ان كاش: {PAYMENT_SETTINGS['mtn']['account_number']}

👑 **الأدمن الحالي:** {', '.join(ADMIN_USERNAMES)}
        """
        
        await update.message.reply_text(settings_text, reply_markup=get_admin_keyboard())
    except Exception as e:
        logger.error(f"❌ خطأ في admin_settings: {e}")
        await update.message.reply_text("❌ حدث خطأ في عرض الإعدادات.")

async def admin_announcement_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إحصائيات الإعلانات المعلقة"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, announcement_type, target_users, sent_count, total_count, created_at
            FROM pending_announcements 
            ORDER BY created_at DESC LIMIT 10
        ''')
        announcements = cursor.fetchall()
        
        if not announcements:
            await update.message.reply_text("📭 **لا توجد إعلانات معلقة**", reply_markup=get_admin_keyboard())
            return
        
        text = "📊 **إحصائيات الإعلانات المعلقة**\n\n"
        
        for ann in announcements:
            ann_id, ann_type, target, sent, total, created = ann
            pending = total - sent
            percentage = (sent / total * 100) if total > 0 else 0
            
            text += f"🆔 **{ann_id}** - {ann_type}\n"
            text += f"📅 {created[:16]}\n"
            text += f"📤 تم الإرسال: {sent}/{total} ({percentage:.1f}%)\n"
            text += f"⏳ في الانتظار: {pending} مستخدم\n\n"
        
        text += "💡 **ملاحظة:** الإعلانات المعلقة ترسل تلقائياً عندما يعود المستخدمون للاتصال"
        
        await update.message.reply_text(text, reply_markup=get_admin_keyboard())
        
    except Exception as e:
        logger.error(f"❌ خطأ في admin_announcement_stats: {e}")
        await update.message.reply_text("❌ حدث خطأ في عرض إحصائيات الإعلانات.")

async def handle_admin_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """معالجة محادثات الأدمن مع إضافة النظام التجريبي"""
    try:
        admin_action = context.user_data.get('admin_action')
        
        if text == "/cancel":
            context.user_data.pop('admin_action', None)
            context.user_data.pop('gift_data', None)
            context.user_data.pop('special_prediction_data', None)
            await show_admin_dashboard(update, context)
            return
        
        # ⬇️⬇️⬇️ إضافة الحالات الجديدة للهدايا ⬇️⬇️⬇️
        
        elif admin_action == 'add_subscription_days_user':
            # معالجة إدخال معرف المستخدم لإضافة الأيام
            try:
                user_id = int(text.strip())
                user = get_user(user_id)
                
                if not user:
                    await update.message.reply_text(
                        "❌ **لم يتم العثور على المستخدم**\n\n"
                        "يرجى التأكد من معرف المستخدم والمحاولة مرة أخرى.",
                        reply_markup=get_gift_subscription_keyboard()
                    )
                    context.user_data.pop('admin_action', None)
                    return
                
                # حفظ بيانات الهدية مؤقتاً
                context.user_data['gift_data'] = {
                    'user_id': user_id,
                    'username': user[1] or 'بدون يوزر',
                    'first_name': user[2]
                }
                context.user_data['admin_action'] = 'add_subscription_days_count'
                
                await update.message.reply_text(
                    f"✅ **تم العثور على المستخدم:** {user[2]} (@{user[1] or 'بدون يوزر'})\n\n"
                    f"🔢 **الآن أرسل عدد الأيام التي تريد إضافتها:**\n"
                    f"• أدخل رقماً فقط (مثال: 30)\n"
                    f"• يمكنك إضافة أي عدد من الأيام\n\n"
                    f"❌ للإلغاء: /cancel"
                )
                
            except ValueError:
                await update.message.reply_text(
                    "❌ **معرف المستخدم غير صحيح**\n\n"
                    "يرجى إدخال رقم صحيح فقط (مثال: 123456789)",
                    reply_markup=get_gift_subscription_keyboard()
                )
        
        elif admin_action == 'add_subscription_days_count':
            # معالجة إدخال عدد الأيام
            try:
                days = int(text.strip())
                
                if days <= 0:
                    await update.message.reply_text(
                        "❌ **عدد الأيام يجب أن يكون أكبر من صفر**",
                        reply_markup=get_gift_subscription_keyboard()
                    )
                    return
                
                gift_data = context.user_data.get('gift_data', {})
                user_id = gift_data.get('user_id')
                
                if not user_id:
                    await update.message.reply_text(
                        "❌ **حدث خطأ في البيانات**",
                        reply_markup=get_gift_subscription_keyboard()
                    )
                    context.user_data.clear()
                    return
                
                # تطبيق الإضافة
                update_subscription(user_id, days)
                
                # إرسال إشعار للمستخدم
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"🎉 **مبروك! حصلت على هدية اشتراك** 🎁\n\n"
                             f"✅ **تم إضافة {days} يوم لاشتراكك**\n\n"
                             f"📅 **يمكنك الآن الاستمتاع بجميع المميزات:**\n"
                             f"• مشاهدة التوقعات اليومية 📊\n"
                             f"• الوصول للتوقعات الخاصة 🔮\n"
                             f"• تحديثات مستمرة 🚀\n\n"
                             f"💡 **استخدم زر 🏠 START لمشاهدة آخر التوقعات!**\n\n"
                             f"شكراً لكونك معنا! 🤝"
                    )
                except Exception as e:
                    logger.error(f"❌ فشل في إرسال إشعار للمستخدم {user_id}: {e}")
                
                # إرسال تأكيد للأدمن
                await update.message.reply_text(
                    f"✅ **تمت العملية بنجاح!**\n\n"
                    f"👤 **المستخدم:** {gift_data.get('first_name')} (@{gift_data.get('username')})\n"
                    f"🆔 **ID:** {user_id}\n"
                    f"📅 **تم الإضافة:** {days} يوم\n"
                    f"🎁 **نوع الهدية:** إضافة أيام اشتراك\n\n"
                    f"💫 تم إرسال إشعار للمستخدم بالهدية.",
                    reply_markup=get_admin_keyboard()
                )
                
                logger.info(f"🎁 تم إضافة {days} يوم اشتراك للمستخدم {user_id} بواسطة الأدمن")
                
                # تنظيف البيانات المؤقتة
                context.user_data.clear()
                
            except ValueError:
                await update.message.reply_text(
                    "❌ **عدد الأيام غير صحيح**\n\n"
                    "يرجى إدخال رقم صحيح فقط (مثال: 30)",
                    reply_markup=get_gift_subscription_keyboard()
                )
        
        elif admin_action == 'give_trial_days_user':
            # معالجة إدخال معرف المستخدم للهدية التجريبية
            try:
                user_id = int(text.strip())
                user = get_user(user_id)
                
                if not user:
                    await update.message.reply_text(
                        "❌ **لم يتم العثور على المستخدم**\n\n"
                        "يرجى التأكد من معرف المستخدم والمحاولة مرة أخرى.",
                        reply_markup=get_gift_subscription_keyboard()
                    )
                    context.user_data.pop('admin_action', None)
                    return
                
                # التحقق من حالة الاشتراك الحالية
                status = get_user_subscription_status(user_id)
                
                if status == 'active':
                    await update.message.reply_text(
                        "⚠️ **المستخدم لديه اشتراك نشط بالفعل**\n\n"
                        "لا يمكن منح هدية تجريبية لمستخدم مشترك.\n"
                        "يمكنك استخدام خيار 'إضافة أيام اشتراك' بدلاً من ذلك.",
                        reply_markup=get_gift_subscription_keyboard()
                    )
                    context.user_data.pop('admin_action', None)
                    return
                
                # تطبيق الهدية التجريبية (3 أيام)
                update_subscription(user_id, 3)
                
                # إرسال إشعار للمستخدم
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"🎉 **أهلاً بك! حصلت على هدية تجريبية مجانية** 🎁\n\n"
                             f"✅ **تم تفعيل 3 أيام تجريبية مجانية لحسابك**\n\n"
                             f"📅 **خلال هذه الفترة يمكنك:**\n"
                             f"• مشاهدة جميع التوقعات اليومية 📊\n"
                             f"• تجربة التوقعات الخاصة 🔮\n"
                             f"• الاستفادة من جميع مميزات البوت 🚀\n\n"
                             f"💡 **استخدم زر 🏠 START لبدء مشاهدة التوقعات!**\n\n"
                             f"نتمنى لك تجربة ممتعة وأرباحاً وفيرة! 🏆"
                    )
                except Exception as e:
                    logger.error(f"❌ فشل في إرسال إشعار للمستخدم {user_id}: {e}")
                
                # إرسال تأكيد للأدمن
                await update.message.reply_text(
                    f"✅ **تمت العملية بنجاح!**\n\n"
                    f"👤 **المستخدم:** {user[2]} (@{user[1] or 'بدون يوزر'})\n"
                    f"🆔 **ID:** {user_id}\n"
                    f"📅 **مدة الهدية:** 3 أيام تجريبية\n"
                    f"🎁 **نوع الهدية:** تجريبية مجانية\n\n"
                    f"💫 تم إرسال إشعار للمستخدم بالهدية التجريبية.",
                    reply_markup=get_admin_keyboard()
                )
                
                logger.info(f"🎁 تم منح 3 أيام تجريبية للمستخدم {user_id} بواسطة الأدمن")
                
                # تنظيف البيانات المؤقتة
                context.user_data.clear()
                
            except ValueError:
                await update.message.reply_text(
                    "❌ **معرف المستخدم غير صحيح**\n\n"
                    "يرجى إدخال رقم صحيح فقط (مثال: 123456789)",
                    reply_markup=get_gift_subscription_keyboard()
                )
        
        # ⬆️⬆️⬆️ نهاية الإضافات الجديدة ⬆️⬆️⬆️
        
        # ⬇️⬇️⬇️ إضافة معالجة تعديل مدة التجربة ⬇️⬇️⬇️
        elif admin_action == 'edit_trial_days':
            try:
                days = int(text.strip())
                
                if days <= 0:
                    await update.message.reply_text(
                        "❌ **عدد الأيام يجب أن يكون أكبر من صفر**",
                        reply_markup=get_trial_management_keyboard()
                    )
                    return
                
                if days > 365:
                    await update.message.reply_text(
                        "❌ **عدد الأيام كبير جداً (الحد الأقصى 365 يوم)**",
                        reply_markup=get_trial_management_keyboard()
                    )
                    return
                
                update_trial_setting('days', str(days))
                
                await update.message.reply_text(
                    f"✅ **تم تحديث مدة التجربة إلى {days} أيام**\n\n"
                    f"سيتم تطبيق المدة الجديدة على جميع التجارب المستقبلية.",
                    reply_markup=get_trial_management_keyboard()
                )
                
                context.user_data.pop('admin_action', None)
                
            except ValueError:
                await update.message.reply_text(
                    "❌ **عدد الأيام غير صحيح**\n\n"
                    "يرجى إدخال رقم صحيح فقط (مثال: 7)",
                    reply_markup=get_trial_management_keyboard()
                )
        # ⬆️⬆️⬆️ نهاية الإضافة ⬆️⬆️⬆️
        
        elif admin_action == 'add_special_pred_title':
            # حفظ العنوان والمضي للخطوة التالية
            context.user_data['special_prediction_data'] = {
                'title': text
            }
            context.user_data['admin_action'] = 'add_special_pred_description'
            
            await update.message.reply_text(
                "📝 **الخطوة 2/3:** أرسل وصف التوقع الخاص:\n"
                "• وصف مختصر وجذاب للتوقع\n"
                "• مثال: 'تحليل مفصل مع إحصائيات متقدمة وتوقعات دقيقة'\n"
                "• هذا الوصف سيراه المستخدمون قبل الشراء\n\n"
                "❌ للإلغاء: /cancel"
            )
            
        elif admin_action == 'add_special_pred_description':
            # حفظ الوصف والمضي للخطوة التالية
            context.user_data['special_prediction_data']['description'] = text
            context.user_data['admin_action'] = 'add_special_pred_content'
            
            await update.message.reply_text(
                "📝 **الخطوة 3/3:** أرسل محتوى التوقع الخاص:\n"
                "• هذا هو المحتوى الحقيقي الذي سيراه المشتري بعد الشراء\n"
                "• يمكنك إرسال نص فقط أو نص مع صورة\n"
                "• المحتوى يجب أن يكون تفصيلياً وقيمياً\n\n"
                "❌ للإلغاء: /cancel"
            )
            
        elif admin_action == 'add_special_pred_content':
            # معالجة محتوى التوقع الخاص (نص أو صورة مع نص)
            special_data = context.user_data.get('special_prediction_data', {})
            title = special_data.get('title', '')
            description = special_data.get('description', '')
            
            if update.message.photo:
                photo = update.message.photo[-1]
                content_text = update.message.caption or ""
                image_file_id = photo.file_id  # ✅ حفظ file_id بدلاً من البيانات الثنائية
                
                # حفظ البيانات مؤقتاً وطلب التأكيد
                context.user_data['pending_message_data'] = {
                    'title': title,
                    'description': description,
                    'content': content_text,
                    'image_file_id': image_file_id
                }
                context.user_data['pending_admin_action'] = 'special_pred'
                
                preview_text = f"""
📋 **معاينة التوقع الخاص:**

🏷️ **العنوان:** {title}
📝 **الوصف:** {description}
📄 **المحتوى:** {content_text if content_text else "📸 صورة بدون نص"}

🖼️ *مرفق مع الصورة*

⚠️ **هل تريد تأكيد الإضافة؟**
                """
                
                if content_text:
                    await update.message.reply_text(
                        preview_text,
                        reply_markup=get_confirmation_keyboard()
                    )
                else:
                    await update.message.reply_photo(
                        photo=image_file_id,
                        caption=preview_text,
                        reply_markup=get_confirmation_keyboard()
                    )
                    
            else:
                # إذا كان نص فقط
                content_text = text
                
                if not content_text.strip():
                    await update.message.reply_text(
                        "❌ **يرجى إرسال محتوى التوقع**\n\n"
                        "أرسل المحتوى الحقيقي للتوقع الخاص، أو أرسل /cancel للإلغاء",
                        reply_markup=ReplyKeyboardMarkup([["🏠 START"]], resize_keyboard=True)
                    )
                    return
                
                # حفظ البيانات مؤقتاً وطلب التأكيد
                context.user_data['pending_message_data'] = {
                    'title': title,
                    'description': description,
                    'content': content_text,
                    'image_file_id': None
                }
                context.user_data['pending_admin_action'] = 'special_pred'
                
                preview_text = f"""
📋 **معاينة التوقع الخاص:**

🏷️ **العنوان:** {title}
📝 **الوصف:** {description}
📄 **المحتوى:** {content_text}

⚠️ **هل تريد تأكيد الإضافة؟**
                """
                
                await update.message.reply_text(
                    preview_text,
                    reply_markup=get_confirmation_keyboard()
                )
            
            # تنظيف البيانات المؤقتة
            context.user_data.pop('admin_action', None)
            context.user_data.pop('special_prediction_data', None)
            
        elif admin_action == 'add_daily_pred':
            if update.message.photo:
                photo = update.message.photo[-1]
                message_text = update.message.caption or ""
                image_file_id = photo.file_id  # ✅ حفظ file_id بدلاً من البيانات الثنائية
                
                context.user_data['pending_message_data'] = {
                    'text': message_text,
                    'image_file_id': image_file_id
                }
                context.user_data['pending_admin_action'] = 'daily_pred'
                
                preview_text = f"""
📋 **معاينة توقعات اليوم:**

{message_text if message_text else "📸 صورة بدون نص"}

🖼️ *مرفق مع الصورة*

👥 **سيتم الإرسال للمستخدمين النشطين فقط**

⚠️ **هل تريد تأكيد الإرسال؟**
                """
                
                if message_text:
                    await update.message.reply_text(
                        preview_text,
                        reply_markup=get_confirmation_keyboard()
                    )
                else:
                    await update.message.reply_photo(
                        photo=image_file_id,
                        caption=preview_text,
                        reply_markup=get_confirmation_keyboard()
                    )
                
            else:
                message_text = text
                context.user_data['pending_message_data'] = {
                    'text': message_text,
                    'image_file_id': None
                }
                context.user_data['pending_admin_action'] = 'daily_pred'
                
                preview_text = f"""
📋 **معاينة توقعات اليوم:**

{message_text}

👥 **سيتم الإرسال للمستخدمين النشطين فقط**

⚠️ **هل تريد تأكيد الإرسال?**
                """
                
                await update.message.reply_text(
                    preview_text,
                    reply_markup=get_confirmation_keyboard()
                )
            
            context.user_data.pop('admin_action', None)
            
        elif admin_action == 'send_announcement':
            if update.message.photo:
                photo = update.message.photo[-1]
                message_text = update.message.caption or ""
                image_file_id = photo.file_id  # ✅ حفظ file_id بدلاً من البيانات الثنائية
                
                context.user_data['pending_message_data'] = {
                    'text': message_text,
                    'image_file_id': image_file_id
                }
                context.user_data['pending_admin_action'] = 'announcement'
                
                preview_text = f"""
📋 **معاينة الإعلان:**

{message_text if message_text else "📸 صورة بدون نص"}

🖼️ *مرفق مع الصورة*

👥 **سيتم الإرسال لجميع المستخدمين**

⚠️ **هل تريد تأكيد الإرسال؟**
                """
                
                if message_text:
                    await update.message.reply_text(
                        preview_text,
                        reply_markup=get_confirmation_keyboard()
                    )
                else:
                    await update.message.reply_photo(
                        photo=image_file_id,
                        caption=preview_text,
                        reply_markup=get_confirmation_keyboard()
                    )
                
            else:
                message_text = text
                context.user_data['pending_message_data'] = {
                    'text': message_text,
                    'image_file_id': None
                }
                context.user_data['pending_admin_action'] = 'announcement'
                
                preview_text = f"""
📋 **معاينة الإعلان:**

{message_text}

👥 **سيتم الإرسال لجميع المستخدمين**

⚠️ **هل تريد تأكيد الإرسال؟**
                """
                
                await update.message.reply_text(
                    preview_text,
                    reply_markup=get_confirmation_keyboard()
                )
            
            context.user_data.pop('admin_action', None)
            
        elif admin_action == 'search_user':
            # بحث عن مستخدم
            search_term = text.strip()
            users = search_users_by_username(search_term)
            
            if not users:
                await update.message.reply_text(
                    f"❌ **لم يتم العثور على مستخدمين مطابقين '{search_term}'**",
                    reply_markup=get_admin_keyboard()
                )
            else:
                text_result = f"🔍 **نتائج البحث عن '{search_term}':**\n\n"
                
                for user in users[:10]:
                    user_id, username, first_name, expiry, is_banned, created_at = user
                    status = "🚫" if is_banned else "✅"
                    username_display = f"@{username}" if username else "بدون يوزر"
                    
                    text_result += f"{status} **{first_name}** ({username_display})\n"
                    text_result += f"🆔: {user_id} | 📅: {created_at.split()[0]}\n"
                    
                    if expiry:
                        expiry_date = datetime.strptime(expiry, '%Y-%m-%d').date()
                        remaining = (expiry_date - datetime.now().date()).days
                        text_result += f"📅 ينتهي بعد: {remaining} يوم\n"
                    
                    text_result += f"🔧 `/ban_{user_id}` | `/unban_{user_id}` | `/info_{user_id}`\n\n"
                
                if len(users) > 10:
                    text_result += f"📎 *عرض 10 من {len(users)} نتيجة*"
                
                await update.message.reply_text(
                    text_result,
                    reply_markup=get_admin_keyboard()
                )
            
            context.user_data.pop('admin_action', None)
        
        else:
            await update.message.reply_text("❌ **لم أفهم الأمر**", reply_markup=get_admin_keyboard())
    except Exception as e:
        logger.error(f"❌ خطأ في handle_admin_conversation: {e}")
        await update.message.reply_text("❌ حدث خطأ في معالجة المحادثة.")

async def show_subscription_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        user_id = user.id
        
        # ✅ التحقق من الاشتراك في القناة إذا كانت محددة
        if REQUIRED_CHANNEL and not await check_channel_subscription(update, context, user_id):
            return
            
        status = get_user_subscription_status(user_id)
        
        if status in ['new', 'trial_eligible', 'trial_used', 'expired']:
            title = "💳 **بدء الاشتراك**"
        else:
            title = "💳 **تجديد الاشتراك**"
        
        text = f"{title}\n\n💰 **السعر:** {SUBSCRIPTION_SETTINGS['monthly_price']:,} ليرة سورية\n\n"
        text += "**اختر طريقة الدفع:**"
        
        context.user_data['payment_type'] = 'subscription'
        
        await update.message.reply_text(text, reply_markup=get_subscription_keyboard())
    except Exception as e:
        logger.error(f"❌ خطأ في show_subscription_options: {e}")
        await update.message.reply_text("❌ حدث خطأ في عرض خيارات الاشتراك.")

async def show_special_predictions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة التوقعات الخاصة للمستخدم"""
    try:
        user_id = update.effective_user.id
        
        # ✅ التحقق من الاشتراك في القناة إذا كانت محددة
        if REQUIRED_CHANNEL and not await check_channel_subscription(update, context, user_id):
            return
            
        special_predictions = get_active_special_predictions()
        if not special_predictions:
            await update.message.reply_text(
                "📭 **لا توجد توقعات خاصة متاحة حالياً**\n\n"
                "🔔 سنقوم بإعلامك فور توفر توقعات خاصة جديدة\n"
                "💫 ترقبوا العروض الحصرية القادمة!",
                reply_markup=get_main_keyboard(user_id, update.effective_user.username)
            )
            return
        
        list_text = "🔮 **قائمة التوقعات الخاصة المتاحة**\n\n"
        list_text += "📋 **اختر التوقع الذي تريد شراءه:**\n\n"
        
        keyboard = []
        
        for pred in special_predictions[:10]:
            pred_id, title, description, content, image_file_id = pred
            list_text += f"• **{title}**\n"
            keyboard.append([InlineKeyboardButton(f"📊 {title}", callback_data=f"view_special_{pred_id}")])
        
        keyboard.append([InlineKeyboardButton("🏠 START", callback_data="back_to_main")])
        
        await update.message.reply_text(
            list_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"❌ خطأ في show_special_predictions: {e}")
        await update.message.reply_text("❌ حدث خطأ في عرض التوقعات الخاصة.")

async def show_subscription_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض معلومات الاشتراك للمستخدم - معدلة"""
    try:
        user_id = update.effective_user.id
        
        # ✅ التحقق من الاشتراك في القناة إذا كانت محددة
        if REQUIRED_CHANNEL and not await check_channel_subscription(update, context, user_id):
            return
            
        user = get_user(user_id)
        
        if not user:
            await update.message.reply_text(
                "❌ **لم يتم العثور على حسابك**\n\n"
                "💳 اشترك الآن لمشاهدة التوقعات",
                reply_markup=get_main_keyboard(user_id, update.effective_user.username)
            )
            return
        
        status = get_user_subscription_status(user_id)
        
        if status in ['new', 'trial_eligible', 'expired', 'trial_used']:
            await update.message.reply_text(
                "❌ **لا يوجد اشتراك نشط**\n\n"
                "💳 اشترك الآن لمشاهدة التوقعات",
                reply_markup=get_main_keyboard(user_id, update.effective_user.username)
            )
            return
        
        # إذا كان هناك اشتراك نشط
        expiry_date = datetime.strptime(user[3], '%Y-%m-%d').date()
        remaining_days = (expiry_date - datetime.now().date()).days
        
        if status == 'trial_active':
            status_text = "🆓 تجريبية مجانية"
        else:
            status_text = "✅ نشط"
        
        info_text = f"""
ℹ️ **معلومات اشتراكك**

{status_text}
📅 **ينتهي في:** {expiry_date.strftime('%Y-%m-%d')}
⏰ **متبقي:** {remaining_days} يوم

🎯 **المميزات المتاحة:**
• مشاهدة التوقعات اليومية
• شراء التوقعات الخاصة
• تحديثات مستمرة

💡 **استخدم زر 🏠 START لمشاهدة آخر التوقعات!**
        """
        
        await update.message.reply_text(info_text, reply_markup=get_main_keyboard(user_id, update.effective_user.username))
    except Exception as e:
        logger.error(f"❌ خطأ في show_subscription_info: {e}")
        await update.message.reply_text("❌ حدث خطأ في عرض معلومات الاشتراك.")

async def handle_payment_method_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """معالجة اختيار طريقة الدفع"""
    try:
        user = update.effective_user
        user_id = user.id
        
        # ✅ التحقق من الاشتراك في القناة إذا كانت محددة
        if REQUIRED_CHANNEL and not await check_channel_subscription(update, context, user_id):
            return
            
        context.user_data['selected_payment_method'] = text
        
        method_key_map = {
            "📱 سيريتل كاش": "syriatel",
            "📲 شام كاش": "sham", 
            "📞 ام تي ان كاش": "mtn"
        }
        
        method_key = method_key_map.get(text)
        if not method_key:
            await update.message.reply_text("❌ **طريقة الدفع غير معروفة**")
            return
        
        payment_info = PAYMENT_SETTINGS.get(method_key)
        if not payment_info:
            await update.message.reply_text("❌ **معلومات الدفع غير متوفرة**")
            return
        
        payment_type = context.user_data.get('payment_type', 'subscription')
        
        if payment_type == 'subscription':
            required_amount = SUBSCRIPTION_SETTINGS['monthly_price']
            product = "اشتراك شهري"
            payment_step = "اشتراك"
            emoji = "📅"
        else:
            required_amount = SUBSCRIPTION_SETTINGS['prediction_price']
            product = "توقع خاص حصري"
            payment_step = "توقع خاص"
            emoji = "🎯"
            
            prediction_id = context.user_data.get('selected_prediction_id')
            if prediction_id:
                prediction = get_special_prediction_by_id(prediction_id)
                if prediction:
                    pred_id, title, description, content, image_file_id = prediction
                    product = f"توقع خاص: {title}"
        
        payment_text = f"""
{emoji} **عملية شراء {payment_step}**

🛒 **المنتج:** {product}
💰 **المبلغ المطلوب:** {required_amount:,} ليرة سورية
📱 **طريقة الدفع:** {payment_info['name']}
💳 **رقم الحساب:** `{payment_info['account_number']}`

  
**يرجى اتباع التعليمات التالية:**
*استخدم التحويل اليدوي في حالة اختيار سيريتل او mtn كاش *
• تحقق من تحويل المبلغ بالكامل
• تأكد من صحة رقم الحساب
• احتفظ برقم العملية

🔢 **الآن أرسل رقم العملية (أرقام باللغة الانكليزية** فقط، بدون مسافات أو أحرف):**
        """
        
        await update.message.reply_text(payment_text)
        context.user_data['payment_step'] = 'waiting_transaction_number'
        context.user_data['required_amount'] = required_amount
        context.user_data['method_key'] = method_key
        
        logger.info(f"✅ بدء عملية دفع للمستخدم {user_id}: {payment_type} - {method_key}")
        
    except Exception as e:
        logger.error(f"❌ خطأ في handle_payment_method_selection: {e}")
        await update.message.reply_text("❌ **حدث خطأ غير متوقع. يرجى المحاولة مرة أخرى لاحقاً.**")

async def handle_conversation_state(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """معالجة إدخال رقم التحويل والمبلغ"""
    try:
        user = update.effective_user
        user_id = user.id
        username = user.username or "بدون يوزر"
        
        # ✅ التحقق من الاشتراك في القناة إذا كانت محددة
        if REQUIRED_CHANNEL and not await check_channel_subscription(update, context, user_id):
            return
            
        payment_step = context.user_data.get('payment_step')
        
        if payment_step == 'waiting_transaction_number':
            transaction_number = text.strip()
            
            if not transaction_number:
                await update.message.reply_text("❌ **يرجى إدخال رقم العملية**")
                return
            
            if not transaction_number.isdigit():
                await update.message.reply_text("❌ **يجب أن يحتوي رقم العملية على أرقام فقط، بدون مسافات أو أحرف**")
                return
            
            if len(transaction_number) < 3:
                await update.message.reply_text("❌ **رقم العملية قصير جداً، يرجى إدخال رقم صحيح**")
                return
            
            context.user_data['transaction_number'] = transaction_number
            context.user_data['payment_step'] = 'waiting_amount'
            
            required_amount = context.user_data.get('required_amount', 0)
            
            await update.message.reply_text(
                f"✅ **تم حفظ رقم العملية: {transaction_number}**\n\n"
                f"💰 **الآن أرسل المبلغ الذي قمت بتحويله (أرقام فقط):**\n"
                f"المبلغ المطلوب: {required_amount:,} ليرة"
            )
            
        elif payment_step == 'waiting_amount':
            amount_text = text.strip()
            
            if not amount_text:
                await update.message.reply_text("❌ **يرجى إدخال المبلغ**")
                return
            
            if not amount_text.isdigit():
                await update.message.reply_text("❌ **يجب أن يحتوي المبلغ على أرقام فقط، بدون مسافات أو أحرف أو فواصل**")
                return
            
            try:
                amount = int(amount_text)
            except ValueError:
                await update.message.reply_text("❌ **المبلغ غير صحيح، يرجى إدخال أرقام فقط**")
                return
            
            required_amount = context.user_data.get('required_amount', 0)
            
            if amount < required_amount:
                await update.message.reply_text(
                    f"❌ **المبلغ المسدد أقل من المطلوب**\n\n"
                    f"💰 المبلغ المطلوب: {required_amount:,} ليرة\n"
                    f"💸 المبلغ المسدد: {amount:,} ليرة\n\n"
                    f"يرجى تحويل المبلغ المطلوب بالكامل وإعادة الإجراء."
                )
                context.user_data.clear()
                return
            
            transaction_number = context.user_data.get('transaction_number')
            payment_type = context.user_data.get('payment_type', 'subscription')
            method_key = context.user_data.get('method_key')
            
            if not method_key:
                await update.message.reply_text("❌ **لم يتم تحديد طريقة الدفع**")
                context.user_data.clear()
                return
            
            payment_info = PAYMENT_SETTINGS.get(method_key)
            if not payment_info:
                await update.message.reply_text("❌ **معلومات الدفع غير متوفرة**")
                context.user_data.clear()
                return
            
            if payment_type == 'subscription':
                transaction_id = add_subscription_transaction(user_id, transaction_number, amount, method_key)
                
                if transaction_id:
                    await update.message.reply_text(
                        "✅ **تم استلام معلومات الدفع بنجاح**\n\n"
                        f"🔢 **رقم العملية:** {transaction_number}\n"
                        f"💰 **المبلغ:** {amount:,} ليرة\n"
                        f"📱 **طريقة الدفع:** {payment_info['name']}\n\n"
                        "⏳ **جاري المراجعة من قبل الإدارة...**\n\n"
                        "سيتم إعلامك فور الموافقة على طلبك.",
                        reply_markup=get_main_keyboard(user_id, username)
                    )
                    
                    admin_text = f"""
🔔 **طلب اشتراك جديد**

👤 **المستخدم:** {user.first_name}
📧 **اليوزر:** @{username if username else 'بدون يوزر'}
🆔 **ID:** {user_id}
💰 **المبلغ:** {amount:,} ليرة
📱 **الطريقة:** {payment_info['name']}
🔢 **رقم العملية:** {transaction_number}
🆔 **معاملة:** {transaction_id}
                    """
                    
                    keyboard = InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("✅ الموافقة", callback_data=f"approve_sub_{transaction_id}"),
                            InlineKeyboardButton("❌ الرفض", callback_data=f"reject_sub_{transaction_id}")
                        ]
                    ])
                    
                    await notify_admins(context, admin_text, keyboard, "subscription")
                else:
                    await update.message.reply_text(
                        "❌ **حدث خطأ في حفظ المعاملة**\n\n"
                        "يرجى المحاولة مرة أخرى أو التواصل مع خدمة العملاء.",
                        reply_markup=get_main_keyboard(user_id, username)
                    )
            
            elif payment_type == 'special_prediction':
                prediction_id = context.user_data.get('selected_prediction_id')
                transaction_id = add_prediction_transaction(user_id, transaction_number, amount, method_key, prediction_id)
                
                if transaction_id:
                    prediction_info = ""
                    if prediction_id:
                        prediction = get_special_prediction_by_id(prediction_id)
                        if prediction:
                            pred_id, title, description, content, image_file_id = prediction
                            prediction_info = f"📋 **التوقع:** {title}"
                    
                    await update.message.reply_text(
                        "✅ **تم استلام معلومات الدفع بنجاح**\n\n"
                        f"🔢 **رقم العملية:** {transaction_number}\n"
                        f"💰 **المبلغ:** {amount:,} ليرة\n"
                        f"📱 **طريقة الدفع:** {payment_info['name']}\n"
                        f"{prediction_info}\n\n"
                        "⏳ **جاري المراجعة من قبل الإدارة...**\n\n"
                        "سيتم إرسال التوقع الخاص فور الموافقة على طلبك.",
                        reply_markup=get_main_keyboard(user_id, username)
                    )
                    
                    admin_text = f"""
🎯 **طلب توقع خاص جديد**

👤 **المستخدم:** {user.first_name}
📧 **اليوزر:** @{username if username else 'بدون يوزر'}
🆔 **ID:** {user_id}
💰 **المبلغ:** {amount:,} ليرة
📱 **الطريقة:** {payment_info['name']}
🔢 **رقم العملية:** {transaction_number}
{prediction_info}
🆔 **معاملة:** {transaction_id}
                    """
                    
                    keyboard = InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("✅ الموافقة", callback_data=f"approve_pred_{transaction_id}"),
                            InlineKeyboardButton("❌ الرفض", callback_data=f"reject_pred_{transaction_id}")
                        ]
                    ])
                    
                    await notify_admins(context, admin_text, keyboard, "special_prediction")
                else:
                    await update.message.reply_text(
                        "❌ **حدث خطأ في حفظ المعاملة**\n\n"
                        "يرجى المحاولة مرة أخرى أو التواصل مع خدمة العملاء.",
                        reply_markup=get_main_keyboard(user_id, username)
                    )
            
            context.user_data.clear()
            
        else:
            await update.message.reply_text(
                "❌ **لم أفهم طلبك**\n\n"
                "يرجى استخدام الأزرار الموجودة في القائمة للتنقل بين الميزات.",
                reply_markup=get_main_keyboard(user_id, username)
            )
            
    except Exception as e:
        logger.error(f"❌ خطأ في handle_conversation_state: {e}")
        await update.message.reply_text("❌ **حدث خطأ غير متوقع. يرجى المحاولة مرة أخرى لاحقاً.**")
        context.user_data.clear()

async def notify_admins(context, message: str, keyboard=None, transaction_type="subscription"):
    """إرسال إشعار لجميع الأدمن"""
    try:
        conn = sqlite3.connect('predictions_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM admins WHERE user_id != 0')
        admins = cursor.fetchall()
        conn.close()
        
        if not admins:
            logger.warning("⚠️ لا يوجد أدمن في قاعدة البيانات.")
            return
        
        if transaction_type == "special_prediction":
            icon = "🎯"
            type_text = "توقع خاص"
        elif transaction_type == "system":
            icon = "🔔"
            type_text = "نظام"
        elif transaction_type == "trial":
            icon = "🆓"
            type_text = "تجربة مجانية"
        else:
            icon = "💳"
            type_text = "اشتراك"
        
        message_with_icon = f"{icon} **{type_text}**\n\n{message}"
        
        logger.info(f"📢 جاري إرسال إشعار {type_text} لـ {len(admins)} أدمن")
        
        for admin in admins:
            try:
                if keyboard:
                    await context.bot.send_message(
                        chat_id=admin[0],
                        text=message_with_icon,
                        parse_mode='Markdown',
                        reply_markup=keyboard
                    )
                else:
                    await context.bot.send_message(
                        chat_id=admin[0],
                        text=message_with_icon,
                        parse_mode='Markdown'
                    )
                logger.info(f"✅ تم إرسال إشعار {type_text} للأدمن {admin[0]}")
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"❌ فشل في إرسال إشعار للأدمن {admin[0]}: {e}")
                continue
                
    except Exception as e:
        logger.error(f"❌ خطأ في notify_admins: {e}")

async def show_today_predictions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض توقعات اليوم"""
    try:
        user_id = update.effective_user.id
        
        # ✅ التحقق من الاشتراك في القناة إذا كانت محددة
        if REQUIRED_CHANNEL and not await check_channel_subscription(update, context, user_id):
            return
            
        if not is_user_subscribed(user_id):
            await update.message.reply_text("❌ **تحتاج إلى اشتراك نشط لمشاهدة التوقعات**")
            return
        
        prediction = get_active_daily_prediction()
        if not prediction:
            await update.message.reply_text(
                "📭 **لا توجد توقعات اليوم**\n\n"
                "سيتم إضافة التوقعات قريباً...\n"
                "🔔 استخدم زر **🏠 START** للتحقق من آخر التحديثات!",
                reply_markup=get_main_keyboard(user_id, update.effective_user.username)
            )
            return
        
        pred_id, prediction_text, image_file_id = prediction
        
        if image_file_id:
            await send_message_with_photo(
                context, 
                user_id, 
                f"🎯 **توقعات اليوم**\n\n{prediction_text}\n\n📊 *نتمنى لك ربحاً موفقاً*",
                image_file_id,
                "🎯 توقعات اليوم"
            )
        else:
            await update.message.reply_text(f"🎯 **توقعات اليوم**\n\n{prediction_text}\n\n📊 *نتمنى لك ربحاً موفقاً*")
            
    except Exception as e:
        logger.error(f"❌ خطأ في show_today_predictions: {e}")
        await update.message.reply_text("❌ حدث خطأ في عرض التوقعات.")

async def customer_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """خدمة العملاء"""
    text = """
👨‍💼 **خدمة العملاء**

للتواصل والاستفسار:
@ESE_support

⏰ أوقات العمل: متواجدون على مدار الساعة🔄
    """
    await update.message.reply_text(text)

async def handle_admin_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        
        if not is_admin(user.id, user.username):
            await update.message.reply_text("❌ **ليس لديك صلاحية للوصول إلى هذا الأمر**")
            return
        
        text = update.message.text
        
        if text.startswith('/ban_'):
            try:
                user_id = int(text.replace('/ban_', ''))
                await ban_user_command(update, context, user_id)
            except ValueError:
                await update.message.reply_text("❌ **رقم المستخدم غير صحيح**")
        
        elif text.startswith('/unban_'):
            try:
                user_id = int(text.replace('/unban_', ''))
                await unban_user_command(update, context, user_id)
            except ValueError:
                await update.message.reply_text("❌ **رقم المستخدم غير صحيح**")
        
        elif text.startswith('/info_'):
            try:
                user_id = int(text.replace('/info_', ''))
                await show_user_info(update, context, user_id)
            except ValueError:
                await update.message.reply_text("❌ **رقم المستخدم غير صحيح**")
        
        elif text.startswith('/user_info '):
            parts = text.split(' ')
            if len(parts) >= 2:
                try:
                    user_id = int(parts[1])
                    await show_user_info(update, context, user_id)
                except ValueError:
                    await update.message.reply_text("❌ **رقم المستخدم غير صحيح**")
        
        elif text.startswith('/extend_sub '):
            parts = text.split(' ')
            if len(parts) >= 3:
                try:
                    user_id = int(parts[1])
                    days = int(parts[2])
                    await extend_subscription(update, context, user_id, days)
                except ValueError:
                    await update.message.reply_text("❌ **الأرقام غير صحيحة**")
        
        elif text.startswith('/set_monthly_price '):
            parts = text.split(' ')
            if len(parts) >= 2:
                try:
                    new_price = int(parts[1])
                    await set_monthly_price(update, context, new_price)
                except ValueError:
                    await update.message.reply_text("❌ **السعر غير صحيح**")
        
        elif text.startswith('/set_prediction_price '):
            parts = text.split(' ')
            if len(parts) >= 2:
                try:
                    new_price = int(parts[1])
                    await set_prediction_price(update, context, new_price)
                except ValueError:
                    await update.message.reply_text("❌ **السعر غير صحيح**")
        
        elif text == '/cancel':
            context.user_data.clear()
            await show_admin_dashboard(update, context)
        
        else:
            await update.message.reply_text("❌ **أمر غير معروف**")
    except Exception as e:
        logger.error(f"❌ خطأ في handle_admin_commands: {e}")
        await update.message.reply_text("❌ حدث خطأ في معالجة الأمر.")

async def set_monthly_price(update: Update, context: ContextTypes.DEFAULT_TYPE, new_price: int):
    """تحديث سعر الاشتراك الشهري"""
    try:
        if new_price <= 0:
            await update.message.reply_text("❌ **السعر يجب أن يكون أكبر من صفر**")
            return
        
        update_setting('monthly_price', str(new_price))
        
        await update.message.reply_text(
            f"✅ **تم تحديث سعر الاشتراك الشهري إلى {new_price:,} ليرة**\n\n"
            f"سيتم تطبيق السعر الجديد على جميع الاشتراكات الجديدة.",
            reply_markup=get_admin_keyboard()
        )
        
        logger.info(f"✅ تم تحديث سعر الاشتراك الشهري إلى {new_price}")
    except Exception as e:
        logger.error(f"❌ خطأ في set_monthly_price: {e}")
        await update.message.reply_text("❌ حدث خطأ في تحديث السعر.")

async def set_prediction_price(update: Update, context: ContextTypes.DEFAULT_TYPE, new_price: int):
    """تحديث سعر التوقع الخاص"""
    try:
        if new_price <= 0:
            await update.message.reply_text("❌ **السعر يجب أن يكون أكبر من صفر**")
            return
        
        update_setting('prediction_price', str(new_price))
        
        await update.message.reply_text(
            f"✅ **تم تحديث سعر التوقع الخاص إلى {new_price:,} ليرة**\n\n"
            f"سيتم تطبيق السعر الجديد على جميع التوقعات الخاصة الجديدة.",
            reply_markup=get_admin_keyboard()
        )
        
        logger.info(f"✅ تم تحديث سعر التوقع الخاص إلى {new_price}")
    except Exception as e:
        logger.error(f"❌ خطأ في set_prediction_price: {e}")
        await update.message.reply_text("❌ حدث خطأ في تحديث السعر.")

async def ban_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """حظر مستخدم"""
    try:
        user = get_user(user_id)
        if not user:
            await update.message.reply_text("❌ **لم يتم العثور على المستخدم**")
            return
        
        ban_user(user_id)
        
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ **تم حظر حسابك من استخدام البوت**\n\n"
                     "للمزيد من المعلومات، يرجى التواصل مع خدمة العملاء."
            )
        except Exception as e:
            logger.error(f"❌ فشل في إعلام المستخدم المحظور {user_id}: {e}")
        
        await update.message.reply_text(
            f"✅ **تم حظر المستخدم {user_id}**",
            reply_markup=get_admin_keyboard()
        )
    except Exception as e:
        logger.error(f"❌ خطأ في ban_user_command: {e}")
        await update.message.reply_text("❌ حدث خطأ في حظر المستخدم.")

async def unban_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """فك حظر مستخدم"""
    try:
        user = get_user(user_id)
        if not user:
            await update.message.reply_text("❌ **لم يتم العثور على المستخدم**")
            return
        
        unban_user(user_id)
        
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="✅ **تم فك حظر حسابك**\n\n"
                     "يمكنك الآن استخدام البوت مرة أخرى."
            )
        except Exception as e:
            logger.error(f"❌ فشل في إعلام المستخدم {user_id}: {e}")
        
        await update.message.reply_text(
            f"✅ **تم فك حظر المستخدم {user_id}**",
            reply_markup=get_admin_keyboard()
        )
    except Exception as e:
        logger.error(f"❌ خطأ في unban_user_command: {e}")
        await update.message.reply_text("❌ حدث خطأ في فك حظر المستخدم.")

async def show_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """عرض معلومات مستخدم"""
    try:
        user = get_user(user_id)
        if not user:
            await update.message.reply_text("❌ **لم يتم العثور على المستخدم**")
            return
        
        status = get_user_subscription_status(user_id)
        status_text = {
            'new': '🆕 جديد',
            'trial_eligible': '🆓 مؤهل للتجربة',
            'trial_active': '🆓 تجريبية نشطة',
            'trial_used': '🆓 استخدم التجربة',
            'active': '✅ نشط',
            'expired': '❌ منتهي',
            'banned': '🚫 محظور'
        }.get(status, 'غير معروف')
        
        user_info = f"""
👤 **معلومات المستخدم**

🆔 **ID:** {user[0]}
👤 **الاسم:** {user[2]}
📧 **اليوزر:** @{user[1] if user[1] else 'بدون يوزر'}
📅 **تاريخ التسجيل:** {user[5].split()[0] if user[5] else 'غير معروف'}

🎯 **حالة الاشتراك:** {status_text}
        """
        
        if user[3]:
            expiry_date = datetime.strptime(user[3], '%Y-%m-%d').date()
            remaining_days = (expiry_date - datetime.now().date()).days
            user_info += f"📅 **ينتهي في:** {user[3]}\n"
            user_info += f"⏰ **متبقي:** {remaining_days} يوم\n"
        
        user_info += f"\n🔧 **الأوامر:**\n"
        user_info += f"• `/ban_{user_id}` - حظر المستخدم\n"
        user_info += f"• `/unban_{user_id}` - فك حظر المستخدم\n"
        user_info += f"• `/extend_sub {user_id} 30` - تمديد 30 يوم"
        
        await update.message.reply_text(user_info, reply_markup=get_admin_keyboard())
    except Exception as e:
        logger.error(f"❌ خطأ في show_user_info: {e}")
        await update.message.reply_text("❌ حدث خطأ في عرض معلومات المستخدم.")

async def extend_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, days: int):
    """تمديد اشتراك مستخدم"""
    try:
        user = get_user(user_id)
        if not user:
            await update.message.reply_text("❌ **لم يتم العثور على المستخدم**")
            return
        
        update_subscription(user_id, days)
        
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎉 **تم تمديد اشتراكك!**\n\n"
                     f"📅 **تمت إضافة {days} يوم لاشتراكك**\n"
                     f"💡 **استخدم زر 🏠 START لمشاهدة آخر التوقعات!**\n"
                     f"شكراً لثقتك بنا! 🏆"
            )
        except Exception as e:
            logger.error(f"❌ فشل في إعلام المستخدم {user_id}: {e}")
        
        await update.message.reply_text(
            f"✅ **تم تمديد اشتراك المستخدم {user_id} لمدة {days} يوم**",
            reply_markup=get_admin_keyboard()
        )
    except Exception as e:
        logger.error(f"❌ خطأ في extend_subscription: {e}")
        await update.message.reply_text("❌ حدث خطأ في تمديد الاشتراك.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الأخطاء العام"""
    try:
        logger.error(f"❌ استثناء أثناء معالجة التحديث: {context.error}")
        
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ حدث خطأ غير متوقع. يرجى المحاولة مرة أخرى لاحقاً."
            )
    except Exception as e:
        logger.error(f"❌ خطأ في معالج الأخطاء: {e}")

# 🚀 نظام إدارة البوت المحسن
class BotManager:
    def __init__(self):
        self.application = None
        self.is_running = False
        
    async def initialize(self):
        """تهيئة البوت"""
        try:
            update_database_schema()
            load_settings_from_db()
            
            self.application = Application.builder().token(BOT_TOKEN).build()
            
            self.application.add_handler(CommandHandler("start", start))
            self.application.add_handler(CallbackQueryHandler(handle_callback))
            self.application.add_handler(CommandHandler("cancel", handle_admin_commands))
            self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
            self.application.add_handler(MessageHandler(filters.TEXT & filters.COMMAND, handle_admin_commands))
            self.application.add_handler(MessageHandler(filters.PHOTO, handle_message))
            
            self.application.add_error_handler(error_handler)
            
            logger.info("✅ تم تهيئة البوت بنجاح")
            return True
            
        except Exception as e:
            logger.error(f"❌ فشل في تهيئة البوت: {e}")
            return False
    
    async def start_polling(self):
        """بدء استقبال الرسائل"""
        try:
            if not self.application:
                logger.error("❌ البوت غير مهيء")
                return
            
            logger.info("🚀 بدء تشغيل البوت...")
            self.is_running = True
            
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            
            logger.info("✅ البوت يعمل الآن واستقبال الرسائل")
            
            while self.is_running:
                await asyncio.sleep(1)
                
        except asyncio.CancelledError:
            logger.info("🛑 تم إلغاء التشغيل")
        except Exception as e:
            logger.error(f"❌ خطأ في التشغيل: {e}")
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """إغلاق البوت بشكل آمن"""
        if not self.is_running:
            return
            
        logger.info("🔴 جاري إغلاق البوت...")
        self.is_running = False
        
        try:
            if self.application:
                if hasattr(self.application, 'updater') and self.application.updater:
                    await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
            
            logger.info("✅ تم إغلاق البوت بنجاح")
            
        except Exception as e:
            logger.error(f"⚠️ حدث خطأ أثناء الإغلاق: {e}")

async def main_async():
    """الدالة الرئيسية بشكل async محسن"""
    init_db()
    
    print("🚀 بدء تشغيل بوت توقعات المباريات...")
    print("=" * 50)
    print("✅ المميزات المضمنة:")
    print("   - نظام اشتراط الانضمام للقناة قبل الاستخدام")
    print("   - نظام التجربة المجانية لمدة 3 أيام")
    print("   - تحكم كامل للأدمن في النظام التجريبي")
    print("   - إحصائيات مفصلة للتجارب المستخدمة")
    print("   - زر START لجميع المستخدمين")
    print("   - إرسال الإعلانات للمستخدمين غير المتصلين عند عودتهم")
    print("   - نظام هدايا الاشتراكات للأدمن")
    print("   - نظام حذف الإعلانات المعلقة")
    print("   - منع إرسال الإعلانات السابقة للمشتركين الجدد")
    print("   - زر إعادة تعيين الإيرادات مع التأكيدات")
    print("=" * 50)
    
    if REQUIRED_CHANNEL:
        print(f"📢 البوت يشترط الاشتراك في القناة: @{REQUIRED_CHANNEL}")
    else:
        print("📢 لا يوجد قناة مطلوبة - يمكن إضافتها لاحقاً في متغير REQUIRED_CHANNEL")
    
    bot_manager = BotManager()
    
    if not await bot_manager.initialize():
        print("❌ فشل في تهيئة البوت")
        return
    
    def signal_handler(signum, frame):
        print(f"\n📡 تم استقبال إشارة إغلاق ({signum})")
        bot_manager.is_running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await bot_manager.start_polling()
    except KeyboardInterrupt:
        print("\n🛑 إيقاف البوت بواسطة المستخدم")
    except Exception as e:
        print(f"❌ خطأ غير متوقع: {e}")
    finally:
        await bot_manager.shutdown()

def main():
    """الدالة الرئيسية"""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n🛑 إيقاف البرنامج...")
    except Exception as e:
        print(f"❌ خطأ غير متوقع: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()