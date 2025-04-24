
import requests
import pandas as pd
from datetime import datetime, timedelta
import numpy as np
import yfinance as yf

# Pushover credentials
PUSHOVER_USER_KEY = "YOUR_PUSHOVER_USER_KEY"
PUSHOVER_API_TOKEN = "YOUR_PUSHOVER_API_TOKEN"

# TwelveData API
TWELVE_API_KEY = "YOUR_TWELVE_API_KEY"

# NewsAPI
NEWSAPI_KEY = "YOUR_NEWSAPI_KEY"

# Assets
TWELVE_ASSETS = ["XAU/USD", "BTC/USD", "EUR/USD"]
YF_ASSETS = {
    "US100": "^NDX",
    "US500": "^GSPC",
    "XAG/USD": "SI=F"
}

def send_pushover_alert(message, title="Market Opportunity"):
    payload = {
        "token": PUSHOVER_API_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "message": message,
        "title": title,
        "sound": "siren",
        "priority": 1
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
    return df[["datetime", "open", "high", "low", "close"]]

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

def detect_fvg(df):
    for i in range(1, len(df) - 1):
        if df["low"].iloc[i] > df["high"].iloc[i-1] and df["high"].iloc[i] < df["low"].iloc[i+1]:
            return df["datetime"].iloc[i]
    return None

def fetch_market_news():
    url = f"https://newsapi.org/v2/everything?q=market OR FED OR inflation&language=en&sortBy=publishedAt&pageSize=1&apiKey={NEWSAPI_KEY}"
    response = requests.get(url)
    data = response.json()
    if "articles" in data and len(data["articles"]) > 0:
        article = data["articles"][0]
        return f"{article['title']} ({article['source']['name']})"
    return "No recent news"

def analyze_asset(symbol, df):
    price = df["close"].iloc[-1]
    rsi = calculate_rsi(df)
    atr = calculate_atr(df)
    now = datetime.now()

    # Prepare session data
    df["hour"] = df["datetime"].dt.hour
    df["date"] = df["datetime"].dt.date
    yesterday = now.date() - timedelta(days=1)
    today_df = df[df["date"] == now.date()]
    prev_df = df[df["date"] == yesterday]

    if not prev_df.empty:
        high_prev = prev_df["high"].max()
        low_prev = prev_df["low"].min()
    else:
        high_prev = low_prev = None

    fvg_detected = detect_fvg(df)
    news = fetch_market_news()

    # Conditions
    rsi_signal = rsi < 30 or rsi > 70
    near_high = high_prev is not None and abs(price - high_prev) < 0.002 * price
    near_low = low_prev is not None and abs(price - low_prev) < 0.002 * price

    opportunity = rsi_signal or near_high or near_low or fvg_detected

    if opportunity:
        msg = f"""
📊 {symbol} Market Signal
💰 Price: {price:.4f}
📈 RSI: {rsi:.2f} {'✅' if rsi_signal else ''}
📊 ATR (Liquidity): {atr:.4f}
🔼 High Prev: {high_prev:.4f} {'✅' if near_high else ''}
🔽 Low Prev: {low_prev:.4f} {'✅' if near_low else ''}
📉 FVG Detected: {'✅ at ' + str(fvg_detected) if fvg_detected else '❌'}
📰 News: {news}
"""
        send_pushover_alert(msg, title=f"{symbol} Opportunity")

# Analyze assets
for asset in TWELVE_ASSETS:
    try:
        df = get_twelvedata(asset)
        analyze_asset(asset, df)
    except Exception as e:
        send_pushover_alert(f"Error with {asset}: {str(e)}", title="Error")

for symbol, yf_symbol in YF_ASSETS.items():
    try:
        df = get_yf_data(yf_symbol)
        analyze_asset(symbol, df)
    except Exception as e:
        send_pushover_alert(f"Error with {symbol}: {str(e)}", title="Error")
