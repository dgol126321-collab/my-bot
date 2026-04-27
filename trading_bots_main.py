import feedparser
import requests
import asyncio
import json
import os
from datetime import datetime
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from telegram import Bot
from apscheduler.schedulers.blocking import BlockingScheduler
import sys
sys.path.insert(0, '/home/dawid/trading_bots')
from config import BOT1_TOKEN, BOT2_TOKEN, BOT3_TOKEN, GROUP_ID, FOREX_THREAD_ID, ALPHA_VANTAGE_KEY, FOREX_PAIRS

bot1 = Bot(token=BOT1_TOKEN)
bot2 = Bot(token=BOT2_TOKEN)
bot3 = Bot(token=BOT3_TOKEN)
analyzer = SentimentIntensityAnalyzer()

POSITIONS_FILE = '/home/dawid/trading_bots/positions.json'

# ============ БОТ 1 — АНАЛИТИК ============

def get_news():
    urls = [
        "https://www.forexlive.com/feed",
        "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines"
    ]
    news = []
    for url in urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:3]:
                news.append(entry.title)
        except:
            pass
    return news

def get_fear_greed():
    try:
        r = requests.get("https://api.alternative.me/fng/", timeout=10)
        data = r.json()
        value = data['data'][0]['value']
        label = data['data'][0]['value_classification']
        return f"{value} ({label})", int(value)
    except:
        return "недоступен", 50

def analyze_sentiment(news_list):
    if not news_list:
        return "🟡 нейтральный", 0
    scores = [analyzer.polarity_scores(n)['compound'] for n in news_list]
    avg = sum(scores) / len(scores)
    if avg > 0.2:
        return "🟢 позитивный", avg
    elif avg < -0.2:
        return "🔴 негативный", avg
    return "🟡 нейтральный", avg

# ============ БОТ 2 — РИСК-МЕНЕДЖЕР ============

def assess_risk(sentiment, score, fg_value):
    risk_score = 50
    if "негативный" in sentiment:
        risk_score += 30
    elif "позитивный" in sentiment:
        risk_score -= 20
    if fg_value < 25:
        risk_score += 25
    elif fg_value > 75:
        risk_score += 15
    else:
        risk_score -= 10

    if risk_score >= 70:
        return "🔴 HIGH", "Воздержаться от торговли", 0.01, risk_score
    elif risk_score >= 40:
        return "🟡 MEDIUM", "Торговать с осторожностью", 0.05, risk_score
    else:
        return "🟢 LOW", "Можно торговать", 0.1, risk_score

# ============ БОТ 3 — ТРЕЙДЕР ============

def load_positions():
    if os.path.exists(POSITIONS_FILE):
        with open(POSITIONS_FILE, 'r') as f:
            return json.load(f)
    return {"balance": 10000.0, "trades": [], "total_pnl": 0.0}

def save_positions(data):
    with open(POSITIONS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def get_current_price(pair):
    try:
        from_currency = pair[:3]
        to_currency = pair[3:]
        url = f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency={from_currency}&to_currency={to_currency}&apikey={ALPHA_VANTAGE_KEY}"
        r = requests.get(url, timeout=10)
        data = r.json()
        return float(data['Realtime Currency Exchange Rate']['5. Exchange Rate'])
    except:
        fallback = {"EURUSD": 1.0850, "GBPUSD": 1.2650, "USDJPY": 149.50}
        return fallback.get(pair, 1.0)

def decide_trade(sentiment, risk_level):
    if "HIGH" in risk_level:
        return "HOLD"
    if "позитивный" in sentiment:
        return "BUY"
    if "негативный" in sentiment:
        return "SELL"
    return "HOLD"

def execute_trade(action, pair, lot, data):
    price = get_current_price(pair)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    closed_pnl = 0.0
    new_trades = []
    for trade in data["trades"]:
        if trade["pair"] == pair:
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
    if action != "HOLD":
        data["trades"].append({
            "action": action,
            "pair": pair,
            "open_price": price,
            "lot": lot,
            "time": now
        })
    save_positions(data)
    return price, closed_pnl

# ============ ГЛАВНЫЙ ЦИКЛ ============

async def run_all():
    print("🔄 Запуск цикла...")

    # БОТ 1 — собираем данные
    news = get_news()
    sentiment, score = analyze_sentiment(news)
    fear_greed_str, fg_value = get_fear_greed()
    top_news = "\n".join([f"• {n}" for n in news[:3]]) if news else "• нет новостей"

    analyst_msg = f"""
📡 <b>Forex Аналитик — отчёт</b>

🌍 <b>Сентимент:</b> {sentiment}
😱 <b>Fear & Greed:</b> {fear_greed_str}

📰 <b>Новости:</b>
{top_news}

⏱ Следующий отчёт через 15 минут
    """
    await bot1.send_message(chat_id=GROUP_ID, message_thread_id=FOREX_THREAD_ID, text=analyst_msg, parse_mode='HTML')
    print("✅ Аналитик отправил отчёт")

    await asyncio.sleep(2)

    # БОТ 2 — оцениваем риск
    risk_level, recommendation, max_lot, risk_score = assess_risk(sentiment, score, fg_value)

    risk_msg = f"""
⚖️ <b>Risk Manager — оценка риска</b>

📊 <b>Уровень риска:</b> {risk_level}
🎯 <b>Риск-скор:</b> {risk_score}/100
💡 <b>Рекомендация:</b> {recommendation}
📦 <b>Макс. лот:</b> {max_lot}

⏱ Ожидаю решения трейдера...
    """
    await bot2.send_message(chat_id=GROUP_ID, message_thread_id=FOREX_THREAD_ID, text=risk_msg, parse_mode='HTML')
    print(f"✅ Риск-менеджер отправил оценку: {risk_level}")

    await asyncio.sleep(2)

    # БОТ 3 — принимаем решение и торгуем
    action = decide_trade(sentiment, risk_level)
    pair = FOREX_PAIRS[0]
    data = load_positions()
    price, closed_pnl = execute_trade(action, pair, max_lot, data)
    data = load_positions()

    open_positions = "\n".join([
        f"• {t['action']} {t['pair']} @ {t['open_price']:.5f} | лот: {t['lot']}"
        for t in data["trades"]
    ]) or "• нет открытых позиций"

    pnl_emoji = "🟢" if closed_pnl >= 0 else "🔴"

    trader_msg = f"""
💼 <b>Trader — исполнение</b>

🎯 <b>Действие:</b> {action}
💱 <b>Пара:</b> {pair}
💰 <b>Цена:</b> {price:.5f}
📦 <b>Лот:</b> {max_lot}

{pnl_emoji} <b>P&L закрытых:</b> ${closed_pnl:.2f}
💵 <b>Баланс:</b> ${data['balance']:.2f}
📈 <b>Общий P&L:</b> ${data['total_pnl']:.2f}

📂 <b>Открытые позиции:</b>
{open_positions}
    """
    await bot3.send_message(chat_id=GROUP_ID, message_thread_id=FOREX_THREAD_ID, text=trader_msg, parse_mode='HTML')
    print(f"✅ Трейдер выполнил: {action} {pair} @ {price:.5f}")

def job():
    asyncio.run(run_all())

scheduler = BlockingScheduler()
scheduler.add_job(job, 'interval', minutes=15)
print("🚀 Все боты запущены!")
job()
scheduler.start()
