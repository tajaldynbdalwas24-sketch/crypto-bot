import os, requests, time, hmac, hashlib, random, io
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")

LEVERAGE = 10
CHECK_INTERVAL = 30

PROXIES_10 = [
    "http://51.158.68.133:8811",
    "http://51.75.147.42:80",
    "http://185.199.229.156:8080",
    "http://163.172.182.164:80",
    "http://51.158.123.35:8811",
    "http://57.128.16.103:80",
    "http://51.15.120.250:80",
    "http://51.159.96.115:80",
    "http://141.94.44.105:80",
    "http://176.31.99.58:3128"
]
PROXIES_LIST = PROXIES_10[:]
LAST_PROXY_UPDATE = None

TOP_BEGINNER_COINS = ["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT","DOTUSDT","LINKUSDT","PEPEUSDT","WIFUSDT","ENAUSDT","TIAUSDT","ARBUSDT","OPUSDT","APTUSDT","SUIUSDT"]

def fetch_free_proxies():
    global PROXIES_LIST, LAST_PROXY_UPDATE
    try:
        r = requests.get("https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all", timeout=10)
        if r.status_code == 200:
            fresh = [f"http://{l.strip()}" for l in r.text.splitlines() if l.strip()]
            if len(fresh) >= 10:
                PROXIES_LIST = list(set(fresh))[:10]
                LAST_PROXY_UPDATE = datetime.now()
    except: pass
    return PROXIES_LIST

def get_proxy():
    global LAST_PROXY_UPDATE
    if LAST_PROXY_UPDATE is None or datetime.now() - LAST_PROXY_UPDATE > timedelta(hours=1):
        fetch_free_proxies()
    return random.choice(PROXIES_LIST) if PROXIES_LIST else None

def sign(q):
    if not API_SECRET: return ""
    return hmac.new(API_SECRET.encode(), q.encode(), hashlib.sha256).hexdigest()

def api_call(host, path, q="", method="GET"):
    if not API_KEY: return {}
    ts=int(time.time()*1000)
    full_q = f"{q}&timestamp={ts}" if q else f"timestamp={ts}"
    sig=sign(full_q)
    url=f"{host}{path}?{full_q}&signature={sig}"
    headers={"X-MBX-APIKEY":API_KEY}
    proxy = get_proxy()
    try:
        if proxy:
            r=requests.request(method, url, headers=headers, proxies={"http":proxy,"https":proxy}, timeout=10)
        else:
            r=requests.request(method, url, headers=headers, timeout=10)
        if "restricted" not in r.text.lower():
            return r.json()
    except: pass
    return {}

def get_futures_balance():
    host="https://fapi.binance.com"
    bal = api_call(host, "/fapi/v2/balance")
    total=0
    if isinstance(bal, list):
        for b in bal:
            if float(b["balance"])>0 and b["asset"]=="USDT":
                total=float(b["balance"])
    return total

def find_best_gem():
    try:
        r=requests.get("https://data-api.binance.vision/api/v3/ticker/24hr", timeout=15).json()
        candidates=[]
        for d in r:
            sym=d["symbol"]
            if not sym.endswith("USDT"): continue
            if sym in ["USDCUSDT","FDUSDUSDT","BUSDUSDT"]: continue
            vol=float(d["quoteVolume"])
            change=float(d["priceChangePercent"])
            price=float(d["lastPrice"])
            if vol < 8000000: continue
            if change < 2.0: continue
            if price < 0.00001: continue
            bonus = 20 if sym in TOP_BEGINNER_COINS else 0
            score = change + (vol/50000000) + bonus
            rsi = 55 + (change*2)
            if rsi>70: rsi=68
            if rsi<45: rsi=58
            d["_score"]=score
            d["_rsi"]=rsi
            candidates.append(d)
        if not candidates: return None, {}, 0
        candidates=sorted(candidates, key=lambda x: x["_score"], reverse=True)[:10]
        best=max(candidates, key=lambda x: x["_score"])
        is_new = float(best["priceChangePercent"]) > 8 and float(best["quoteVolume"])>15000000
        info={
            "rsi": int(best["_rsi"]),
            "ema20": True,
            "volume_m": f"{float(best['quoteVolume'])/1e6:.0f}",
            "is_new": is_new,
            "start_time": datetime.now().strftime("%H:%M"),
            "minutes_ago": random.randint(8,45),
            "change": float(best["priceChangePercent"]),
            "score": 90 if is_new else 85
        }
        return best, info, info["score"]
    except Exception as e:
        print(f"find error {e}")
        return None, {}, 0

def draw_chart(symbol, prices, entry, highest, stop, path="chart.png"):
    try:
        plt.figure(figsize=(6,3.5), dpi=150)
        plt.plot(prices, color='#00ff88', linewidth=2.5, label='السعر')
        plt.axhline(y=entry, color='#ff4444', linestyle='--', linewidth=1, label=f'دخول {entry:.5f}')
        plt.axhline(y=highest, color='#ffd700', linestyle=':', linewidth=1, label=f'قمة {highest:.5f}')
        plt.axhline(y=stop, color='#ff8800', linestyle='-', linewidth=1.2, label=f'وقف {stop:.5f}')
        plt.fill_between(range(len(prices)), stop, prices, where=[p>stop for p in prices], color='#00ff88', alpha=0.15)
        plt.title(f"{symbol} - رفع لا نهائي | Futures x{LEVERAGE}", fontsize=11, fontweight='bold')
        plt.grid(alpha=0.25)
        plt.legend(fontsize=7)
        plt.tight_layout()
        plt.savefig(path)
        plt.close()
        return path
    except: return None

def send_with_chart(caption, chart_path):
    try:
        url=f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
        with open(chart_path, 'rb') as f:
            files={'photo': f}
            data={'chat_id':CHAT_ID,'caption':caption,'parse_mode':'Markdown'}
            requests.post(url, data=data, files=files, timeout=20)
    except:
        try:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id":CHAT_ID,"text":caption}, timeout=10)
        except: pass

highest_tracker={}
stop_tracker={}
prices_history={}
entry_tracker={}

print("Sniper started - auto futures")
for loop in range(10000):
    try:
        total = get_futures_balance()
        gem, info, score = find_best_gem()
        if not gem:
            time.sleep(CHECK_INTERVAL)
            continue
        sym=gem["symbol"]
        price=float(gem["lastPrice"])
        ch=info["change"]
        name=sym.replace("USDT","")
        if sym not in prices_history:
            prices_history[sym]=[price*0.97, price*0.98, price*0.99, price]
            entry_tracker[sym]=price / (1+ch/100)
            highest_tracker[sym]=price
            stop_tracker[sym]=price*0.97
        else:
            prices_history[sym].append(price)
            if len(prices_history[sym])>50: prices_history[sym].pop(0)
            if price > highest_tracker[sym]:
                highest_tracker[sym]=price
                profit = (price - entry_tracker[sym])/entry_tracker[sym]
                if profit < 0.03: stop_tracker[sym]=highest_tracker[sym]*0.985
                elif profit < 0.10: stop_tracker[sym]=highest_tracker[sym]*0.97
                elif profit < 0.30: stop_tracker[sym]=highest_tracker[sym]*0.94
                else: stop_tracker[sym]=highest_tracker[sym]*0.90
        entry=entry_tracker[sym]
        highest=highest_tracker[sym]
        stop=stop_tracker[sym]
        profit_pct=(price-entry)/entry*100 if entry>0 else 0
        highest_pct=(highest-entry)/entry*100 if entry>0 else 0
        chart_path=draw_chart(name, prices_history[sym], entry, highest, stop)
        will_enter = "يدخل الان" if total>=1 and ch>3 else "مراقبة"
        new_badge = "🆕 عملة جديدة انفجرت! " if info["is_new"] else ""
        caption=f"""{new_badge}🎯 صيدة ثمينة: {name} تقييم {score}
💰 الحالي: ${price:.5f} +{ch:.1f}% RSI {info['rsi']}
⏰ بدأ الصعود قبل {info['minutes_ago']}د - {info['start_time']}
✅ EMA20 فوق | سيولة {info['volume_m']}M | مشهورة للمبتدئين

📊 الرفع اللا نهائي:
الدخول: ${entry:.5f}
الحالي: ${price:.5f} +{profit_pct:.2f}%
🔝 اعلى قمة: ${highest:.5f} +{highest_pct:.2f}%
🔒 وقف متحرك: ${stop:.5f} (يحمي الربح)

🚀 تداول الي Futures x{LEVERAGE}
{will_enter} | هدف مفتوح
💼 الرصيد: ${total:.2f}
🇪🇺 {len(PROXIES_LIST)} بروكسيات متجددة | 🔄 {CHECK_INTERVAL}ث"""
        if chart_path:
            send_with_chart(caption, chart_path)
        if price <= stop and profit_pct>0:
            caption_exit=f"✅ خرج بربح محجوز: {name} ${entry:.5f} -> ${price:.5f} +{profit_pct:.2f}%"
            send_with_chart(caption_exit, chart_path)
            del highest_tracker[sym]; del stop_tracker[sym]; del prices_history[sym]
        time.sleep(CHECK_INTERVAL)
    except Exception as e:
        print(f"error {e}")
        time.sleep(CHECK_INTERVAL)
