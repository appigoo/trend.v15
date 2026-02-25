import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt
import time
import requests
from datetime import datetime

# ======================
# 1. 頁面基本配置
# ======================
st.set_page_config(page_title="Advanced Stock Monitor", layout="wide")

# 初始化通知記憶體（防止重複發送）
if 'last_signal_tracker' not in st.session_state:
    st.session_state.last_signal_tracker = {}

# ======================
# 2. 功能函數 (Telegram & 計算)
# ======================
def send_telegram_message(message):
    try:
        token = st.secrets["TELEGRAM_BOT_TOKEN"]
        chat_id = st.secrets["TELEGRAM_CHAT_ID"]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload)
    except Exception as e:
        st.error(f"Telegram 發送失敗: {e}")

def calculate_ema(series, period):
    return series.ewm(alpha=2/(period+1), adjust=False).mean()

def calculate_macd(close):
    ema12 = calculate_ema(close, 12)
    ema26 = calculate_ema(close, 26)
    macd_line = ema12 - ema26
    signal_line = calculate_ema(macd_line, 9)
    return macd_line, signal_line, macd_line - signal_line

@st.cache_data(ttl=60)
def get_stock_data(symbol):
    try:
        df = yf.download(symbol, period="5d", interval="5m", progress=False)
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
# 3. 核心信號邏輯 (含 Telegram 格式化)
# ======================
def process_signals(df, symbol):
    if df is None or len(df) < 30: return []
    
    i = len(df) - 1
    row = df.iloc[i]
    prev = df.iloc[i-1]
    ts = df.index[i].strftime('%H:%M')
    
    # 提取數值
    close, vol, avg_v = row['close'], row['volume'], row['avg_volume']
    macd, macd_s = row['MACD'], row['MACD_signal']
    res = row['resistance']
    
    msg = None
    sig_type = None

    # --- 買入條件 ---
    if (close > row['EMA5'] > row['EMA10']) and (macd > macd_s > prev['MACD_signal']) and (vol > avg_v * 1.2):
        sig_type = "BUY_REVERSAL"
        stop = df['low'].iloc[-10:].min() * 0.98
        msg = f"🟢 *[買入信號 - 反轉]*\n📈 股票: `{symbol}`\n💰 價格: `{close:.2f}`\n🛑 止損: `{stop:.2f}`\n📊 卷比: `{vol/avg_v:.2f}x`"
    
    elif (close > res > prev['close']) and (vol > avg_v * 1.2) and (macd > 0):
        sig_type = "BUY_BREAKOUT"
        target = res * 1.05
        msg = f"🚀 *[買入信號 - 突破]*\n📈 股票: `{symbol}`\n💰 價格: `{close:.2f}`\n🎯 目標: `{target:.2f}`\n🔥 阻力: `{res:.2f}`"

    # --- 賣出條件 ---
    elif (close < row['EMA5'] < row['EMA10']) and (macd < macd_s < prev['MACD_signal']) and (vol > avg_v * 1.2):
        sig_type = "SELL_DANGER"
        msg = f"🔴 *[賣出信號 - 趨勢轉空]*\n📉 股票: `{symbol}`\n💰 價格: `{close:.2f}`\n⚠️ 建議減碼或離場"

    elif (close < res < prev['close']) and (macd < 0):
        sig_type = "SELL_FAILED"
        msg = f"⚠️ *[賣出信號 - 突破失敗]*\n📉 股票: `{symbol}`\n💰 價格: `{close:.2f}`\n❌ 跌回阻力位下方"

    # 發送通知判斷 (同一根K線、同一種信號不重複發)
    if msg:
        tracker_key = f"{symbol}_{df.index[i]}_{sig_type}"
        if tracker_key not in st.session_state.last_signal_tracker:
            send_telegram_message(msg)
            st.session_state.last_signal_tracker[tracker_key] = True
        return [msg]
    
    return []

# ======================
# 4. Streamlit UI 佈局
# ======================
st.title("💹 全能股票監控機器人")

with st.sidebar:
    st.header("設定中心")
    raw_input = st.text_input("輸入監控代碼 (逗號分隔)", value="AAPL, TSLA, NVDA")
    symbols = [s.strip().upper() for s in raw_input.split(",") if s.strip()]
    auto_refresh = st.toggle("開啟自動監控", value=True)
    st.divider()
    st.write("目前監控中:", len(symbols), "隻股票")

if symbols:
    tabs = st.tabs(symbols)
    for i, symbol in enumerate(symbols):
        with tabs[i]:
            data = get_stock_data(symbol)
            if data is not None:
                df = calculate_indicators(data)
                curr = df.iloc[-1]
                
                # 視覺化指標
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("當前價", f"{curr['close']:.2f}")
                c2.metric("20節阻力", f"{curr['resistance']:.2f}")
                c3.metric("MACD Hist", f"{curr['MACD_hist']:.4f}")
                c4.metric("量比", f"{curr['volume']/curr['avg_volume']:.1f}x")

                # 繪圖
                fig, ax = plt.subplots(figsize=(12, 5))
                ax.plot(df.index, df['close'], color='black', label='Price')
                ax.plot(df.index, df['EMA5'], color='#17becf', label='EMA5', alpha=0.8)
                ax.plot(df.index, df['EMA20'], color='#e377c2', label='EMA20', alpha=0.8)
                ax.fill_between(df.index, df['close'], df['resistance'], where=df['close']>=df['resistance'], color='green', alpha=0.1)
                ax.legend()
                st.pyplot(fig)

                # 信號顯示區
                st.subheader("🔔 策略狀態")
                signals = process_signals(df, symbol)
                if signals:
                    for s in signals:
                        if "買入" in s: st.success(s)
                        else: st.warning(s)
                else:
                    st.info("💡 市場波動中，暫無觸發條件")
            else:
                st.error(f"代碼 {symbol} 獲取失敗，請檢查格式。")

# 循環刷新
if auto_refresh:
    time.sleep(60)
    st.rerun()
