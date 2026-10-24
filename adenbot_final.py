import os, requests, time, hmac, hashlib, random
from datetime import datetime
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
SHOW_BALANCE = True  # <-- هذا يظهر رصيدك الحقيقي
USE_WEBHOOK = False
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

def sign(q):
    return hmac.new(API_SECRET.encode(), q.encode(), hashlib.sha256).hexdigest() if API_SECRET else ""

def api_call(path, q=""):
    if not API_KEY: return None
    ts=int(time.time()*1000)
    full_q=f"{q}&timestamp={ts}" if q else f"timestamp={ts}"
    sig=sign(full_q)
    url=f"https://api.binance.com{path}?{full_q}&signature={sig}"
    headers={"X-MBX-APIKEY":API_KEY}
    try:
        r=requests.get(url,headers=headers,timeout=10)
        data=r.json()
        print(f"API {path}: {str(data)[:200]}")
        return data
    except Exception as e:
        print(f"API fail {e}")
        return None

def get_real_balance():
    wallets={}; total=0; bnb=0
    # 1- جرب getUserAsset (يجيب كل المحافظ حتى التمويل)
    data = api_call("/sapi/v1/asset/getUserAsset")
    if isinstance(data, list) and len(data)>0:
        for b in data:
            asset=b.get("asset","")
            amt=float(b.get("free",0))+float(b.get("locked",0))+float(b.get("freeze",0))+float(b.get("withdrawing",0))
            if amt>0:
                usd=amt
                if asset!="USDT":
                    try:
                        p=requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={asset}USDT",timeout=3).json()
                        usd=amt*float(p.get("price",0))
                    except:
                        if asset=="BNB": usd=amt*600
                if usd>=0.0001:
                    wallets[asset]={"amt":amt,"usd":usd}
                    total+=usd
                    if asset=="BNB": bnb+=usd
        if total>0:
            print(f"Balance from getUserAsset: ${total:.4f}")
            return wallets,total,bnb
    # 2- fallback: spot account
    data2 = api_call("/api/v3/account")
    if data2 and "balances" in data2:
        for b in data2["balances"]:
            asset=b["asset"]
            amt=float(b["free"])+float(b["locked"])
            if amt>0:
                usd=amt
                if asset!="USDT":
                    try:
                        p=requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={asset}USDT",timeout=3).json()
                        usd=amt*float(p.get("price",0))
                    except: continue
                if usd>=0.0001:
                    wallets[asset]={"amt":amt,"usd":usd}
                    total+=usd
                    if asset=="BNB": bnb+=usd
    return wallets,total,bnb

def calc_atr(klines, period=14):
    try:
        tr=[]
        for i in range(1,len(klines)):
            h=float(klines[i][2]); l=float(klines[i][3]); pc=float(klines[i-1][4])
            tr.append(max(h-l, abs(h-pc), abs(l-pc)))
        return sum(tr[-period:])/period if len(tr)>=period else sum(tr)/len(tr) if tr else 0
    except: return 0

def get_indicators(symbol):
    try:
        kl=requests.get(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1h&limit=50",timeout=8).json()
        if not isinstance(kl,list) or len(kl)<26: return None
        closes=[float(k[4]) for k in kl]
        ema20=sum(closes[-20:])/20
        price=closes[-1]
        deltas=[closes[i]-closes[i-1] for i in range(1,len(closes))]
        gains=[d if d>0 else 0 for d in deltas[-14:]]
        losses=[-d if d<0 else 0 for d in deltas[-14:]]
        rs=(sum(gains)/14)/((sum(losses)/14) if sum(losses)!=0 else 0.01)
        rsi=100-(100/(1+rs))
        vol=requests.get(f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}",timeout=5).json()
        atr=calc_atr(kl,14)
        return {"price":price,"closes":closes,"ema20":ema20,"rsi":rsi,"atr":atr,"change":float(vol.get("priceChangePercent",0)),"ema_signal":price>ema20}
    except: return None

# رسالة بدء مع رصيدك
def send_startup():
    wallets,total,bnb = get_real_balance()
    lines=[f"{k}: {v['amt']:.6f} (~${v['usd']:.4f})" for k,v in wallets.items()]
    txt_bal="\n".join(lines) if lines else "ما لقى رصيد - تأكد من صلاحية القراءة في API"
    msg=f"✅ V6.3 اشتغل\n💰 رصيدك الحقيقي: ${total:.4f}\n{txt_bal}\nBNB ~${bnb:.4f}\nATR={USE_ATR_STOP} | يبدأ البحث..."
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",data={"chat_id":CHAT_ID,"text":msg},timeout=10)
        print(msg)
    except: pass
    return wallets,total,bnb

wallets,total,bnb = send_startup()

highest={}; stop={}; entry={}; last_coins={}

for loop in range(10000):
    try:
        wallets,total,bnb = get_real_balance()
        r=requests.get("https://api.binance.com/api/v3/ticker/24hr",timeout=15).json()
        top=sorted(r,key=lambda x: float(x.get("quoteVolume",0)),reverse=True)[:120]
        for d in top:
            sym=d["symbol"]
            if not sym.endswith("USDT") or sym in ["USDCUSDT","FDUSDUSDT"]: continue
            if sym in last_coins and (datetime.now()-last_coins[sym]).seconds<600: continue
            vol=float(d["quoteVolume"]); change=float(d["priceChangePercent"])
            if vol<4000000 or change<1.2: continue
            ind=get_indicators(sym)
            if not ind or ind["rsi"]>77 or ind["rsi"]<37 or not ind["ema_signal"]: continue
            name=sym.replace("USDT","")
            price=ind["price"]; ch=ind["change"]
            if sym not in highest:
                highest[sym]=price
                entry[sym]=price*0.98
                stop[sym]=price - (ind["atr"]*1.5) if USE_ATR_STOP else price*0.97
            else:
                if price>highest[sym]:
                    highest[sym]=price
                    stop[sym]=highest[sym] - (ind["atr"]*2.0) if USE_ATR_STOP else highest[sym]*0.97
            profit=(price-entry[sym])/entry[sym]*100
            bal_text="\n".join([f"{'⭐' if 'BNB' in k else '•'} {k}: {v['amt']:.5f} (~${v['usd']:.4f})" for k,v in wallets.items()]) or f"${total:.4f}"
            caption=f"🚀 {name} تقييم +{ch:.1f}% ترند\n🎯 دخول ${price:.5f}\n📊 RSI {ind['rsi']:.0f} | EMA20 ${ind['ema20']:.2f} فوق ✅\n📈 ATR {ind['atr']:.4f} | وقف ATR ${stop[sym]:.5f}\n💰 دخول {entry[sym]:.5f} -> حالي {price:.5f} +{profit:.2f}%\n🔝 قمة {highest[sym]:.5f}\n\n💼 رصيدك:\n{bal_text}\n💰 إجمالي ${total:.4f} | BNB ${bnb:.4f}\n🚀 Futures x{LEVERAGE}"
            try:
                plt.figure(figsize=(5,3),dpi=150)
                plt.plot(ind["closes"][-40:],color='#00ff88',linewidth=2)
                plt.axhline(y=entry[sym],color='#ff4444',linestyle='--',label='Entry')
                plt.axhline(y=stop[sym],color='#ff8800',linewidth=1.5,label=f'ATR Stop {stop[sym]:.4f}')
                plt.title(f"{name} ATR {ind['atr']:.4f}"); plt.grid(alpha=0.2); plt.legend(fontsize=7); plt.tight_layout(); plt.savefig("chart.png"); plt.close()
                with open("chart.png",'rb') as f:
                    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendPhoto",data={'chat_id':CHAT_ID,'caption':caption},files={'photo':f},timeout=20)
            except Exception as e:
                print(f"Chart fail {e}")
                requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",data={"chat_id":CHAT_ID,"text":caption},timeout=10)
            last_coins[sym]=datetime.now()
            break
        time.sleep(30)
    except Exception as e:
        print(f"Loop err {e}")
        time.sleep(10)
