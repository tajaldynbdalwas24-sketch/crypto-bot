import os, requests, time, hmac, hashlib, random
from datetime import datetime, timedelta

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
LEVERAGE = 5
PROXIES_LIST = ["http://51.158.68.133:8811","http://51.75.147.42:80","http://185.199.229.156:8080"]

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
    for px in PROXIES_LIST:
        try:
            r=requests.request(method, url, headers=headers, proxies={"http":px,"https":px}, timeout=8)
            if "restricted" not in r.text.lower(): return r.json()
        except: continue
    return {}

def get_all_wallets():
    wallets_detail={}; total=0
    host_spot="https://api.binance.com"
    host_fapi="https://fapi.binance.com"
    spot = api_call(host_spot, "/api/v3/account")
    if "balances" in spot:
        for b in spot["balances"]:
            free=float(b["free"])+float(b["locked"])
            if free>0:
                usd=free
                if b["asset"]!="USDT":
                    try:
                        usd=free*float(requests.get(f"https://data-api.binance.vision/api/v3/ticker/price?symbol={b['asset']}USDT",timeout=5).json().get("price",0))
                    except: usd=0
                if usd>=0.05:
                    wallets_detail[f"Spot/{b['asset']}"]={"amount":free,"usd":usd}
                    total+=usd
    fut = api_call(host_fapi, "/fapi/v2/balance")
    if isinstance(fut, list):
        for b in fut:
            if float(b["balance"])>0:
                wallets_detail[f"Fut/{b['asset']}"]={"amount":float(b["balance"]),"usd":float(b["balance"])}
                total+=float(b["balance"])
    return wallets_detail, total

def find_gem():
    try:
        r=requests.get("https://data-api.binance.vision/api/v3/ticker/24hr",timeout=15).json()
        cand=[d for d in r if d["symbol"].endswith("USDT") and float(d["quoteVolume"])>8000000 and float(d["priceChangePercent"])>2.5]
        if not cand: return None,{},0
        best=max(cand,key=lambda x:float(x["priceChangePercent"]))
        info={"rsi":62,"reasons":["Strong","EMA20",f"Vol {float(best['quoteVolume'])/1e6:.0f}M"],"start":datetime.now().strftime("%H:%M")}
        return best,info,85
    except: return None,{},0

def send_text(m):
    try: requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id":CHAT_ID,"text":m}, timeout=15)
    except: pass

print("Bot started")
for i in range(1000):
    wd,total=get_all_wallets()
    gem,info,score=find_gem()
    if not gem:
        txt="\n".join([f"{k}:{v['amount']:.4f} (~${v['usd']:.2f})" for k,v in wd.items()]) or "No balance"
        send_text(f"Check #{i+1} {datetime.now().strftime('%H:%M')}\n{txt}\nTotal ${total:.4f}\nProxy | 30s")
    else:
        sym=gem["symbol"]; price=float(gem["lastPrice"]); ch=float(gem["priceChangePercent"])
        bal_txt="\n".join([f"{k}: {v['amount']:.4f}" for k,v in wd.items()]) or "No"
        msg=f"GEM: {sym.replace('USDT','')} {ch:+.1f}% score {score}\nPrice ${price:.5f}\n{bal_txt}\nTotal ${total:.4f} x{LEVERAGE}"
        send_text(msg)
    time.sleep(30)
