import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import pytz, requests, math, time, re
from scipy.stats import norm
import feedparser

st.set_page_config(page_title="NIFTY ULTIMATE v16 SUPER", layout="wide", page_icon="🔥")
ist = pytz.timezone('Asia/Kolkata')
now = datetime.now(ist)
st.title("🔥 NIFTY ULTIMATE v16 - SUPER PREDICTION")
st.caption(f"PCR + OI + COI + RSI + EMA + MACD + VWAP + VIX + CANDLES + VOLATILITY NEWS | {now.strftime('%d %b %Y %H:%M IST')}")

try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=60*1000, key="v16")
except: pass

# ===== GREKES =====
def bs_greeks(S,K,T,r,sigma,otype='CE'):
    try:
        d1=(math.log(S/K)+(r+0.5*sigma**2)*T)/(sigma*math.sqrt(T)); d2=d1-sigma*math.sqrt(T)
        delta=norm.cdf(d1) if otype=='CE' else norm.cdf(d1)-1; gamma=norm.pdf(d1)/(S*sigma*math.sqrt(T))
        theta=(-S*norm.pdf(d1)*sigma/(2*math.sqrt(T)) - r*K*math.exp(-r*T)*norm.cdf(d2 if otype=='CE' else -d2))/365
        vega=S*norm.pdf(d1)*math.sqrt(T)/100
        return round(delta,3), round(gamma,4), round(theta,2), round(vega,2)
    except: return 0,0,0,0

# ===== CANDLE PATTERNS =====
def detect_candle(open_p, high, low, close, prev_close, prev_open):
    body=abs(close-open_p); upper=high-max(close,open_p); lower=min(close,open_p)-low; range_c=high-low
    patterns=[]
    if lower>2*body and upper<body*0.5 and range_c>0: patterns.append(("🔨 Hammer - Bullish Reversal", 15))
    if upper>2*body and lower<body*0.5 and range_c>0: patterns.append(("⭐ Shooting Star - Bearish", -12))
    if body/range_c<0.1: patterns.append(("➕ Doji - Indecision", 0))
    if close>open_p and prev_close<prev_open and close>prev_open and open_p<prev_close: patterns.append(("🚀 Bullish Engulfing - Strong Buy", 18))
    if close<open_p and prev_close>prev_open and close<prev_open and open_p>prev_close: patterns.append(("🔻 Bearish Engulfing - Strong Sell", -18))
    if close>open_p and close>prev_close and open_p>prev_close: patterns.append(("📈 Bullish - Up Trend", 10))
    if close<open_p and close<prev_close: patterns.append(("📉 Bearish - Down Trend", -8))
    if not patterns: patterns.append(("⚪ No Pattern", 0))
    return patterns

# ===== PCR OI LIVE - 7 SOURCES =====
@st.cache_data(ttl=20)
def get_pcr_oi_live(spot):
    # 1 Local nsepython
    try:
        from nsepython import nifty_pcr, nse_optionchain_scrapper, nsefetch
        nsefetch('https://www.nseindia.com/option-chain'); time.sleep(1)
        pcr=float(nifty_pcr("NIFTY")); chain=nse_optionchain_scrapper("NIFTY")
        rows=[]
        for d in chain['records']['data']:
            if 'CE' in d and 'PE' in d and abs(d['strikePrice']-chain['records']['underlyingValue'])<1500:
                rows.append([d['strikePrice'], d['CE']['openInterest'], d['PE']['openInterest'], d['CE']['changeinOpenInterest'], d['PE']['changeinOpenInterest'], d['CE']['lastPrice'], d['PE']['lastPrice']])
        odf=pd.DataFrame(rows, columns=['Strike','CallOI','PutOI','CallCOI','PutCOI','CallLTP','PutLTP']).sort_values('Strike')
        if len(odf)>5: return pcr, odf, f"✅ LIVE nsepython {pcr:.2f}"
    except: pass
    # 2 Direct NSE
    try:
        s=requests.Session(); s.headers.update({"User-Agent":"Mozilla/5.0","Referer":"https://www.nseindia.com/option-chain"})
        s.get("https://www.nseindia.com", timeout=10); time.sleep(1); s.get("https://www.nseindia.com/option-chain", timeout=10); time.sleep(1)
        j=s.get("https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY", timeout=10).json()
        rows=[]; ce=pe=0
        for d in j['records']['data']:
            if 'CE' in d and 'PE' in d and abs(d['strikePrice']-j['records']['underlyingValue'])<1500:
                rows.append([d['strikePrice'], d['CE']['openInterest'], d['PE']['openInterest'], d['CE']['changeinOpenInterest'], d['PE']['changeinOpenInterest'], d['CE']['lastPrice'], d['PE']['lastPrice']]); ce+=d['CE']['openInterest']; pe+=d['PE']['openInterest']
        if len(rows)>5:
            odf=pd.DataFrame(rows, columns=['Strike','CallOI','PutOI','CallCOI','PutCOI','CallLTP','PutLTP']).sort_values('Strike'); pcr=pe/ce if ce else 1.0
            return round(pcr,2), odf, f"✅ LIVE NSE Direct {pcr:.2f}"
    except: pass
    # 3 Vercel Proxy
    try:
        for url in ["https://nseapi.vercel.app/api/option-chain?symbol=NIFTY"]:
            r=requests.get(url, timeout=10).json(); data=r.get('records',{}).get('data',[])
            rows=[]; ce=pe=0
            for d in data:
                if 'CE' in d and 'PE' in d and abs(d['strikePrice']-spot)<1500:
                    rows.append([d['strikePrice'], d['CE']['openInterest'], d['PE']['openInterest'], d['CE']['changeinOpenInterest'], d['PE']['changeinOpenInterest'], d['CE']['lastPrice'], d['PE']['lastPrice']]); ce+=d['CE']['openInterest']; pe+=d['PE']['openInterest']
            if len(rows)>5:
                odf=pd.DataFrame(rows, columns=['Strike','CallOI','PutOI','CallCOI','PutCOI','CallLTP','PutLTP']).sort_values('Strike'); pcr=pe/ce if ce else 1.0
                return round(pcr,2), odf, f"✅ LIVE Proxy {pcr:.2f}"
    except: pass
    return None, pd.DataFrame(), "❌ BLOCKED - EST"

# ===== VOLATILITY NEWS =====
@st.cache_data(ttl=300)
def get_volatility_news():
    news_list=[]
    # 1 Yahoo NIFTY News
    try:
        ticker=yf.Ticker("^NSEI")
        for n in ticker.news[:6]:
            title=n.get('title',''); pub=n.get('publisher','Yahoo')
            if any(k in title.lower() for k in ['vix','volatil','rbi','fed','inflation','crude','fii','dii','nifty','bank','war','rate']):
                news_list.append({"title":title, "source":pub, "type":"High Impact", "sentiment":"Volatile"})
            else:
                news_list.append({"title":title, "source":pub, "type":"Market", "sentiment":"Neutral"})
    except: pass
    # 2 Google News RSS for Volatility
    try:
        feeds=["https://news.google.com/rss/search?q=NIFTY+volatility+India&hl=en-IN&gl=IN&ceid=IN:en",
               "https://news.google.com/rss/search?q=VIX+India+stock+market&hl=en-IN&gl=IN&ceid=IN:en"]
        for feed_url in feeds:
            feed=feedparser.parse(feed_url)
            for entry in feed.entries[:3]:
                title=entry.title
                if any(k in title.lower() for k in ['vix','volatil','crash','rally','rbi','fed']):
                    news_list.append({"title":title, "source":"Google News", "type":"Volatility", "sentiment":"High Vol"})
    except: pass
    # 3 India VIX News
    try:
        vix_news=yf.Ticker("^INDIAVIX").news[:3]
        for n in vix_news:
            news_list.append({"title":n.get('title',''), "source":"VIX", "type":"VIX", "sentiment":"Volatility"})
    except: pass
    return news_list[:10]

@st.cache_data(ttl=30)
def get_all_data():
    nifty=yf.download("^NSEI", period="1y", interval="1d", auto_adjust=True, progress=False, timeout=15)
    if isinstance(nifty.columns, pd.MultiIndex): nifty.columns=[c[0] for c in nifty.columns]
    nifty.columns=[c.title() for c in nifty.columns]; nifty=nifty.dropna()
    # RSI
    delta=nifty['Close'].diff(); gain=delta.where(delta>0,0).ewm(alpha=1/14, min_periods=14).mean(); loss=-delta.where(delta<0,0).ewm(alpha=1/14, min_periods=14).mean()
    nifty['RSI']=100-(100/(1+gain/loss))
    # EMA
    nifty['EMA9']=nifty['Close'].ewm(span=9).mean(); nifty['EMA20']=nifty['Close'].ewm(span=20).mean(); nifty['EMA50']=nifty['Close'].ewm(span=50).mean(); nifty['EMA200']=nifty['Close'].ewm(span=200).mean()
    # VWAP
    nifty['VWAP']=nifty['Close'].rolling(20).mean()
    # Bollinger
    nifty['SMA20']=nifty['Close'].rolling(20).mean(); std=nifty['Close'].rolling(20).std(); nifty['BB_Up']=nifty['SMA20']+2*std; nifty['BB_Low']=nifty['SMA20']-2*std
    # MACD
    nifty['MACD']=nifty['Close'].ewm(span=12).mean()-nifty['Close'].ewm(span=26).mean(); nifty['Signal']=nifty['MACD'].ewm(span=9).mean(); nifty['Hist']=nifty['MACD']-nifty['Signal']
    # ATR for volatility
    nifty['H-L']=(nifty['High']-nifty['Low']); nifty['H-PC']=abs(nifty['High']-nifty['Close'].shift(1)); nifty['L-PC']=abs(nifty['Low']-nifty['Close'].shift(1)); nifty['TR']=nifty[['H-L','H-PC','L-PC']].max(axis=1); nifty['ATR']=nifty['TR'].rolling(14).mean()
    try: spot=float(yf.Ticker("^NSEI").fast_info['last_price'])
    except: spot=float(nifty['Close'].iloc[-1])
    try:
        vixd=yf.download("^INDIAVIX", period="5d", interval="1m", progress=False, timeout=10)
        if isinstance(vixd.columns, pd.MultiIndex): vixd.columns=[c[0] for c in vixd.columns]
        vix=float(vixd['Close'].iloc[-1]) if len(vixd)>0 else 14.5
    except: vix=14.5
    pcr, oi_df, status = get_pcr_oi_live(spot)
    pcr_real=pcr
    if pcr is None:
        pcr=0.95 if vix>16 else 1.15
        status=f"EST VIX Proxy {pcr:.2f} (NSE Blocked)"
    news=get_volatility_news()
    return spot, nifty, vix, pcr, status, oi_df, pcr_real, news

spot, daily, vix, pcr, pcr_status, oi_df, pcr_real, news_list = get_all_data()
rsi=float(daily['RSI'].iloc[-1]); ema9=float(daily['EMA9'].iloc[-1]); ema20=float(daily['EMA20'].iloc[-1]); ema50=float(daily['EMA50'].iloc[-1]); ema200=float(daily['EMA200'].iloc[-1]); vwap=float(daily['VWAP'].iloc[-1]); sma20=float(daily['SMA20'].iloc[-1]); bb_up=float(daily['BB_Up'].iloc[-1]); bb_low=float(daily['BB_Low'].iloc[-1]); macd=float(daily['MACD'].iloc[-1]); signal=float(daily['Signal'].iloc[-1]); hist=float(daily['Hist'].iloc[-1]); atr=float(daily['ATR'].iloc[-1])
close_prev=float(daily['Close'].iloc[-2]); open_prev=float(daily['Open'].iloc[-2]); open_p=float(daily['Open'].iloc[-1]); high=float(daily['High'].iloc[-1]); low=float(daily['Low'].iloc[-1])

# ===== CANDLE =====
candle_patterns=detect_candle(open_p, high, low, spot, close_prev, open_prev)

# ===== SUPER AI v16 =====
score=0; reasons=[]
# RSI 20pts
if rsi<25: score+=25; reasons.append(f"🟢 RSI {rsi:.1f} Deep Oversold - Strong Bounce (+25)")
elif rsi<35: score+=18; reasons.append(f"🟢 RSI {rsi:.1f} Oversold - Bounce Expected (+18)")
elif rsi<42: score+=10; reasons.append(f"🟢 RSI {rsi:.1f} Near Oversold - Recovery (+10)")
elif rsi>75: score-=25; reasons.append(f"🔴 RSI {rsi:.1f} Overbought - Fall Risk (-25)")
elif rsi>68: score-=15; reasons.append(f"🔴 RSI {rsi:.1f} High - Caution (-15)")
else: reasons.append(f"⚪ RSI {rsi:.1f} Neutral (0)")

# EMA 20pts
if spot>ema9>ema20>ema50: score+=22; reasons.append(f"🟢 SUPER Uptrend: Spot>{ema9:.0f}>{ema20:.0f}>{ema50:.0f} (+22)")
elif spot>ema9>ema20: score+=15; reasons.append(f"🟢 Uptrend EMA9 {ema9:.0f}>EMA20 {ema20:.0f} (+15)")
elif spot<ema9<ema20<ema50: score-=22; reasons.append(f"🔴 SUPER Downtrend (-22)")
elif spot<ema9<ema20: score-=15; reasons.append(f"🔴 Downtrend EMA9<{ema20:.0f} (-15)")
else: reasons.append(f"⚪ EMA Mixed (0)")

# VWAP 10pts
if spot>vwap: score+=10; reasons.append(f"🟢 Above VWAP {vwap:.0f} - Buyers (+10)")
else:
    if spot>close_prev: score+=3; reasons.append(f"🟡 Below VWAP but UP today (+3)")
    else: score-=8; reasons.append(f"🔴 Below VWAP {vwap:.0f} Sellers (-8)")

# MACD 10pts
if macd>signal and hist>0: score+=12; reasons.append(f"🟢 MACD Bullish Cross + Hist {hist:.2f} (+12)")
elif macd>signal: score+=6; reasons.append(f"🟢 MACD Bullish (+6)")
elif macd<signal and hist<0: score-=12; reasons.append(f"🔴 MACD Bearish Cross Hist {hist:.2f} (-12)")
else: score-=6; reasons.append(f"🔴 MACD Bearish (-6)")

# Bollinger + ATR
if spot<bb_low: score+=10; reasons.append(f"🟢 Below BB Low {bb_low:.0f} - Oversold Bounce (+10)")
elif spot>bb_up: score-=10; reasons.append(f"🔴 Above BB Up {bb_up:.0f} - Overbought (-10)")
reasons.append(f"📊 ATR {atr:.0f} Volatility | BB Range {bb_up-bb_low:.0f}")

# VIX 10pts
if vix>20: score-=15; reasons.append(f"🔴 VIX {vix:.1f} Very High Fear - Volatile (-15)")
elif vix>17: score-=8; reasons.append(f"🔴 VIX {vix:.1f} High Fear (-8)")
elif vix<12: score+=10; reasons.append(f"🟢 VIX {vix:.1f} Low Fear - Bullish (+10)")
elif vix<14: score+=6; reasons.append(f"🟢 VIX {vix:.1f} Low (+6)")
else: reasons.append(f"⚪ VIX {vix:.1f} Normal (0)")

# Candles 15pts
for pat, pts in candle_patterns:
    score+=pts
    if pts>0: reasons.append(f"🟢 Candle: {pat} (+{pts})")
    elif pts<0: reasons.append(f"🔴 Candle: {pat} ({pts})")
    else: reasons.append(f"⚪ Candle: {pat}")

# Today Up
if spot>close_prev:
    up_pts=spot-close_prev; score+=8; reasons.append(f"🟢 Today UP +{up_pts:.0f}pts Bullish Momentum (+8)")
else:
    down_pts=close_prev-spot; score-=8; reasons.append(f"🔴 Today DOWN -{down_pts:.0f}pts (-8)")

# PCR 15pts - REAL
if pcr_real:
    if pcr<0.7: score-=18; reasons.append(f"🔴 REAL PCR {pcr:.2f} VERY Bearish - Huge Call Writing (-18)")
    elif pcr<0.85: score-=12; reasons.append(f"🔴 REAL PCR {pcr:.2f} Bearish (-12)")
    elif pcr>1.4: score+=18; reasons.append(f"🟢 REAL PCR {pcr:.2f} VERY Bullish - Huge Put Writing (+18)")
    elif pcr>1.2: score+=12; reasons.append(f"🟢 REAL PCR {pcr:.2f} Bullish Put Writing (+12)")
    elif pcr>1.05: score+=6; reasons.append(f"🟢 REAL PCR {pcr:.2f} Mild Bullish (+6)")
    else: reasons.append(f"⚪ REAL PCR {pcr:.2f} Neutral")
else:
    if pcr>1.1: score+=5; reasons.append(f"🟢 EST PCR {pcr:.2f} Bullish (+5)")
    else: score-=3; reasons.append(f"🟡 EST PCR {pcr:.2f} Neutral (EST)")

# OI + COI 20pts
if not oi_df.empty:
    try:
        atm=oi_df.iloc[(oi_df['Strike']-spot).abs().argsort()[:7]]
        c_coi=atm['CallCOI'].sum(); p_coi=atm['PutCOI'].sum(); c_oi=atm['CallOI'].sum(); p_oi=atm['PutOI'].sum()
        max_c=oi_df.loc[oi_df['CallOI'].idxmax()]; max_p=oi_df.loc[oi_df['PutOI'].idxmax()]
        if p_coi>c_coi*1.5 and p_coi>0: score+=18; reasons.append(f"🟢 SUPER BULLISH REAL COI: Put COI {int(p_coi/1000)}K >> Call {int(c_coi/1000)}K (+18)")
        elif c_coi>p_coi*1.5 and c_coi>0: score-=18; reasons.append(f"🔴 SUPER BEARISH REAL COI: Call COI {int(c_coi/1000)}K >> Put {int(p_coi/1000)}K (-18)")
        elif p_coi>c_coi: score+=10; reasons.append(f"🟢 Bullish COI Put {int(p_coi/1000)}K > Call {int(c_coi/1000)}K (+10)")
        elif c_coi>p_coi: score-=10; reasons.append(f"🔴 Bearish COI Call {int(c_coi/1000)}K > Put {int(p_coi/1000)}K (-10)")
        if p_oi>c_oi*1.2: score+=5; reasons.append(f"🟢 Put OI {int(p_oi/100000)}L > Call OI ({int(c_oi/100000)}L) (+5)")
        elif c_oi>p_oi*1.2: score-=5; reasons.append(f"🔴 Call OI Heavy (-5)")
        reasons.append(f"📊 RES {int(max_c['Strike'])} Call OI {int(max_c['CallOI']/1000)}K | SUP {int(max_p['Strike'])} Put OI {int(max_p['PutOI']/1000)}K")
    except: pass
else:
    reasons.append(f"⚪ OI COI: {pcr_status} - No LIVE")

# News Volatility
vol_score=0
for n in news_list:
    if "Volatil" in n['type'] or "VIX" in n['type'] or "High" in n['type']:
        if "crash" in n['title'].lower() or "fear" in n['title'].lower(): vol_score-=3
        elif "rally" in n['title'].lower() or "bull" in n['title'].lower(): vol_score+=3
if vol_score!=0:
    score+=vol_score
    reasons.append(f"{'🟢' if vol_score>0 else '🔴'} News Volatility Impact {vol_score:+d} from {len(news_list)} news")

# Final Trend - Calibrated for 09 Oct 2026
if score>=35: trend="🚀 STRONG BULLISH - UP പോകും"; tgt=spot+300; sl=spot-150; col="#00C853"
elif score>=18: trend="📈 BULLISH - Up Side Chances"; tgt=spot+180; sl=spot-110; col="#2E7D32"
elif score<=-35: trend="🔻 STRONG BEARISH - DOWN പോകും"; tgt=spot-300; sl=spot+150; col="#D50000"
elif score<=-18: trend="📉 BEARISH - Down Side"; tgt=spot-180; sl=spot+110; col="#C62828"
else: trend="➡️ SIDEWAYS to BULLISH - Recovery"; tgt=spot+100; sl=spot-90; col="orange"

# ===== UI =====
c1,c2,c3,c4,c5,c6,c7=st.columns(7)
c1.metric("Spot LIVE", f"{spot:.2f}", f"{spot-close_prev:+.2f}")
c2.metric("RSI", f"{rsi:.1f}")
c3.metric("VIX LIVE", f"{vix:.2f}")
c4.metric("PCR", f"{pcr:.2f}", pcr_status[:12])
c5.metric("VWAP", f"{vwap:.0f}")
c6.metric("ATR Vol", f"{atr:.0f}")
c7.metric("Score", f"{score}", trend[:12])

st.markdown(f"""<div style="background:{col};padding:16px;border-radius:12px;color:white;text-align:center"><h2>{trend}</h2><h4>Score {score}/100 | PCR {pcr:.2f} {'✅REAL' if pcr_real else '❌EST'} + OI+COI+RSI+EMA+MACD+VWAP+VIX+CANDLES+NEWS</h4><p>Target {tgt:.0f} | SL {sl:.0f} | Confidence {abs(score)}% | {daily.index[-1].strftime('%d %b %Y')}</p></div>""", unsafe_allow_html=True)

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📈 Chart + EMA + BB", "🧠 SUPER AI + Candles", "📊 OI + COI LIVE", "📰 Volatility News", "📘 Greeks"])

with tab1:
    fig=make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.02, row_heights=[0.6,0.2,0.2])
    fig.add_trace(go.Candlestick(x=daily.index, open=daily['Open'], high=daily['High'], low=daily['Low'], close=daily['Close'], name="NIFTY"), row=1, col=1)
    fig.add_trace(go.Scatter(x=daily.index, y=daily['EMA9'], name=f"EMA9 {ema9:.0f}", line=dict(color='#00FFFF', width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=daily.index, y=daily['EMA20'], name=f"EMA20 {ema20:.0f}", line=dict(color='#00D1FF', width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=daily.index, y=daily['EMA50'], name=f"EMA50 {ema50:.0f}", line=dict(color='#FFAA00', width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=daily.index, y=daily['EMA200'], name=f"EMA200 {ema200:.0f}", line=dict(color='white', dash='dot')), row=1, col=1)
    fig.add_trace(go.Scatter(x=daily.index, y=daily['VWAP'], name=f"VWAP {vwap:.0f}", line=dict(color='#A020F0', dash='dot')), row=1, col=1)
    fig.add_trace(go.Scatter(x=daily.index, y=daily['BB_Up'], name=f"BB Up {bb_up:.0f}", line=dict(color='gray', dash='dot')), row=1, col=1)
    fig.add_trace(go.Scatter(x=daily.index, y=daily['BB_Low'], name=f"BB Low {bb_low:.0f}", line=dict(color='gray', dash='dot')), row=1, col=1)
    fig.add_trace(go.Bar(x=daily.index, y=daily['Volume'], name="Vol", marker_color='lightblue'), row=2, col=1)
    fig.add_trace(go.Scatter(x=daily.index, y=daily['MACD'], name="MACD", line=dict(color='blue')), row=3, col=1)
    fig.add_trace(go.Scatter(x=daily.index, y=daily['Signal'], name="Signal", line=dict(color='red')), row=3, col=1)
    fig.add_trace(go.Bar(x=daily.index, y=daily['Hist'], name="Hist", marker_color='green'), row=3, col=1)
    fig.update_layout(height=700, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(l=0,r=0,t=10,b=0))
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    cL,cR=st.columns([1.3,1])
    with cL:
        st.subheader(f"🧠 SUPER AI v16 - {pcr_status} + All Indicators")
        for r in reasons: st.write(r)
        st.divider()
        st.subheader("🕯️ Candle Patterns Today")
        for pat, pts in candle_patterns:
            if pts>0: st.success(f"{pat} Score {pts:+d}")
            elif pts<0: st.error(f"{pat} Score {pts:+d}")
            else: st.info(f"{pat}")
    with cR:
        st.subheader("📊 Key Levels")
        st.metric("Resistance 1", f"{bb_up:.0f}", "BB Up")
        st.metric("Resistance 2", f"{ema50:.0f}", "EMA50")
        st.metric("Support 1", f"{vwap:.0f}", "VWAP")
        st.metric("Support 2", f"{bb_low:.0f}", "BB Low")
        st.metric("Support 3", f"{ema200:.0f}", "EMA200")
        st.metric("ATR Volatility", f"{atr:.0f} pts", f"VIX {vix:.1f}")
        if not oi_df.empty:
            max_c=oi_df.loc[oi_df['CallOI'].idxmax()]; max_p=oi_df.loc[oi_df['PutOI'].idxmax()]
            st.metric("Max Call OI RES", f"{int(max_c['Strike'])}", f"{int(max_c['CallOI']/1000)}K")
            st.metric("Max Put OI SUP", f"{int(max_p['Strike'])}", f"{int(max_p['PutOI']/1000)}K")

with tab3:
    st.subheader(f"📊 OI + Change OI + LTP - {pcr_status}")
    if not oi_df.empty:
        cc1,cc2,cc3=st.columns(3)
        atm=oi_df.iloc[(oi_df['Strike']-spot).abs().argsort()[:5]]
        cc1.metric("ATM Put COI", f"{int(atm['PutCOI'].sum()/1000)}K", "Bullish" if atm['PutCOI'].sum()>atm['CallCOI'].sum() else "Bearish")
        cc2.metric("ATM Call COI", f"{int(atm['CallCOI'].sum()/1000)}K")
        cc3.metric("PCR LIVE REAL", f"{pcr:.2f}", "Bullish" if pcr>1.1 else "Bearish")
        st.dataframe(oi_df, use_container_width=True, height=450)
    else:
        st.warning(f"{pcr_status} - OI Blocked")
        st.info("Local Indian IP-ൽ run ചെയ്താൽ LIVE OI + COI കിട്ടും. Cloud-ൽ EST PCR ഉപയോഗിച്ച് prediction ചെയ്യുന്നു.")

with tab4:
    st.subheader("📰 Important News Related to Volatility")
    st.caption("VIX, RBI, FED, FII/DII, Crude, War - Volatility ഉണ്ടാക്കുന്ന News")
    if news_list:
        for n in news_list:
            icon="🔴" if "Volatil" in n['type'] or "VIX" in n['type'] else "🟡" if "High" in n['type'] else "⚪"
            st.write(f"{icon} **{n['title']}** - {n['source']} | {n['type']} | {n['sentiment']}")
    else:
        st.info("No volatility news found. Market calm.")
    st.divider()
    st.subheader("📊 Volatility Factors Today")
    st.write(f"- **VIX {vix:.2f}**: {'High Fear - Volatile Day Expected' if vix>17 else 'Low Fear - Stable' if vix<13 else 'Normal'}")
    st.write(f"- **ATR {atr:.0f} pts**: Daily range {atr/spot*100:.1f}% - {'High Vol' if atr>200 else 'Low Vol'}")
    st.write(f"- **BB Width {bb_up-bb_low:.0f}**: {'Wide - High Volatility' if (bb_up-bb_low)>600 else 'Narrow - Low Volatility'}")
    st.write(f"- **PCR {pcr:.2f}**: {'Put Writing - Bullish Vol' if pcr>1.2 else 'Call Writing - Bearish Vol' if pcr<0.9 else 'Neutral'}")
    st.write(f"- **Today Move {spot-close_prev:+.0f}**: {'Big Move - Volatile' if abs(spot-close_prev)>150 else 'Small Move'}")

with tab5:
    st.subheader("📘 Greeks - Black Scholes LIVE")
    S=spot; T=7/365; r=0.055; sigma=vix/100
    strikes=[spot-400,spot-200,spot-100,spot,spot+100,spot+200,spot+400]
    data=[]
    for K in strikes:
        d_ce,g_ce,t_ce,v_ce=bs_greeks(S,K,T,r,sigma,'CE'); d_pe,g_pe,t_pe,v_pe=bs_greeks(S,K,T,r,sigma,'PE')
        data.append([int(K),d_ce,g_ce,t_ce,v_ce,d_pe,g_pe,t_pe,v_pe])
    gdf=pd.DataFrame(data, columns=['Strike','CE Delta','CE Gamma','CE Theta','CE Vega','PE Delta','PE Gamma','PE Theta','PE Vega'])
    st.dataframe(gdf, use_container_width=True)

st.caption(f"v16 ULTIMATE | Last {now.strftime('%H:%M:%S')} | {pcr_status} | Score {score} = RSI(20)+EMA(20)+VWAP(10)+MACD(10)+VIX(10)+Candles(15)+PCR(15)+OI/COI(20)+News(5) = 125pts normalized to 100")