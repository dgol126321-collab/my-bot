import asyncio
import sys
sys.path.insert(0, '/home/dawid/trading_bots')
from config import BOT2_TOKEN, GROUP_ID, FOREX_THREAD_ID
from telegram import Bot, Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

bot = Bot(token=BOT2_TOKEN)

def assess_risk(sentiment: str, score: float, fear_greed: str) -> tuple:
    """Оценивает риск на основе данных аналитика"""
    risk_level = "MEDIUM"
    risk_score = 50

    # Оцениваем по сентименту
    if "негативный" in sentiment:
        risk_score += 30
    elif "позитивный" in sentiment:
        risk_score -= 20

    # Оцениваем по Fear & Greed
    try:
        fg_value = int(fear_greed.split()[0])
        if fg_value < 25:
            risk_score += 25  # Extreme Fear — высокий риск
        elif fg_value > 75:
            risk_score += 15  # Extreme Greed — тоже риск
        else:
            risk_score -= 10
    except:
        pass

    # Определяем уровень риска
    if risk_score >= 70:
        risk_level = "🔴 HIGH"
        recommendation = "Воздержаться от торговли"
        max_lot = 0.01
    elif risk_score >= 40:
        risk_level = "🟡 MEDIUM"
        recommendation = "Торговать с осторожностью"
        max_lot = 0.05
    else:
        risk_level = "🟢 LOW"
        recommendation = "Можно торговать"
        max_lot = 0.1

    return risk_level, recommendation, max_lot, risk_score

def parse_analyst_message(text: str) -> dict:
    """Парсит сообщение аналитика"""
    result = {"sentiment": "", "fear_greed": "", "is_analyst": False}

    if "Forex Аналитик" not in text:
        return result

    result["is_analyst"] = True

    lines = text.split('\n')
    for line in lines:
        if "Сентимент:" in line:
            result["sentiment"] = line
        if "Fear & Greed:" in line:
            result["fear_greed"] = line.split("Fear & Greed:")[-1].strip()

    return result

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик новых сообщений в топике"""
    message = update.message
    if not message or not message.text:
        return

    # Проверяем что сообщение из нашего топика
    if message.message_thread_id != FOREX_THREAD_ID:
        return

    # Игнорируем свои сообщения
    if message.from_user and message.from_user.is_bot:
        # Проверяем что это не наш бот
        if str(BOT2_TOKEN.split(':')[0]) in str(message.from_user.id):
            return

    parsed = parse_analyst_message(message.text)
    if not parsed["is_analyst"]:
        return

    # Оцениваем риск
    risk_level, recommendation, max_lot, risk_score = assess_risk(
        parsed["sentiment"],
        0,
        parsed["fear_greed"]
    )

    report = f"""
⚖️ <b>Risk Manager — оценка риска</b>

📊 <b>Уровень риска:</b> {risk_level}
🎯 <b>Риск-скор:</b> {risk_score}/100
💡 <b>Рекомендация:</b> {recommendation}
📦 <b>Макс. лот:</b> {max_lot}

⏱ Ожидаю решения трейдера...
    """

    await bot.send_message(
        chat_id=GROUP_ID,
        message_thread_id=FOREX_THREAD_ID,
        text=report,
        parse_mode='HTML'
    )
    print(f"Риск-менеджер отправил оценку: {risk_level}")

def main():
    app = Application.builder().token(BOT2_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Бот 2 (Риск-менеджер) запущен!")
    app.run_polling(allowed_updates=["message"])

if __name__ == "__main__":
    main()
