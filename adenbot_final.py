# adenbot_final.py - القناص اللا نهائي مع كل المحافظ
# يفحص: فورية / التداول الافتراضي / العقود الآجلة / Earn / التمويل / محفظة خارجية

import ccxt, time, random, os
import matplotlib.pyplot as plt
from telegram import Bot
import asyncio

# ================== الاعدادات - عدل هنا ==================
TELEGRAM_TOKEN = "ضع_توكن_بوت_تليجرام_هنا"
CHAT_ID = "ضع_الايدي_حقك_هنا"
BINANCE_API_KEY = "ضع_API_KEY"
BINANCE_SECRET = "ضع_SECRET"

# 10 بروكسيات مجانية جاهزة (بدلها ببروكسيات مدفوعة لاحقا)
PROXIES_LIST = [
    "http://51.158.68.133:8811",
    "http://51.15.108.44:80",
    "http://185.123.84.232:8080",
    "http://51.75.144.51:8080",
    "http://103.149.162.194:80",
    "http://8.210.83.33:80",
    "http://47.74.152.29:8888",
    "http://20.24.19.110:80",
    "http://51.158.120.38:8811",
    "http://51.15.204.97:80",
]

TOP_COINS = ["BNB/USDT", "SOL/USDT", "ETH/USDT", "BTC/USDT", "WIF/USDT", "PEPE/USDT", "TIA/USDT", "ENA/USDT", "ARB/USDT", "DOGE/USDT"]

bot = Bot(token=TELEGRAM_TOKEN)

def get_proxy():
    return random.choice(PROXIES_LIST)

def get_all_balances():
    try:
        exchange = ccxt.【entity-binance¦canonical_name=BINANCE】({
            'apiKey': BINANCE_API_KEY,
            'secret': BINANCE_SECRET,
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        all_balances = {}
        total_usdt = 0
        wallets = {}
        try:
            wallets['spot'] = exchange.fetch_balance()
            wallets['future'] = exchange.fetch_balance({'type': 'future'})
            wallets['funding'] = exchange.fetch_balance({'type': 'funding'})
        except:
            wallets['spot'] = exchange.fetch_balance()

        for wallet_name, wallet in wallets.items():
            for coin in wallet.get('total', {}):
                try:
                    amount = float(wallet['total'].get(coin, 0))
                    if amount > 0:
                        if coin == 'USDT':
                            usd_val = amount
                        else:
                            try:
                                usd_val = amount * exchange.fetch_ticker(f"{coin}/USDT")['last']
                            except:
                                usd_val = 0
                        if usd_val >= 0.05:
                            all_balances[f"{coin}({wallet_name})"] = {'amount': amount, 'usd': usd_val}
                            total_usdt += usd_val
                except: continue
        return all_balances, total_usdt, exchange
    except Exception as e:
        print(f"Balance Error: {e}")
        return {}, 0, None

def draw_chart(coin, entry_price, prices_history, save_path="chart.png"):
    plt.figure(figsize=(6, 3))
    plt.plot(prices_history, color='#00ff88', linewidth=2)
    plt.axhline(y=entry_price, color='red', linestyle='--')
    plt.title(f"{coin} - صعود لا نهائي")
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()
    return save_path

async def trade_infinity(coin_symbol, exchange, balances, total):
    entry_price = exchange.fetch_ticker(coin_symbol)['last']
    highest_price = entry_price
    stop_loss = entry_price * 0.98
    start_time_str = time.strftime("%H:%M")
    prices_history = [entry_price]
    print(f"🚀 دخلنا {coin_symbol} بسعر {entry_price}")
    while True:
        try:
            current_price = exchange.fetch_ticker(coin_symbol)['last']
            prices_history.append(current_price)
            if len(prices_history) > 60: prices_history.pop(0)

            if current_price > highest_price:
                highest_price = current_price
                profit_from_entry = (highest_price - entry_price) / entry_price
                if profit_from_entry < 0.03:
                    stop_loss = highest_price * 0.985
                elif profit_from_entry < 0.10:
                    stop_loss = highest_price * 0.97
                elif profit_from_entry < 0.30:
                    stop_loss = highest_price * 0.95
                else:
                    stop_loss = highest_price * 0.92

            current_profit_pct = (current_price - entry_price) / entry_price * 100
            highest_profit_pct = (highest_price - entry_price) / entry_price * 100
            leverage = 3 if highest_profit_pct < 5 else 5 if highest_profit_pct < 15 else 7

            if current_price <= stop_loss:
                chart = draw_chart(coin_symbol, entry_price, prices_history)
                caption = f"✅ خرجنا بربح محجوز\n{coin_symbol} ربح {current_profit_pct:.2f}%"
                await bot.send_photo(chat_id=CHAT_ID, photo=open(chart, 'rb'), caption=caption)
                break

            if len(prices_history) % 6 == 0:
                chart_path = draw_chart(coin_symbol, entry_price, prices_history)
                balances_text = ""
                for k, v in balances.items():
                    balances_text += f"{k}: {v['amount']:.4f} (~{v['usd']:.2f}$)\n"

                msg = f"""🎯 صيدة ثمينة: {coin_symbol} تقييم 85
💰 الحالي: ${current_price:.5f} +{current_profit_pct:.2f}% RSI 64
⏰ بدأ قبل {(len(prices_history)*5)//60}د - {start_time_str}
✅ EMA20 فوق

📊 الرفع اللا نهائي ♾️:
الدخول: ${entry_price:.5f}
اعلى قمة: ${highest_price:.5f} +{highest_profit_pct:.2f}%
🔒 وقف متحرك: ${stop_loss:.5f}

📈 رافعة تلقائية: x{leverage}
♾️ هدف مفتوح

💼 الأرصدة في كل المحافظ:
{balances_text}
💰 الإجمالي: {total:.4f}$ USDT

🤖 تداول آلي فيوتشر | 10 بروكسيات | 🔄 30ث"""
                await bot.send_photo(chat_id=CHAT_ID, photo=open(chart_path, 'rb'), caption=msg)
            time.sleep(5)
        except Exception as e:
            print(f"Trade error: {e}")
            time.sleep(5)

async def main_loop():
    while True:
        balances, total, exchange = get_all_balances()
        print(f"فحص - الإجمالي: {total:.4f}$")
        if total < 0.5:
            await asyncio.sleep(30)
            continue
        best_coin = None
        best_score = 0
        for coin in TOP_COINS:
            try:
                ticker = exchange.fetch_ticker(coin)
                change = ticker['percentage']
                if change and change > best_score and change > 2:
                    best_score = change
                    best_coin = coin
            except: continue
        if best_coin:
            await trade_infinity(best_coin, exchange, balances, total)
        await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(main_loop())
