import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt
import time
import requests

# ======================
# 手動計算 EMA 的函數
# ======================
def calculate_ema(series, period):
    alpha = 2 / (period + 1)
    ema = series.ewm(alpha=alpha, adjust=False).mean()
    return ema

# ======================
# 手動計算 MACD 的函數
# ======================
def calculate_macd(close, fast=12, slow=26, signal=9):
    ema_fast = calculate_ema(close, fast)
    ema_slow = calculate_ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

# ======================
# 獲取股票數據 (使用 yfinance)
# ======================
@st.cache_data(ttl=60)
def get_stock_data(symbol, period="5d", interval="5m"):
    try:
        df = yf.download(symbol, period=period, interval=interval, progress=False)
        if df.empty:
            st.error(f"無法獲取 {symbol} 的數據，請檢查代碼或網路")
            return None
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
        df.columns = ['open', 'high', 'low', 'close', 'volume']
        df.index.name = 'timestamp'
        return df
    except Exception as e:
        st.error(f"下載數據失敗: {e}")
        return None

# ======================
# 計算所有指標，包括阻力位
# ======================
def calculate_indicators(df):
    if df is None or len(df) < 50:
        return df
    
    df = df.copy()
    df['EMA5']  = calculate_ema(df['close'], 5)
    df['EMA10'] = calculate_ema(df['close'], 10)
    df['EMA20'] = calculate_ema(df['close'], 20)
    
    df['MACD'], df['MACD_signal'], df['MACD_hist'] = calculate_macd(df['close'])
    
    df['avg_volume'] = df['volume'].rolling(window=20).mean()
    
    df['resistance'] = df['high'].rolling(window=20).max().shift(1)
    
    return df

# ======================
# 產生買賣信號
# ======================
def generate_signals(df):
    if df is None or len(df) < 30:
        return []
    
    signals = []
    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i-1]
        
        close = row['close']
        ema5 = row['EMA5']
        ema10 = row['EMA10']
        macd = row['MACD']
        macd_sig = row['MACD_signal']
        vol = row['volume']
        avg_vol = row['avg_volume']
        resistance = row['resistance']
        
        if (close > ema5 > ema10) and (macd > macd_sig > prev['MACD_signal']) and (vol > avg_vol * 1.2):
            recent_low = df['low'].iloc[max(0, i-10):i+1].min()
            stop_loss = recent_low * 0.98
            signals.append(f"**買入信號 (EMA/MACD反轉)** @ {close:.2f}  (時間: {df.index[i]}) | 建議買入10股，止損: {stop_loss:.2f}")
        
        elif (close > resistance > prev['close']) and (vol > avg_vol * 1.2) and (macd > 0):
            recent_low = df['low'].iloc[max(0, i-10):i+1].min()
            stop_loss = recent_low * 0.98
            next_target = resistance * 1.02
            signals.append(f"**買入信號 (突破阻力)** @ {close:.2f}  (時間: {df.index[i]}) | 建議買入10股，止損: {stop_loss:.2f}，目標: {next_target:.2f}")
        
        elif (close < ema5 < ema10) and (macd < macd_sig < prev['MACD_signal']) and (vol > avg_vol * 1.2):
            recent_high = df['high'].iloc[max(0, i-10):i+1].max()
            stop_loss = recent_high * 1.02
            signals.append(f"**賣出信號 (EMA/MACD下跌)** @ {close:.2f}  (時間: {df.index[i]}) | 建議賣出10股，止損: {stop_loss:.2f}")
        
        elif (close < resistance < prev['close']) and (macd < 0):
            recent_high = df['high'].iloc[max(0, i-10):i+1].max()
            stop_loss = recent_high * 1.02
            signals.append(f"**賣出信號 (突破失敗)** @ {close:.2f}  (時間: {df.index[i]}) | 建議賣出10股，止損: {stop_loss:.2f}")
    
    return signals[-5:]

# ======================
# 使用 requests 發送 Telegram 訊息
# ======================
def send_telegram_message(bot_token, chat_id, text):
    if not bot_token or not chat_id:
        return False, "Telegram 配置缺失"
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return True, "發送成功"
        else:
            return False, f"Telegram API 錯誤: {response.status_code} - {response.text}"
    except Exception as e:
        return False, f"發送失敗: {str(e)}"

# ======================
# Streamlit 主程式
# ======================
st.title("實時股票監控與買賣建議App（整合突破阻力策略）")
st.markdown("基於EMA、MACD、成交量及突破阻力位，實時監控並給出建議。每60秒自動更新。")

symbols_input = st.text_input("輸入股票代碼，用逗號分隔", value="TSLA").upper().strip()
symbols = [s.strip() for s in symbols_input.split(',') if s.strip()]
auto_refresh = st.checkbox("自動刷新（每60秒）", value=True)

# 初始化已發送記錄
if 'sent_signals' not in st.session_state:
    st.session_state.sent_signals = {symbol: [] for symbol in symbols}

# 從 secrets 讀取 Telegram 設定
TELEGRAM_BOT_TOKEN = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = st.secrets.get("TELEGRAM_CHAT_ID", "")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    st.warning("Telegram Bot Token 或 Chat ID 未在 secrets 中設定，通知功能將禁用。")

placeholder = st.empty()

while True:
    with placeholder.container():
        if symbols:
            tabs = st.tabs(symbols)
            for idx, symbol in enumerate(symbols):
                with tabs[idx]:
                    df = get_stock_data(symbol)
                    if df is not None:
                        df_ind = calculate_indicators(df)
                        
                        with st.expander(f"最新數據 - {symbol} (5分鐘K線)", expanded=True):
                            st.dataframe(
                                df_ind.tail(8)[['close','EMA5','EMA10','EMA20','MACD','MACD_signal','MACD_hist','volume', 'resistance']]
                                .style.format("{:.2f}")
                            )
                        
                        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True, gridspec_kw={'height_ratios': [3, 1]})
                        
                        ax1.plot(df_ind.index, df_ind['close'], label='Close', color='black', linewidth=1.2)
                        ax1.plot(df_ind.index, df_ind['EMA5'], label='EMA5', color='#1f77b4')
                        ax1.plot(df_ind.index, df_ind['EMA10'], label='EMA10', color='#ff7f0e')
                        ax1.plot(df_ind.index, df_ind['EMA20'], label='EMA20', color='#2ca02c')
                        ax1.plot(df_ind.index, df_ind['resistance'], label='Resistance', color='red', linestyle='--')
                        ax1.legend(loc='upper left')
                        ax1.set_title(f"{symbol} 價格、EMA與阻力位")
                        ax1.grid(True, alpha=0.3)
                        ax1.set_ylabel('價格')
                        
                        ax2.plot(df_ind.index, df_ind['MACD'], label='MACD', color='#1f77b4')
                        ax2.plot(df_ind.index, df_ind['MACD_signal'], label='Signal', color='#ff7f0e')
                        ax2.bar(df_ind.index, df_ind['MACD_hist'], 
                                color=np.where(df_ind['MACD_hist'] >= 0, 'green', 'red'), alpha=0.6)
                        ax2.axhline(0, color='black', linestyle='--', linewidth=0.8)
                        ax2.legend(loc='upper left')
                        ax2.set_title("MACD")
                        ax2.grid(True, alpha=0.3)
                        ax2.set_ylabel('MACD 值')
                        
                        st.pyplot(fig)
                        
                        st.subheader("最新買賣信號")
                        signals = generate_signals(df_ind)
                        if signals:
                            for sig in signals:
                                full_sig = f"[{symbol}] {sig}"
                                if full_sig not in st.session_state.sent_signals.get(symbol, []):
                                    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
                                        success, msg = send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, full_sig)
                                        if success:
                                            st.session_state.sent_signals[symbol].append(full_sig)
                                        else:
                                            st.error(f"Telegram 通知失敗 ({symbol}): {msg}")
                                if "買入" in sig:
                                    st.success(full_sig)
                                else:
                                    st.warning(full_sig)
                        else:
                            st.info("目前無明確買賣信號")
        else:
            st.info("請輸入至少一個股票代碼")
    
    if not auto_refresh:
        break
    
    time.sleep(60)
    st.rerun()
