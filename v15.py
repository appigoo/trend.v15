import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt
import time
import requests  # 新增：用於發送 Telegram 請求

# 設定頁面配置
st.set_page_config(page_title="Pro Stock Monitor + Telegram", layout="wide")

# ======================
# Telegram 通知函數
# ======================
def send_telegram_message(message):
    try:
        # 從 st.secrets 讀取配置
        token = st.secrets["TELEGRAM_BOT_TOKEN"]
        chat_id = st.secrets["TELEGRAM_CHAT_ID"]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload)
    except Exception as e:
        st.error(f"Telegram 發送失敗: {e}")

# ======================
# 原有計算邏輯 (保持完整)
# ======================
def calculate_ema(series, period):
    alpha = 2 / (period + 1)
    return series.ewm(alpha=alpha, adjust=False).mean()

def calculate_macd(close, fast=12, slow=26, signal=9):
    ema_fast = calculate_ema(close, fast)
    ema_slow = calculate_ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal)
    return macd_line, signal_line, macd_line - signal_line

@st.cache_data(ttl=60)
def get_stock_data(symbol, period="5d", interval="5m"):
    try:
        df = yf.download(symbol, period=period, interval=interval, progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
        df.columns = ['open', 'high', 'low', 'close', 'volume']
        return df
    except: return None

def calculate_indicators(df):
    if df is None or len(df) < 50: return df
    df = df.copy()
    df['EMA5'] = calculate_ema(df['close'], 5)
    df['EMA10'] = calculate_ema(df['close'], 10)
    df['EMA20'] = calculate_ema(df['close'], 20)
    df['MACD'], df['MACD_signal'], df['MACD_hist'] = calculate_macd(df['close'])
    df['avg_volume'] = df['volume'].rolling(window=20).mean()
    df['resistance'] = df['high'].rolling(window=20).max().shift(1)
    return df

# ======================
# 產生信號 + 自動通知
# ======================
def generate_signals(df, symbol):
    if df is None or len(df) < 30: return []
    signals = []
    # 獲取最後一根 K 線的數據進行判斷
    i = len(df) - 1
    row = df.iloc[i]; prev = df.iloc[i-1]
    
    close, ema5, ema10 = row['close'], row['EMA5'], row['EMA10']
    macd, macd_sig, vol = row['MACD'], row['MACD_signal'], row['volume']
    avg_vol, resistance = row['avg_volume'], row['resistance']
    
    msg = None
    # 買入條件 1: 反轉
    if (close > ema5 > ema10) and (macd > macd_sig > prev['MACD_signal']) and (vol > avg_vol * 1.2):
        low_price = df['low'].iloc[max(0, i-10):i+1].min()
        msg = f"🟢 *[買入信號 - 反轉]*\n股票: {symbol}\n價格: {close:.2f}\n止損: {low_price*0.98:.2f}"
    
    # 買入條件 2: 突破
    elif (close > resistance > prev['close']) and (vol > avg_vol * 1.2) and (macd > 0):
        msg = f"🚀 *[買入信號 - 突破]*\n股票: {symbol}\n價格: {close:.2f}\n目標: {resistance*1.02:.2f}"

    if msg:
        signals.append(msg)
        # 僅針對最後一根 K 線產生的「新信號」發送通知
        # 為了防止重複發送，這裡建議在實際運行時加入 Session State 判斷，暫先提供基礎發送功能
        send_telegram_message(msg)
        
    return signals

# ======================
# UI 介面
# ======================
st.title("💹 多股票監控 & Telegram 報警系統")

with st.sidebar:
    #symbols = st.multiselect("監控清單", ["AAPL", "TSLA", "NVDA", "BTC-USD"], default=["AAPL", "TSLA"])
    symbols = st.text_input("代碼名單", value="TSLA, NIO, TSLL, XPEV, META, GOOGL, AAPL, NVDA, AMZN, MSFT, TSM, GLD, BTC-USD, QQQ").upper()
    auto_refresh = st.toggle("自動刷新", value=True)

if symbols:
    tabs = st.tabs(symbols)
    for i, symbol in enumerate(symbols):
        with tabs[i]:
            df_ind = calculate_indicators(get_stock_data(symbol))
            if df_ind is not None:
                curr = df_ind.iloc[-1]
                
                # 頂部儀表盤
                c1, c2, c3 = st.columns(3)
                c1.metric(f"{symbol} 現價", f"{curr['close']:.2f}")
                c2.metric("阻力位", f"{curr['resistance']:.2f}")
                c3.metric("成交量", f"{int(curr['volume'])}")

                # 圖表 (簡化美化版)
                fig, ax = plt.subplots(figsize=(10, 4))
                ax.plot(df_ind.index, df_ind['close'], color='black', alpha=0.7)
                ax.plot(df_ind.index, df_ind['EMA5'], color='cyan', label='EMA5')
                ax.hlines(curr['resistance'], df_ind.index[0], df_ind.index[-1], colors='red', linestyles='--')
                st.pyplot(fig)

                # 信號顯示
                st.subheader("🔔 即時信號")
                new_signals = generate_signals(df_ind, symbol)
                if new_signals:
                    for s in new_signals: st.success(s)
                else:
                    st.info("目前無新買入信號")

if auto_refresh:
    time.sleep(60)
    st.rerun()
