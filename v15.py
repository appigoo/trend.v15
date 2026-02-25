#New v.2
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt
import time

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
@st.cache_data(ttl=60)  # 快取 60 秒，避免過度請求
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
    
    # 20期平均成交量
    df['avg_volume'] = df['volume'].rolling(window=20).mean()
    
    # 簡單計算阻力位：近期（前20期）高點
    df['resistance'] = df['high'].rolling(window=20).max().shift(1)  # 移位避免未來數據洩漏
    
    return df

# ======================
# 產生買賣信號 (整合 EMA/MACD/成交量 + 突破阻力策略)
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
        hist = row['MACD_hist']
        vol = row['volume']
        avg_vol = row['avg_volume']
        resistance = row['resistance']
        
        # 買入條件1：EMA/MACD 金叉 + 成交量放大（下跌趨勢反轉）
        if (close > ema5 > ema10) and (macd > macd_sig > prev['MACD_signal']) and (vol > avg_vol * 1.2):
            recent_low = df['low'].iloc[max(0, i-10):i+1].min()
            stop_loss = recent_low * 0.98
            signals.append(f"**買入信號 (EMA/MACD反轉)** @ {close:.2f}  (時間: {df.index[i]}) | 建議買入10股，止損: {stop_loss:.2f}")
        
        # 買入條件2：突破阻力 + 成交量放大 + MACD正向
        elif (close > resistance > prev['close']) and (vol > avg_vol * 1.2) and (macd > 0):
            recent_low = df['low'].iloc[max(0, i-10):i+1].min()
            stop_loss = recent_low * 0.98  # 或設為阻力下方
            next_target = resistance * 1.02  # 預估止盈
            signals.append(f"**買入信號 (突破阻力)** @ {close:.2f}  (時間: {df.index[i]}) | 建議買入10股，止損: {stop_loss:.2f}，目標: {next_target:.2f}")
        
        # 賣出條件1：EMA/MACD 死叉 + 成交量放大（下跌趨勢確認）
        elif (close < ema5 < ema10) and (macd < macd_sig < prev['MACD_signal']) and (vol > avg_vol * 1.2):
            recent_high = df['high'].iloc[max(0, i-10):i+1].max()
            stop_loss = recent_high * 1.02
            signals.append(f"**賣出信號 (EMA/MACD下跌)** @ {close:.2f}  (時間: {df.index[i]}) | 建議賣出10股，止損: {stop_loss:.2f}")
        
        # 賣出條件2：突破失敗（回落破阻力） + MACD負向
        elif (close < resistance < prev['close']) and (macd < 0):
            recent_high = df['high'].iloc[max(0, i-10):i+1].max()
            stop_loss = recent_high * 1.02
            signals.append(f"**賣出信號 (突破失敗)** @ {close:.2f}  (時間: {df.index[i]}) | 建議賣出10股，止損: {stop_loss:.2f}")
    
    return signals[-5:]  # 只顯示最近 5 條

# ======================
# Streamlit 主程式
# ======================
st.title("實時股票監控與買賣建議App（整合突破阻力策略）")
st.markdown("基於EMA、MACD、成交量及突破阻力位，實時監控並給出建議。每60秒自動更新。策略來自圖片分析：下跌趨勢反轉及阻力突破。")

symbol = st.text_input("輸入股票代碼", value="TSLA").upper().strip()
auto_refresh = st.checkbox("自動刷新（每60秒）", value=True)

placeholder = st.empty()

while True:
    with placeholder.container():
        df = get_stock_data(symbol)
        if df is not None:
            df_ind = calculate_indicators(df)
            
            # 顯示最新數據
            st.subheader(f"最新數據 - {symbol} (5分鐘K線)")
            st.dataframe(df_ind.tail(8)[['close','EMA5','EMA10','EMA20','MACD','MACD_signal','MACD_hist','volume', 'resistance']])
            
            # 繪製圖表
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
            
            # 價格 + EMA + 阻力位
            ax1.plot(df_ind.index, df_ind['close'], label='Close', color='black', linewidth=1.2)
            ax1.plot(df_ind.index, df_ind['EMA5'], label='EMA5', color='#1f77b4')
            ax1.plot(df_ind.index, df_ind['EMA10'], label='EMA10', color='#ff7f0e')
            ax1.plot(df_ind.index, df_ind['EMA20'], label='EMA20', color='#2ca02c')
            ax1.plot(df_ind.index, df_ind['resistance'], label='Resistance', color='red', linestyle='--')
            ax1.legend()
            ax1.set_title(f"{symbol} 價格、EMA與阻力位")
            ax1.grid(True, alpha=0.3)
            
            # MACD
            ax2.plot(df_ind.index, df_ind['MACD'], label='MACD', color='#1f77b4')
            ax2.plot(df_ind.index, df_ind['MACD_signal'], label='Signal', color='#ff7f0e')
            ax2.bar(df_ind.index, df_ind['MACD_hist'], label='Histogram', color='gray', alpha=0.5)
            ax2.axhline(0, color='black', linestyle='--', linewidth=0.8)
            ax2.legend()
            ax2.set_title("MACD")
            ax2.grid(True, alpha=0.3)
            
            st.pyplot(fig)
            
            # 買賣建議
            st.subheader("最新買賣信號")
            signals = generate_signals(df_ind)
            if signals:
                for sig in signals:
                    if "買入" in sig:
                        st.success(sig)
                    else:
                        st.warning(sig)
            else:
                st.info("目前無明確買賣信號")
    
    if not auto_refresh:
        st.stop()
    
    time.sleep(60)
    st.rerun()
