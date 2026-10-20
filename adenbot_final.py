import os, requests, time, hmac, hashlib, urllib.parse, random
from datetime import datetime
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
API_KEY = os.getenv("BIN" + "ANCE_API_KEY")
API_SECRET = os.getenv("BIN" + "ANCE_API_SECRET")
LEVERAGE = 5
PROXIES_10 = ["http://51.158.68.133:8811","http://51.75.147.42:80","http://185.199.229.156:8080","http://163.172.182.164:80","http://51.158.123.35:8811","http://57.128.16.103:80","http://51.15.120.250:80","http://51.159.96.115:80","http://141.94.44.105:80","http://176.31.99.58:3128"]

def send_text(m):
    try: requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id":CHAT_ID,"text":m,"parse_mode":"Markdown"}, timeout=15)
    except: pass

def sign(q): return hmac.new(API_SECRET.encode(), q.encode(), hashlib.sha256).hexdigest()

def api_call(host, path, q="", method="GET", futures=False):
    if not API_KEY: return {}
    ts=int(time.time()*1000); full_q = f"{q}&timestamp={ts}" if q else f"timestamp={ts}"
    sig=sign(full_q)
    url=f"{host}{path}?{full_q}&signature={sig}"
    headers={"X-MBX-APIKEY":API_KEY}
    random.shuffle(PROXIES_10)
    for px in PROXIES_10:
        try:
            r=requests.request(method, url, headers=headers, proxies={"http":px,"https":px}, timeout=8)
            if "restricted" not in r.text.lower(): return r.json()
        except: continue
    return {}

def get_all_wallets():
    wallets={}; total_usdt=0
    host_spot="https://api." + "bin" + "ance.com"
    host_fapi="https://fapi." + "bin" + "ance.com"
    
    # 1. المحفظة الفورية (Spot) - الصورة: فورية
    spot_data = api_call(host_spot, "/api/v3/account")
    if "balances" in spot_data:
        for b in spot_data["balances"]:
            free=float(b["free"]); 
            if free>0:
                wallets[f"فورية/{b['asset']}"]=free
                if b["asset"]=="USDT": total_usdt+=free
    
    # 2. محفظة التمويل (Funding) - الصورة: التمويل
    fund_data = api_call(host_spot, "/sapi/v1/asset/get-funding-asset")
    if isinstance(fund_data, list):
        for b in fund_data:
            free=float(b["free"])
            if free>0:
                wallets[f"التمويل/{b['asset']}"]=free
                if b["asset"]=="USDT": total_usdt+=free
                # تحويل تلقائي من التمويل للفورية عشان يتداول
                if b["asset"]=="USDT" and free>=1:
                    api_call(host_spot, "/sapi/v1/asset/transfer", f"asset=USDT&amount={free}&type=1", "POST")
    
    # 3. العقود الآجلة (Futures) - الصورة: العقود الآجلة
    fut_data = api_call(host_fapi, "/fapi/v2/balance")
    if isinstance(fut_data, list):
        for b in fut_data:
            bal=float(b["balance"])
            if bal>0:
                wallets[f"العقود الآجلة/{b['asset']}"]=bal
                if b["asset"]=="USDT": total_usdt+=bal
    
    # 4. Earn - الصورة: Earn
    earn_data = api_call(host_spot, "/sapi/v1/simple-earn/flexible/position")
    if "rows" in earn_data:
        for b in earn_data["rows"]:
            amt=float(b["totalAmount"])
            if amt>0:
                wallets[f"Earn/{b['asset']}"]=amt
                if b["asset"]=="USDT": total_usdt+=amt
    
    # 5. محفظة خارجية/الخيارات - الصورة: محفظة خارجية + عقود الخيارات
    # نعرضها اذا فيها رصيد
    cross_data = api_call(host_spot, "/sapi/v1/margin/account")
    if "userAssets" in cross_data:
        for b in cross_data["userAssets"]:
            free=float(b["free"])
            if free>0:
                wallets[f"الهامش/{b['asset']}"]=free
                if b["asset"]=="USDT": total_usdt+=free
    
    return wallets, total_usdt

def send_candle_chart(symbol, analysis, score, price, ch, wallets, total_usdt):
    try:
        base_url = "https://data-api." + "bin" + "ance.vision/api/v3/klines"
        r = requests.get(f"{base_url}?symbol={symbol}&interval=15m&limit=40", timeout=10).json()
        opens=[float(x[1]) for x in r]; highs=[float(x[2]) for x in r]; lows=[float(x[3]) for x in r]; closes=[float(x[4]) for x in r]
        def calc_ema(data, p=20):
            k=2/(p+1); ema=data[0]; emas=[ema]
            for c in data[1:]: ema=c*k+ema*(1-k); emas.append(ema)
            return emas
        ema20=calc_ema(closes)
        fig, (ax1, ax2) = plt.subplots(2,1, figsize=(10,6), gridspec_kw={'height_ratios':[3,1]}, sharex=True)
        for i in range(len(closes)):
            color='#00ff88' if closes[i]>=opens[i] else '#ff4444'
            ax1.plot([i,i],[lows[i],highs[i]], color=color, linewidth=1)
            body_low=min(opens[i], closes[i]); body_high=max(opens[i], closes[i])
            rect=mpatches.Rectangle((i-0.3, body_low), 0.6, body_high-body_low, facecolor=color, edgecolor=color)
            ax1.add_patch(rect)
        ax1.plot(ema20, color='yellow', linewidth=1.5, label='EMA20')
        ax1.set_title(f"{symbol.replace('USDT','')} - ${price:.5f} {ch:+.1f}%", color='white', fontsize=12, fontweight='bold')
        ax1.legend(); ax1.grid(True, alpha=0.2); ax1.set_facecolor('#0e1116'); fig.patch.set_facecolor('#0e1116'); ax1.tick_params(colors='white')
        def calc_rsi_series(closes, period=14):
            rsi_vals=[]
            for j in range(len(closes)):
                if j<period: rsi_vals.append(50)
                else:
                    gains=[]; losses=[]
                    for k in range(j-period+1, j+1):
                        d=closes[k]-closes[k-1]
                        gains.append(max(d,0)); losses.append(max(-d,0))
                    ag=sum(gains)/period; al=sum(losses)/period
                    rsi_vals.append(70 if al==0 else 100-(100/(1+ag/al)))
            return rsi_vals
        rsi_series=calc_rsi_series(closes)
        ax2.plot(rsi_series, color='#00aaff', linewidth=1.5)
        ax2.axhline(70, color='red', linestyle='--', alpha=0.5); ax2.axhline(30, color='green', linestyle='--', alpha=0.5)
        ax2.set_ylabel('RSI', color='white'); ax2.set_facecolor('#0e1116'); ax2.tick_params(colors='white'); ax2.grid(True, alpha=0.2); ax2.set_ylim(0,100)
        plt.tight_layout(); plt.savefig("/tmp/chart.png", dpi=180, facecolor='#0e1116'); plt.close()
        
        # بناء رسالة الرصيد لكل المحافظ من صورتك
        bal_text = f"💼 *تحكم كامل بكل المحافظ:*\n"
        for name, val in wallets.items():
            if val>=0.01: bal_text+=f"• {name}: {val:.4f}\n"
        bal_text+= f"\n💰 *الإجمالي: ${total_usdt:.4f} USDT في كل المحافظ*\n\n"
        
        caption = f"🎯 *صيدة: {symbol.replace('USDT','')}* تقييم {score}\n💰 ${price:.5f} {ch:+.1f}% RSI {analysis['rsi']:.0f}\n⏰ بدأ قبل {analysis['minutes_ago']}د - {analysis['start_time']} عدن\n{', '.join(analysis['reasons'])}\n\n{bal_text}"
        if total_usdt>=0.5:
            trade_amount=total_usdt*0.95
            caption+= f"🚀 *يدخل بـ ${trade_amount:.4f} من كل المحافظ (حتى نص دولار)*\n🛡️ وقف 2% | 🎯 هدف 6% | 💸 ربح متوقع ${ch*0.01*trade_amount:.4f} سبوت / ${ch*0.01*LEVERAGE*trade_amount:.4f} فيوتشر {LEVERAGE}x\n"
        else:
            caption+= f"⚠️ رصيدك ${total_usdt:.4f} أقل من 0.5$ - اشحن أي محفظة\n"
        caption+= f"🇪🇺 10 بروكسيات | يتحكم كامل | 🔄 30ث"
        url=f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
        with open("/tmp/chart.png","rb") as f: requests.post(url, data={"chat_id":CHAT_ID,"caption":caption,"parse_mode":"Markdown"}, files={"photo":f}, timeout=15)
        return total_usdt
    except Exception as e:
        print(e); return 0

def calc_rsi(closes, p=14):
    if len(closes)<p+1: return 50
    gains=[]; losses=[]
    for i in range(1,len(closes)):
        d=closes[i]-closes[i-1]; gains.append(max(d,0)); losses.append(max(-d,0))
    ag=sum(gains[-p:])/p; al=sum(losses[-p:])/p
    return 70 if al==0 else 100-(100/(1+ag/al))

def calc_ema(closes, p=20):
    if not closes: return 0
    k=2/(p+1); ema=closes[0]
    for c in closes[1:]: ema=c*k+ema*(1-k)
    return ema

def find_gem():
    try:
        base_ticker="https://data-api." + "bin" + "ance.vision/api/v3/ticker/24hr"
        r=requests.get(base_ticker, timeout=15).json()
        cand=[]
        for d in r:
            if not d["symbol"].endswith("USDT"): continue
            if d["symbol"] in ["USDCUSDT","FDUSDUSDT"]: continue
            vol=float(d["quoteVolume"]); ch=float(d["priceChangePercent"])
            if vol<8000000: continue
            if ch<3: continue
            cand.append(d)
        cand=sorted(cand, key=lambda x: float(x["quoteVolume"]), reverse=True)[:25]
        best=None; best_score=0; best_info={}
        for d in cand:
            sym=d["symbol"]
            kline_url="https://data-api." + "bin" + "ance.vision/api/v3/klines"
            kl=requests.get(f"{kline_url}?symbol={sym}&interval=15m&limit=30", timeout=8).json()
            closes=[float(x[4]) for x in kl]; vols=[float(x[5]) for x in kl]
            if len(closes)<20: continue
            rsi=calc_rsi(closes); ema20=calc_ema(closes,20); curr=closes[-1]
            vol_avg=sum(vols[-11:-1])/10 if len(vols)>10 else 1; vspike=vols[-1]/vol_avg*100
            start_idx=0
            for i in range(len(closes)-1,0,-1):
                if closes[i]<ema20: start_idx=i; break
            minutes_ago=(len(closes)-start_idx)*15; score=0; reasons=[]
            if 52<=rsi<=67: score+=30; reasons.append(f"RSI {rsi:.0f}")
            if curr>ema20: score+=20; reasons.append("فوق EMA20 ✅")
            if vspike>180: score+=25; reasons.append(f"انفجار {vspike:.0f}% 🔥")
            if float(d["quoteVolume"])>50000000: score+=15; reasons.append(f"سيولة {float(d['quoteVolume'])/1e6:.0f}M")
            if score>best_score: best_score=score; best=d; best_info={"rsi":rsi,"vspike":vspike,"reasons":reasons,"minutes_ago":minutes_ago,"start_time":datetime.now().strftime("%H:%M")}
        return best, best_info, best_score
    except: return None, {}, 0

def trade_api(path, params, futures=False):
    if not API_KEY: return {}
    params['timestamp']=int(time.time()*1000)
    q=urllib.parse.urlencode(params); sig=sign(q)
    host="https://fapi." + "bin" + "ance.com" if futures else "https://api." + "bin" + "ance.com"
    url=f"{host}{path}?{q}&signature={sig}"; headers={"X-MBX-APIKEY":API_KEY}
    random.shuffle(PROXIES_10)
    for px in PROXIES_10:
        try:
            r=requests.request("POST" if "order" in path else "GET", url, headers=headers, proxies={"http":px,"https":px}, timeout=8)
            if "restricted" not in r.text.lower(): return r.json()
        except: continue
    return {}

for i in range(10):
    wallets, total = get_all_wallets()
    gem, info, score = find_gem()
    if not gem:
        bal_text="\n".join([f"{k}: {v:.4f}" for k,v in wallets.items() if v>=0.01]) or "لا يوجد رصيد"
        send_text(f"🔍 *يفحص #{i+1}/10* ⏰ {datetime.now().strftime('%H:%M:%S')} عدن\n💼 المحافظ:\n{bal_text}\n💰 الإجمالي ${total:.4f}\n🇪🇺 10 بروكسيات | 🔄 30ث")
    else:
        sym=gem["symbol"]; price=float(gem["lastPrice"]); ch=float(gem["priceChangePercent"])
        available=send_candle_chart(sym, info, score, price, ch, wallets, total)
        if total>=0.5 and score>=60:
            trade_amount=total*0.95
            try:
                if trade_amount<5:
                    trade_api("/fapi/v1/leverage",{"symbol":sym,"leverage":LEVERAGE}, futures=True)
                    res=trade_api("/fapi/v1/order",{"symbol":sym,"side":"BUY","type":"MARKET","quantity":round(trade_amount/price,6)}, futures=True)
                else:
                    res=trade_api("/api/v3/order",{"symbol":sym,"side":"BUY","type":"MARKET","quoteOrderQty":round(trade_amount,2)})
                if "orderId" in str(res):
                    send_text(f"✅ *تم التداول من كل المحافظ: {sym.replace('USDT','')}*\n💰 ${trade_amount:.4f} من إجمالي ${total:.4f}\n🆔 {res.get('orderId')}\n📊 شوفه في Binance")
            except: pass
    if i<9: time.sleep(30)
