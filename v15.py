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
st.set_page_config(page_title="Pro Stock Monitor v3", layout="wide")

# 初始化通知記憶體：確保同一分鐘內，同一種信號不會重複發送 Telegram
if 'last_signal_tracker' not in st.session_state:
    st.session_state.last_signal_tracker = {}

# ======================
# 2. Telegram 發送函數 (詳細說明版)
# ======================
def send_telegram_message(message):
    """
    透過 Telegram Bot API 發送訊息。
    參數:
        message: 欲發送的字串內容，支援 Markdown 格式。
    配置要求:
        需在 Streamlit Secrets 中設定 TELEGRAM_BOT_TOKEN 與 TELEGRAM_CHAT_ID。
    """
    try:
        # 從 st.secrets 安全取得憑證
        token = st.secrets["TELEGRAM_BOT_TOKEN"]
        chat_id = st.secrets["TELEGRAM_CHAT_ID"]
        
        # Telegram API 端點
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        
        # 設定發送參數：使用 Markdown 讓訊息排版更專業
        payload = {
            "chat_id": chat_id, 
            "text": message, 
            "parse_mode": "Markdown"
        }
        
        # 發送 POST 請求
        response = requests.post(url, json=payload, timeout=10)
        
        # 檢查是否發送成功
        if response.status_code != 200:
            st.error(f"Telegram API 返回錯誤: {response.text}")
    except Exception as e:
        st.error(f"無法發送 Telegram 通知: {e}")

# ======================
# 3. 技術指標計算 (保持原算法完整)
# ======================
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
# 4. 買賣信號判斷 + 詳細訊息封裝
# ======================
def process_signals(df, symbol):
    if df is None or len(df) < 30: return []
    
    i = len(df) - 1
    row = df.iloc[i]
    prev = df.iloc[i-1]
    
    # 提取詳細數據用於 Telegram 報告
    close = row['close']
    vol_ratio = row['volume'] / row['avg_volume'] if row['avg_volume'] > 0 else 0
    macd_val = row['MACD']
    res_level = row['resistance']
    timestamp = df.index[i].strftime('%Y-%m-%d %H:%M')
    
    msg = None
    sig_type = None

    # --- 買入邏輯 1: EMA/MACD 反轉 ---
    if (close > row['EMA5'] > row['EMA10']) and (macd_val > row['MACD_signal'] > prev['MACD_signal']) and (vol_ratio > 1.2):
        sig_type = "BUY_REVERSAL"
        stop_loss = df['low'].iloc[-10:].min() * 0.98
        msg = (
            f"🟢 *[買入信號：反轉趨勢]*\n"
            f"📈 股票代碼: `{symbol}`\n"
            f"⏰ 觸發時間: `{timestamp}`\n"
            f"💰 當前價格: `{close:.2f}`\n"
            f"🛑 建議止損: `{stop_loss:.2f}`\n\n"
            f"📊 **詳細指標數據**:\n"
            f"• 量比 (Volume Ratio): `{vol_ratio:.2f}x` (放量)\n"
            f"• MACD 狀態: `{macd_val:.4f}` (金叉)\n"
            f"• 均線狀態: `EMA5 > EMA10` (多頭)"
        )

    # --- 買入邏輯 2: 突破阻力 ---
    elif (close > res_level > prev['close']) and (vol_ratio > 1.2) and (macd_val > 0):
        sig_type = "BUY_BREAKOUT"
        target = res_level * 1.05
        msg = (
            f"🚀 *[買入信號：強力突破]*\n"
            f"📈 股票代碼: `{symbol}`\n"
            f"⏰ 觸發時間: `{timestamp}`\n"
            f"💰 當前價格: `{close:.2f}`\n"
            f"🎯 預期目標: `{target:.2f}`\n\n"
            f"📊 **詳細指標數據**:\n"
            f"• 突破阻力位: `{res_level:.2f}`\n"
            f"• 量比 (Volume Ratio): `{vol_ratio:.2f}x` (突破量)\n"
            f"• MACD 方向: `正向 (Bullish)`"
        )

    # --- 賣出邏輯 1: 轉向下跌 ---
    elif (close < row['EMA5'] < row['EMA10']) and (macd_val < row['MACD_signal'] < prev['MACD_signal']) and (vol_ratio > 1.2):
        sig_type = "SELL_DANGER"
        msg = (
            f"🔴 *[賣出信號：空頭確認]*\n"
            f"📉 股票代碼: `{symbol}`\n"
            f"💰 離場價格: `{close:.2f}`\n"
            f"⚠️ **警告**: EMA 均線死叉且放量下跌，建議減碼。"
        )

    # --- 賣出邏輯 2: 突破失敗 ---
    elif (close < res_level < prev['close']) and (macd_val < 0):
        sig_type = "SELL_FAILED"
        msg = (
            f"⚠️ *[賣出信號：突破失敗]*\n"
            f"📉 股票代碼: `{symbol}`\n"
            f"💰 離場價格: `{close:.2f}`\n"
            f"❌ **說明**: 價格跌回阻力位 `{res_level:.2f}` 下方，MACD 為負，假突破風險高。"
        )

    # 防重複發送邏輯：檢查 (股票+時間+信號類型)
    if msg:
        tracker_key = f"{symbol}_{df.index[i]}_{sig_type}"
        if tracker_key not in st.session_state.last_signal_tracker:
            send_telegram_message(msg)
            st.session_state.last_signal_tracker[tracker_key] = True
        return [msg]
    
    return []

# ======================
# 5. Streamlit 主頁面 UI
# ======================
st.title("💹 專業級多股票實時監控系統")

with st.sidebar:
    st.header("控制面板")
    input_str = st.text_input("輸入股票代碼 (逗號分隔)", value="TSLA, NIO, TSLL, XPEV, META, GOOGL, AAPL, NVDA, AMZN, MSFT, TSM, GLD, BTC-USD, QQQ")
    symbols = [s.strip().upper() for s in input_str.split(",") if s.strip()]
    auto_refresh = st.toggle("開啟 60s 自動刷新", value=True)
    st.info("支援格式: AAPL, 2330.TW, BTC-USD")

if symbols:
    tabs = st.tabs(symbols)
    for i, symbol in enumerate(symbols):
        with tabs[i]:
            raw_data = get_stock_data(symbol)
            if raw_data is not None:
                df_ind = calculate_indicators(raw_data)
                curr = df_ind.iloc[-1]
                
                # 頂部即時數據卡
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("當前價", f"{curr['close']:.2f}")
                c2.metric("阻力位", f"{curr['resistance']:.2f}")
                c3.metric("量比", f"{curr['volume']/curr['avg_volume']:.2f}x")
                c4.metric("MACD 柱", f"{curr['MACD_hist']:.4f}")

                # 圖表展示
                fig, ax = plt.subplots(figsize=(10, 4))
                ax.plot(df_ind.index, df_ind['close'], color='black', label='Price')
                ax.plot(df_ind.index, df_ind['EMA5'], label='EMA5', alpha=0.7)
                ax.plot(df_ind.index, df_ind['EMA20'], label='EMA20', alpha=0.7)
                ax.hlines(curr['resistance'], df_ind.index[0], df_ind.index[-1], colors='r', linestyles='--')
                ax.legend(loc='best')
                st.pyplot(fig)

                # 信號顯示區
                st.subheader("🔔 實時策略監控")
                sigs = process_signals(df_ind, symbol)
                if sigs:
                    for s in sigs:
                        if "買入" in s: st.success(s)
                        else: st.warning(s)
                else:
                    st.info("目前無觸發信號，系統持續監控中...")
            else:
                st.error(f"無法獲取 {symbol} 的數據。")

if auto_refresh:
    time.sleep(60)
    st.rerun()
