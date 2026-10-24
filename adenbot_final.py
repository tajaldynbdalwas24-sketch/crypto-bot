import os, requests, time, hmac, hashlib, random, json
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

# === الأزرار الثلاثة ===
USE_ATR_STOP = True
SIGNAL_ONLY = True
USE_WEBHOOK = False
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

PROXIES_10 = ["http://51.158.68.133:8811","http://51.75.147.42:80","http://185.199.229.156:8080","http://163.172.182.164:80","http://51.158.123.35:8811","http://57.128.16.103:80","http://51.15.120.250:80","http://51.159.96.115:80","http://141.94.44.105:80","http://176.31.99.58:3128"]
PROXIES_LIST = PROXIES_10[:]
LAST_PROXY_UPDATE=None
TOP_BEGINNER_COINS=["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT","DOTUSDT","LINKUSDT","PEPEUSDT","WIFUSDT","ENAUSDT","TIAUSDT","ARBUSDT","OPUSDT","APTUSDT","SUIUSDT"]

def fetch_free_proxies():
    global PROXIES_LIST, LAST_PROXY_UPDATE
    try:
        r=requests.get("https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all",timeout=10)
        if r.status_code==200:
            fresh=[f"http://{l.strip()}" for l in r.text.splitlines() if l.strip()]
            if len(fresh)>=10:
                PROXIES_LIST=list(set(fresh))[:10]
                LAST_PROXY_UPDATE=datetime.now()
    except: pass

def get_proxy():
    global LAST_PROXY_UPDATE
    if LAST_PROXY_UPDATE is None or datetime.now()-LAST_PROXY_UPDATE>timedelta(hours=1):
        fetch_free_proxies()
    return random.choice(PROXIES_LIST) if PROXIES_LIST else None

def sign(q):
    if not API_SECRET: return ""
    return hmac.new(API_SECRET.encode(), q.encode(), hashlib.sha256).hexdigest()

def api_call(host,path,q="",method="GET"):
    if not API_KEY: return {}
    ts=int(time.time()*1000)
    full_q=f"{q}&timestamp={ts}" if q else f"timestamp={ts}"
    sig=sign(full_q)
    url=f"{host}{path}?{full_q}&signature={sig}"
    headers={"X-MBX-APIKEY":API_KEY}
    proxy=get_proxy()
    try:
        if proxy:
            r=requests.request(method,url,headers=headers,proxies={"http":proxy,"https":proxy},timeout=10)
        else:
            r=requests.request(method,url,headers=headers,timeout=10)
        if "restricted" not in r.text.lower():
            return r.json()
    except: pass
    return {}

def get_all_wallets_once():
    wallets={}; total=0; bnb_total=0
    host_spot="https://api.binance.com"
    try:
        user_assets = api_call(host_spot, "/sapi/v1/asset/getUserAsset")
        if isinstance(user_assets, list):
            for b in user_assets:
                free=float(b.get("free",0)); locked=float(b.get("locked",0)); freeze=float(b.get("freeze",0))
                all_amt=free+locked+freeze
                if all_amt>0:
                    asset=b.get("asset","")
                    usd=all_amt
                    if asset!="USDT":
                        try:
                            tk=requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={asset}USDT",timeout=3).json()
                            usd=all_amt*float(tk.get("price",0))
                        except: usd=0
                    if usd>=0.0001:
                        wallets[asset]={"amount":all_amt,"usd":usd}
                        total+=usd
                        if asset=="BNB": bnb_total+=usd
    except: pass
    return wallets,total,bnb_total

def calc_atr(klines, period=14):
    try:
        tr_list=[]
        for i in range(1, len(klines)):
            high=float(klines[i][2]); low=float(klines[i][3]); prev_close=float(klines[i-1][4])
            tr=max(high-low, abs(high-prev_close), abs(low-prev_close))
            tr_list.append(tr)
        if len(tr_list)<period: return sum(tr_list)/len(tr_list) if tr_list else 0
        return sum(tr_list[-period:])/period
    except: return 0

def get_indicators(symbol):
    try:
        url=f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1h&limit=50"
        kl=requests.get(url,timeout=8).json()
        if not isinstance(kl,list) or len(kl)<26: return None
        closes=[float(k[4]) for k in kl]
        volumes=[float(k[5]) for k in kl]
        ema20=sum(closes[-20:])/20
        price=closes[-1]
        ema_signal=price>ema20
        deltas=[closes[i]-closes[i-1] for i in range(1,len(closes))]
        gains=[d if d>0 else 0 for d in deltas[-14:]]
        losses=[-d if d<0 else 0 for d in deltas[-14:]]
        avg_gain=sum(gains)/14 if gains else 0.01
        avg_loss=sum(losses)/14 if losses else 0.01
        rs=avg_gain/(avg_loss if avg_loss!=0 else 0.01)
        rsi=100-(100/(1+rs))
        vol_now=volumes[-1]; vol_avg=sum(volumes[-10:-1])/9 if len(volumes)>10 else vol_now
        vol_trend=vol_now/vol_avg if vol_avg>0 else 1
        ema12=sum(closes[-12:])/12; ema26=sum(closes[-26:])/26
        macd=ema12-ema26
        atr=calc_atr(kl, 14)
        return {"ema20":ema20,"ema_signal":ema_signal,"rsi":rsi,"vol_trend":vol_trend,"macd":macd,"macd_signal":macd>0,"price":price,"closes":closes,"klines":kl,"atr":atr}
    except: return None

last_coins={}
def find_top_coins():
    try:
        r=requests.get("https://api.binance.com/api/v3/ticker/24hr",timeout=15).json()
        all_sorted=sorted(r,key=lambda x: float(x.get("quoteVolume",0)),reverse=True)[:150]
        candidates=[]
        for d in all_sorted:
            sym=d["symbol"]
            if not sym.endswith("USDT"): continue
            if sym in ["USDCUSDT","FDUSDUSDT","BUSDUSDT"]: continue
            vol=float(d["quoteVolume"]); change=float(d["priceChangePercent"]); price=float(d["lastPrice"])
            if vol<5000000 or price<0.000001 or change<1.5: continue
            if sym in last_coins and (datetime.now()-last_coins[sym]).total_seconds()<600: continue
            ind=get_indicators(sym)
            if not ind or ind["rsi"]>78 or ind["rsi"]<38 or not ind["ema_signal"] or ind["vol_trend"]<1.1: continue
            bonus=60 if sym=="BNBUSDT" else (25 if sym in TOP_BEGINNER_COINS else 0)
            trending_score=change*2+ind["vol_trend"]*10+(ind["rsi"]-50)+(10 if ind["macd_signal"] else 0)
            score=trending_score+bonus+(vol/30000000)
            candidates.append({"symbol":sym,"price":price,"change":change,"vol":vol,"ind":ind,"score":score})
        if not candidates: return []
        return sorted(candidates,key=lambda x: x["score"],reverse=True)[:5]
    except: return []

def draw_chart(symbol, closes, entry, highest, stop, atr, path="chart.png"):
    try:
        plt.figure(figsize=(6,3.5),dpi=160)
        plt.plot(closes[-40:],color='#00ff88',linewidth=2.2,label='Price')
        plt.axhline(y=entry,color='#ff4444',linestyle='--',linewidth=1,label=f'Entry {entry:.5f}')
        plt.axhline(y=highest,color='#ffd700',linestyle=':',linewidth=1,label=f'Peak {highest:.5f}')
        plt.axhline(y=stop,color='#ff8800',linestyle='-',linewidth=1.5,label=f'ATR Stop {stop:.5f}')
        plt.fill_between(range(len(closes[-40:])), stop, closes[-40:], where=[p>stop for p in closes[-40:]], color='#00ff88', alpha=0.15)
        plt.title(f"{symbol} ATR {atr:.4f} | BNB",fontsize=10,fontweight='bold')
        plt.grid(alpha=0.25); plt.legend(fontsize=7); plt.tight_layout(); plt.savefig(path); plt.close()
        return path
    except: return None

def send_telegram(caption, chart_path):
    try:
        url=f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
        if chart_path and os.path.exists(chart_path):
            with open(chart_path,'rb') as f:
                requests.post(url,data={'chat_id':CHAT_ID,'caption':caption,'parse_mode':'Markdown'},files={'photo':f},timeout=20)
        else:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",data={"chat_id":CHAT_ID,"text":caption},timeout=10)
    except: pass

def send_webhook(data):
    if not WEBHOOK_URL: return
    try:
        requests.post(WEBHOOK_URL, json=data, timeout=10)
    except: pass

print(f"Sniper V6 - ATR={USE_ATR_STOP} SIGNAL_ONLY={SIGNAL_ONLY} WEBHOOK={USE_WEBHOOK}")
wallets_cache, total_cache, bnb_cache = get_all_wallets_once() if SIGNAL_ONLY else ({},0,0)

highest_tracker={}; stop_tracker={}; entry_tracker={}; prices_history={}
for loop in range(10000):
    try:
        if SIGNAL_ONLY:
            wallets,total,bnb_total = wallets_cache,total_cache,bnb_cache
        else:
            wallets,total,bnb_total = get_all_wallets_once()
        top_list=find_top_coins()
        if not top_list:
            time.sleep(CHECK_INTERVAL)
            continue
        for coin_data in top_list[:3]:
            sym=coin_data["symbol"]; price=coin_data["price"]; ch=coin_data["change"]; ind=coin_data["ind"]; score=coin_data["score"]
            name=sym.replace("USDT","")
            last_coins[sym]=datetime.now()
            if sym not in prices_history:
                prices_history[sym]=ind["closes"][-20:]
                entry_tracker[sym]=price/(1+ch/100) if ch!=0 else price*0.98
                highest_tracker[sym]=price
                atr_val=ind["atr"] if ind["atr"]>0 else price*0.02
                stop_tracker[sym]=price - (atr_val*1.5) if USE_ATR_STOP else price*0.97
            else:
                prices_history[sym].append(price)
                if len(prices_history[sym])>60: prices_history[sym].pop(0)
                if price>highest_tracker[sym]:
                    highest_tracker[sym]=price
                    atr_val=ind["atr"] if ind["atr"]>0 else price*0.02
                    profit=(price-entry_tracker[sym])/entry_tracker[sym]
                    if USE_ATR_STOP:
                        mult = 1.5 if profit<0.03 else 2.0 if profit<0.10 else 2.5
                        stop_tracker[sym]=highest_tracker[sym] - (atr_val*mult)
                    else:
                        if profit<0.03: stop_tracker[sym]=highest_tracker[sym]*0.985
                        elif profit<0.10: stop_tracker[sym]=highest_tracker[sym]*0.97
                        else: stop_tracker[sym]=highest_tracker[sym]*0.94
            entry=entry_tracker[sym]; highest=highest_tracker[sym]; stop=stop_tracker[sym]
            profit_pct=(price-entry)/entry*100 if entry>0 else 0
            atr_val=ind["atr"]
            chart_path=draw_chart(name, ind["closes"], entry, highest, stop, atr_val)
            webhook_data={"symbol":sym,"price":price,"change":ch,"rsi":round(ind["rsi"],1),"atr":atr_val,"stop_atr":stop,"entry":entry,"signal":"LONG","time":datetime.now().strftime("%H:%M:%S")}
            if USE_WEBHOOK and WEBHOOK_URL:
                send_webhook(webhook_data)
            if SIGNAL_ONLY:
                caption=f"""🆕🔥 {name} تقييم {score:.0f} | {ch:.1f}% ترند
🎯 دخول: ${price:.5f}
📊 RSI {ind['rsi']:.0f} | EMA20 فوق ✅ | MACD صاعد
📈 ATR {atr_val:.4f} | وقف ATR: ${stop:.5f}
💰 دخول {entry:.5f} -> حالي {price:.5f} +{profit_pct:.2f}%
🔒 وقف متحرك ATR ديناميكي
🚀 Futures x{LEVERAGE} | إشارة فقط"""
            else:
                caption=f"""🚀 {name} {score:.0f} | ${price:.5f} +{ch:.1f}% | ATR {atr_val:.4f} | وقف ${stop:.5f}"""
            if not USE_WEBHOOK:
                send_telegram(caption, chart_path)
            time.sleep(2)
        time.sleep(CHECK_INTERVAL)
    except Exception as e:
        print(f"Main {e}")
        time.sleep(CHECK_INTERVAL)
