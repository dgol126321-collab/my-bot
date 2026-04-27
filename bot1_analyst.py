import feedparser
import requests
import asyncio
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from telegram import Bot
from apscheduler.schedulers.blocking import BlockingScheduler
import sys
sys.path.insert(0, '/home/dawid/trading_bots')
from config import BOT1_TOKEN, YOUR_CHAT_ID, ALPHA_VANTAGE_KEY, GROUP_ID, FOREX_THREAD_ID

bot = Bot(token=BOT1_TOKEN)
analyzer = SentimentIntensityAnalyzer()

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
        return f"{value} ({label})"
    except:
        return "недоступен"

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

async def send_report():
    news = get_news()
    sentiment, score = analyze_sentiment(news)
    fear_greed = get_fear_greed()
    top_news = "\n".join([f"• {n}" for n in news[:3]]) if news else "• нет новостей"

    message = f"""
📡 <b>Forex Аналитик — отчёт</b>

🌍 <b>Сентимент:</b> {sentiment}
😱 <b>Fear & Greed:</b> {fear_greed}

📰 <b>Новости:</b>
{top_news}

⏱ Следующий отчёт через 15 минут
    """

    await bot.send_message(
        chat_id=GROUP_ID,
        message_thread_id=FOREX_THREAD_ID,
        text=message,
        parse_mode='HTML'
    )
    print("Отчёт отправлен в топик!")

def job():
    asyncio.run(send_report())

scheduler = BlockingScheduler()
scheduler.add_job(job, 'interval', minutes=15)
print("Бот 1 запущен!")
job()
scheduler.start()
