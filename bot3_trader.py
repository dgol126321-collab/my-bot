import asyncio
import json
import os
import sys
import requests
from datetime import datetime
sys.path.insert(0, '/home/dawid/trading_bots')
from config import BOT3_TOKEN, GROUP_ID, FOREX_THREAD_ID, ALPHA_VANTAGE_KEY, FOREX_PAIRS
from telegram import Bot, Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

bot = Bot(token=BOT3_TOKEN)

# Файл для хранения открытых позиций
POSITIONS_FILE = '/home/dawid/trading_bots/positions.json'

def load_positions() -> dict:
    if os.path.exists(POSITIONS_FILE):
        with open(POSITIONS_FILE, 'r') as f:
            return json.load(f)
    return {"balance": 10000.0, "trades": [], "total_pnl": 0.0}

def save_positions(data: dict):
    with open(POSITIONS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def get_current_price(pair: str) -> float:
    """Получает текущую цену через Alpha Vantage"""
    try:
        # Alpha Vantage формат: EURUSD -> from=EUR, to=USD
        from_currency = pair[:3]
        to_currency = pair[3:]
        url = f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency={from_currency}&to_currency={to_currency}&apikey={ALPHA_VANTAGE_KEY}"
        r = requests.get(url, timeout=10)
        data = r.json()
        rate = float(data['Realtime Currency Exchange Rate']['5. Exchange Rate'])
        return rate
    except:
        # Фолбэк цены если API недоступен
        fallback = {"EURUSD": 1.0850, "GBPUSD": 1.2650, "USDJPY": 149.50}
        return fallback.get(pair, 1.0)

def decide_trade(sentiment: str, risk_level: str) -> str:
    """Принимает решение о сделке"""
    if "HIGH" in risk_level:
        return "HOLD"
    if "позитивный" in sentiment and "LOW" in risk_level:
        return "BUY"
    if "негативный" in sentiment and "LOW" in risk_level:
        return "SELL"
    if "позитивный" in sentiment and "MEDIUM" in risk_level:
        return "BUY"
    if "негативный" in sentiment and "MEDIUM" in risk_level:
        return "SELL"
    return "HOLD"

def execute_trade(action: str, pair: str, lot: float, data: dict) -> dict:
    """Симулирует открытие/закрытие сделки"""
    price = get_current_price(pair)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Закрываем старые позиции по этой паре
    closed_pnl = 0.0
    new_trades = []
    for trade in data["trades"]:
        if trade["pair"] == pair:
            # Считаем P&L
            if trade["action"] == "BUY":
                pnl = (price - trade["open_price"]) * trade["lot"] * 100000
            else:
                pnl = (trade["open_price"] - price) * trade["lot"] * 100000
            closed_pnl += pnl
        else:
            new_trades.append(trade)

    data["trades"] = new_trades
    data["total_pnl"] += closed_pnl
    data["balance"] += closed_pnl

    result = {
        "action": action,
        "pair": pair,
        "price": price,
        "lot": lot,
        "time": now,
        "closed_pnl": closed_pnl
    }

    if action != "HOLD":
        data["trades"].append({
            "action": action,
            "pair": pair,
            "open_price": price,
            "lot": lot,
            "time": now
        })

    save_positions(data)
    return result

def parse_risk_message(text: str) -> dict:
    """Парсит сообщение риск-менеджера"""
    result = {"is_risk": False, "risk_level": "", "max_lot": 0.05}

    if "Risk Manager" not in text:
        return result

    result["is_risk"] = True

    for line in text.split('\n'):
        if "Уровень риска:" in line:
            result["risk_level"] = line
        if "Макс. лот:" in line:
            try:
                result["max_lot"] = float(line.split(":")[-1].strip())
            except:
                pass

    return result

# Хранилище последнего сентимента от аналитика
last_sentiment = {"text": "🟡 нейтральный"}

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_sentiment
    message = update.message
    if not message or not message.text:
        return

    if message.message_thread_id != FOREX_THREAD_ID:
        return

    if message.from_user and message.from_user.is_bot:
        if str(BOT3_TOKEN.split(':')[0]) in str(message.from_user.id):
            return

    text = message.text

    # Запоминаем сентимент от аналитика
    if "Forex Аналитик" in text:
        for line in text.split('\n'):
            if "Сентимент:" in line:
                last_sentiment["text"] = line
        return

    # Реагируем на риск-менеджера
    parsed = parse_risk_message(text)
    if not parsed["is_risk"]:
        return

    data = load_positions()
    action = decide_trade(last_sentiment["text"], parsed["risk_level"])
    pair = FOREX_PAIRS[0]  # Торгуем первой парой из конфига
    lot = parsed["max_lot"]

    result = execute_trade(action, pair, lot, data)
    data = load_positions()

    # Формируем отчёт
    open_positions = "\n".join([
        f"• {t['action']} {t['pair']} @ {t['open_price']:.5f} | лот: {t['lot']}"
        for t in data["trades"]
    ]) or "• нет открытых позиций"

    pnl_emoji = "🟢" if result["closed_pnl"] >= 0 else "🔴"

    report = f"""
💼 <b>Trader — исполнение</b>

🎯 <b>Действие:</b> {action}
💱 <b>Пара:</b> {pair}
💰 <b>Цена:</b> {result['price']:.5f}
📦 <b>Лот:</b> {lot}

{pnl_emoji} <b>P&L закрытых:</b> ${result['closed_pnl']:.2f}
💵 <b>Баланс:</b> ${data['balance']:.2f}
📈 <b>Общий P&L:</b> ${data['total_pnl']:.2f}

📂 <b>Открытые позиции:</b>
{open_positions}
    """

    await bot.send_message(
        chat_id=GROUP_ID,
        message_thread_id=FOREX_THREAD_ID,
        text=report,
        parse_mode='HTML'
    )
    print(f"Трейдер выполнил: {action} {pair} @ {result['price']}")

def main():
    app = Application.builder().token(BOT3_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Бот 3 (Трейдер) запущен!")
    app.run_polling(allowed_updates=["message"])

if __name__ == "__main__":
    main()
