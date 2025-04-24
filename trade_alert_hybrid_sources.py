
import requests
import pandas as pd
from datetime import datetime, timedelta
import numpy as np
import yfinance as yf

# إعدادات Pushover
PUSHOVER_USER_KEY = "YOUR_PUSHOVER_USER_KEY"
PUSHOVER_API_TOKEN = "YOUR_PUSHOVER_API_TOKEN"

# TwelveData API
TWELVE_API_KEY = "YOUR_TWELVE_API_KEY"

# NewsAPI
NEWSAPI_KEY = "YOUR_NEWSAPI_KEY"

# تصنيف الأصول حسب المصدر
TWELVE_ASSETS = ["XAU/USD", "BTC/USD", "EUR/USD"]
YF_ASSETS = {
    "US100": "^NDX",
    "US500": "^GSPC",
    "XAG/USD": "SI=F"
}

def send_pushover_alert(message, title="Trade Alert"):
    payload = {
        "token": PUSHOVER_API_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "message": message,
        "title": title
    }
    requests.post("https://api.pushover.net/1/messages.json", data=payload)

def get_twelvedata(symbol):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=15min&outputsize=500&apikey={TWELVE_API_KEY}"
    response = requests.get(url)
    data = response.json()
    if "values" not in data:
        raise ValueError(f"No data for {symbol}")
    df = pd.DataFrame(data["values"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime")
    df[["open", "high", "low", "close"]] = df[["open", "high", "low", "close"]].astype(float)
    return df

def get_yf_data(yf_symbol):
    ticker = yf.Ticker(yf_symbol)
    data = ticker.history(period="2d", interval="15m")
    if data.empty:
        raise ValueError(f"No Yahoo Finance data for {yf_symbol}")
    df = data.reset_index()
    df.rename(columns={"Datetime": "datetime", "Open": "open", "High": "high", "Low": "low", "Close": "close"}, inplace=True)
    df = df[["datetime", "open", "high", "low", "close"]]
    return df

def calculate_rsi(data, period=14):
    delta = data["close"].diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = pd.Series(gain).rolling(window=period).mean()
    avg_loss = pd.Series(loss).rolling(window=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

def calculate_atr(df, period=14):
    df["H-L"] = df["high"] - df["low"]
    df["H-PC"] = abs(df["high"] - df["close"].shift())
    df["L-PC"] = abs(df["low"] - df["close"].shift())
    tr = df[["H-L", "H-PC", "L-PC"]].max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr.iloc[-1]

def get_current_session():
    hour = datetime.utcnow().hour
    if 0 <= hour < 7:
        return "Tokyo"
    elif 7 <= hour < 13:
        return "London"
    elif 13 <= hour < 20:
        return "New York"
    else:
        return "Off Hours"

def extract_session_high_low(df, session):
    df["hour"] = df["datetime"].dt.hour
    if session == "Tokyo":
        session_df = df[(df["hour"] >= 0) & (df["hour"] < 7)]
    elif session == "London":
        session_df = df[(df["hour"] >= 7) & (df["hour"] < 13)]
    elif session == "New York":
        session_df = df[(df["hour"] >= 13) & (df["hour"] < 20)]
    else:
        session_df = df[(df["hour"] >= 20) | (df["hour"] < 0)]
    return session_df["high"].max(), session_df["low"].min()

def detect_fvg(df):
    for i in range(1, len(df) - 1):
        if df["low"].iloc[i] > df["high"].iloc[i-1] and df["high"].iloc[i] < df["low"].iloc[i+1]:
            return f"FVG at {df['datetime'].iloc[i]}"
    return "No FVG"

def detect_liquidity_sweep(df):
    prev_high = df["high"].shift(1)
    prev_low = df["low"].shift(1)
    sweep_up = (df["high"] > prev_high) & (df["close"] < prev_high)
    sweep_down = (df["low"] < prev_low) & (df["close"] > prev_low)
    if sweep_up.any():
        return "Sweep UP"
    elif sweep_down.any():
        return "Sweep DOWN"
    return "No sweep"

def fetch_market_news():
    url = f"https://newsapi.org/v2/everything?q=market OR FED OR inflation&language=en&sortBy=publishedAt&pageSize=3&apiKey={NEWSAPI_KEY}"
    response = requests.get(url)
    data = response.json()
    if "articles" in data and len(data["articles"]) > 0:
        headline = data["articles"][0]["title"]
        if "rally" in headline.lower() or "gain" in headline.lower():
            sentiment = "Bullish"
        elif "drop" in headline.lower() or "loss" in headline.lower():
            sentiment = "Bearish"
        else:
            sentiment = "Neutral"
        return f"{sentiment} news: {headline}"
    return "No news data"

def analyze_asset(symbol, df):
    price = df["close"].iloc[-1]
    rsi = calculate_rsi(df)
    atr = calculate_atr(df)
    now = datetime.now()
    session = get_current_session()
    high_now, low_now = extract_session_high_low(df[df["datetime"].dt.date == now.date()], session)
    yesterday = now.date() - timedelta(days=1)
    high_prev, low_prev = extract_session_high_low(df[df["datetime"].dt.date == yesterday], session)
    fvg = detect_fvg(df)
    liquidity = detect_liquidity_sweep(df)
    news = fetch_market_news()

    msg = f"""
[📊 {symbol} SCALPING SIGNAL]
🕒 Session: {session}
⏰ Time: {now.strftime('%H:%M')}
💰 Price: {price:.2f}
📈 RSI: {rsi:.2f} | ATR: {atr:.2f}
🔼 High (Now): {high_now:.2f}
🔽 Low (Now): {low_now:.2f}
🔼 High (Prev): {high_prev:.2f}
🔽 Low (Prev): {low_prev:.2f}
📉 FVG: {fvg}
💥 Liquidity: {liquidity}
📰 News: {news}
"""
    send_pushover_alert(msg, title=f"{symbol} Alert")

# تحليل الأصول من TwelveData
for asset in TWELVE_ASSETS:
    try:
        df = get_twelvedata(asset)
        analyze_asset(asset, df)
    except Exception as e:
        send_pushover_alert(f"Error with {asset}: {str(e)}", title="Error")

# تحليل الأصول من Yahoo Finance
for symbol, yf_symbol in YF_ASSETS.items():
    try:
        df = get_yf_data(yf_symbol)
        analyze_asset(symbol, df)
    except Exception as e:
        send_pushover_alert(f"Error with {symbol}: {str(e)}", title="Error")
