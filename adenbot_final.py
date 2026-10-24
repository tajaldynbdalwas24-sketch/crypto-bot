import os, requests, time, hmac, hashlib, random
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
USE_ATR_STOP = True
SIGNAL_ONLY = True
USE_WEBHOOK = False
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

PROXIES_10 = ["http://51.158.68.133:8811","http://51.75.147.42:80","http://185.199.229.156:8080","http://163.172.182.164:80","http://51.158.123.35:8811"]
PROXIES_LIST = PROXIES_10[:]
TOP_BEGINNER_COINS=["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT","DOTUSDT","LINKUSDT"]

def send_startup():
    try:
        msg=f"✅ بوت V6 اشتغل\nATR={USE_ATR_STOP} SIGNAL={SIGNAL_ONLY}\nالوقت {datetime.now().strftime('%H:%M:%S')}\nبيدور على عملات ترند..."
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",data={"chat_id":CHAT_ID,"text":msg},timeout=10)
        print("Startup sent")
    except Exception as e:
        print(f"Startup fail {e}")

send_startup()

# باقي الكود نفس V6
def sign(q):
    return hmac.new(API_SECRET.encode(), q.encode(), hashlib.sha256).hexdigest() if API_SECRET else ""
def api_call(host,path,q="",method="GET"):
    if not API_KEY: return {}
    ts=int(time.time()*1000)
    full_q=f"{q}&timestamp={ts}" if q else f"timestamp={ts}"
    sig=sign(full_q)
    url=f"{host}{path}?{full_q}&signature={sig}"
    try:
        r=requests.get(url,headers={"X-MBX-APIKEY":API_KEY},timeout=10)
        return r.json()
    except: return {}
def get_all_wallets_once():
    wallets={}; total=0; bnb_total=0
    try:
        user_assets = api_call("https://api.binance.com", "/sapi/v1/asset/getUserAsset")
        if isinstance(user_assets, list):
            for b in user_assets:
                amt=float(b.get("free",0))+float(b.get("locked",0))
                if amt>0 and b.get("asset")=="BNB":
                    bnb_total=amt*600
    except: pass
    return {},total,bnb_total
def calc_atr(klines, period=14):
    try:
        tr=[]
        for i in range(1,len(klines)):
            h=float(klines[i][2]); l=float(klines[i][3]); pc=float(klines[i-1][4])
            tr.append(max(h-l, abs(h-pc), abs(l-pc)))
        return sum(tr[-period:])/period if tr else 0
    except: return 0
def get_indicators(symbol):
    try:
        kl=requests.get(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1h&limit=50",timeout=8).json()
        if not isinstance(kl,list) or len(kl)<26: return None
        closes=[float(k[4]) for k in kl]
        volumes=[float(k[5]) for k in kl]
        ema20=sum(closes[-20:])/20
        price=closes[-1]
        deltas=[closes[i]-closes[i-1] for i in range(1,len(closes))]
        gains=[d if d>0 else 0 for d in deltas[-14:]]
        losses=[-d if d<0 else 0 for d in deltas[-14:]]
        rs=(sum(gains)/14)/((sum(losses)/14) if sum(losses)!=0 else 0.01)
        rsi=100-(100/(1+rs))
        vol_trend=volumes[-1]/(sum(volumes[-10:-1])/9)
        atr=calc_atr(kl,14)
        return {"ema20":ema20,"price":price,"rsi":rsi,"vol_trend":vol_trend,"closes":closes,"atr":atr,"ema_signal":price>ema20}
    except: return None

last_coins={}
highest_tracker={}; stop_tracker={}; entry_tracker={}; prices_history={}
wallets_cache,total_cache,bnb_cache=get_all_wallets_once()

for loop in range(10000):
    try:
        print(f"Loop {loop} scanning...")
        r=requests.get("https://api.binance.com/api/v3/ticker/24hr",timeout=15).json()
        all_sorted=sorted(r,key=lambda x: float(x.get("quoteVolume",0)),reverse=True)[:100]
        sent=False
        for d in all_sorted:
            sym=d["symbol"]
            if not sym.endswith("USDT") or sym in last_coins: continue
            vol=float(d["quoteVolume"]); change=float(d["priceChangePercent"]); price=float(d["lastPrice"])
            if vol<3000000 or change<1: continue
            ind=get_indicators(sym)
            if not ind or ind["rsi"]>75 or ind["rsi"]<35: continue
            if not ind["ema_signal"]: continue
            name=sym.replace("USDT","")
            score=change*2+ind["vol_trend"]*5
            if sym not in prices_history:
                entry_tracker[sym]=price*0.98
                highest_tracker[sym]=price
                stop_tracker[sym]=price - (ind["atr"]*1.5) if USE_ATR_STOP else price*0.97
                prices_history[sym]=ind["closes"]
            profit=(price-entry_tracker[sym])/entry_tracker[sym]*100
            caption=f"🔥 {name} {change:.1f}% ترند\n🎯 دخول ${price:.5f}\nRSI {ind['rsi']:.0f} | ATR {ind['atr']:.4f}\nوقف ATR ${stop_tracker[sym]:.5f} | ربح +{profit:.2f}%\nFutures x{LEVERAGE} | {datetime.now().strftime('%H:%M')}"
            # رسم
            try:
                plt.figure(figsize=(5,3))
                plt.plot(ind["closes"][-30:],color='#00ff88')
                plt.axhline(y=stop_tracker[sym],color='red',linestyle='--')
                plt.savefig("chart.png"); plt.close()
                with open("chart.png",'rb') as f:
                    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendPhoto",data={'chat_id':CHAT_ID,'caption':caption},files={'photo':f},timeout=20)
            except:
                requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",data={"chat_id":CHAT_ID,"text":caption},timeout=10)
            last_coins[sym]=True
            sent=True
            time.sleep(2)
            if sent: break
        if not sent:
            print("No coin matched, waiting")
        time.sleep(CHECK_INTERVAL)
    except Exception as e:
        print(f"Error {e}")
        time.sleep(10)
