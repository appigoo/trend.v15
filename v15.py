import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt
import time
from concurrent.futures import ThreadPoolExecutor  # 加速多股票下載

# ======================
# 手動計算 EMA
# ======================
def calculate_ema(series, period):
    alpha = 2 / (period + 1)
    return series.ewm(alpha=alpha, adjust=False).mean()

# ======================
# 手動計算 MACD
# ======================
def calculate_macd(close, fast=12, slow=26, signal=9):
    ema_fast = calculate_ema(close, fast)
    ema_slow = calculate_ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

# ======================
# 獲取單檔股票數據
# ======================
def fetch_single_stock(symbol):
    try:
        df = yf.download(symbol, period="5d", interval="5m", progress=False)
        if df.empty:
            print(f"Empty data for {symbol}")
            return symbol, None
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
        df.columns = ['open', 'high', 'low', 'close', 'volume']
        df.index.name = 'timestamp'
        print(f"Success: {symbol} - rows: {len(df)}, last close: {df['close'].iloc[-1]}")
        return symbol, df
    except Exception as e:
        print(f"Error for {symbol}: {e}")
        return symbol, None

# ======================
# 計算指標（含阻力位）
# ======================
def calculate_indicators(df):
    if df is None or len(df) < 50:
        return None
    
    df = df.copy()
    df['EMA5']  = calculate_ema(df['close'], 5)
    df['EMA10'] = calculate_ema(df['close'], 10)
    df['EMA20'] = calculate_ema(df['close'], 20)
    
    df['MACD'], df['MACD_signal'], df['MACD_hist'] = calculate_macd(df['close'])
    
    df['avg_volume'] = df['volume'].rolling(window=20).mean()
    
    # 阻力位：前20期最高點（移位避免前瞻）
    df['resistance'] = df['high'].rolling(window=20).max().shift(1)
    
    return df

# ======================
# 產生信號（整合所有策略）
# ======================
def generate_signals(df, symbol):
    if df is None or len(df) < 30:
        return []
    
    signals = []
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    close = latest['close']
    ema5 = latest['EMA5']
    ema10 = latest['EMA10']
    macd = latest['MACD']
    macd_sig = latest['MACD_signal']
    vol = latest['volume']
    avg_vol = latest['avg_volume']
    resistance = latest['resistance']
    
    # 買入1：EMA/MACD 金叉 + 量放大
    if (close > ema5 > ema10) and (macd > macd_sig > prev['MACD_signal']) and (vol > avg_vol * 1.2):
        stop_loss = df['low'].iloc[-10:].min() * 0.98
        signals.append(f"**買入 (EMA/MACD反轉)** @ {close:.2f} | 止損 {stop_loss:.2f}")
    
    # 買入2：突破阻力 + 量放大 + MACD > 0
    if (close > resistance > prev['close']) and (vol > avg_vol * 1.2) and (macd > 0):
        stop_loss = df['low'].iloc[-10:].min() * 0.98
        target = resistance * 1.03
        signals.append(f"**買入 (突破阻力)** @ {close:.2f} | 止損 {stop_loss:.2f} 目標 {target:.2f}")
    
    # 賣出1：EMA/MACD 死叉 + 量放大
    if (close < ema5 < ema10) and (macd < macd_sig < prev['MACD_signal']) and (vol > avg_vol * 1.2):
        stop_loss = df['high'].iloc[-10:].max() * 1.02
        signals.append(f"**賣出 (EMA/MACD下跌)** @ {close:.2f} | 止損 {stop_loss:.2f}")
    
    # 賣出2：回落破阻力 + MACD < 0
    if (close < resistance < prev['close']) and (macd < 0):
        stop_loss = df['high'].iloc[-10:].max() * 1.02
        signals.append(f"**賣出 (突破失敗)** @ {close:.2f} | 止損 {stop_loss:.2f}")
    
    return signals

# ======================
# Streamlit App
# ======================
st.set_page_config(page_title="多股票實時掃描器", layout="wide")
st.title("多股票實時掃描與買賣建議（2026版）")
st.markdown("同時監控多檔股票，整合 EMA/MACD + 突破阻力策略。每 60 秒自動更新。")

# 預設股票清單（可編輯）
default_tickers = "AAPL,NVDA,MSFT,GOOGL,META,AMD,TSLA,AMZN,INTC,PYPL"
tickers_input = st.text_input("輸入股票代碼（用逗號分隔）", value=default_tickers)
tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]

auto_refresh = st.checkbox("自動刷新（每60秒）", value=True)
max_stocks_per_page = 10  # 避免過多圖表卡住

if not tickers:
    st.warning("請輸入至少一檔股票代碼")
else:
    with st.spinner(f"正在載入 {len(tickers)} 檔股票數據..."):
        # 使用 ThreadPoolExecutor 加速下載
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(fetch_single_stock, tickers))
    
    data_dict = {}
    for sym, df in results:
        if df is not None:
            if sym in data_dict:
                print(f"Duplicate key warning: {sym}")
            data_dict[sym] = df
    
    if not data_dict:
        st.error("所有股票數據載入失敗，請檢查網路或代碼")
    else:
        # 總覽表格
        summary_data = []
        for sym, df in data_dict.items():
            df_ind = calculate_indicators(df)
            if df_ind is None:
                continue
            latest = df_ind.iloc[-1]
            signals = generate_signals(df_ind, sym)
            signal_str = " / ".join(signals) if signals else "無訊號"
            summary_data.append({
                "股票": sym,
                "最新價": f"{latest['close']:.2f}",
                "漲跌%": f"{(latest['close']/df_ind.iloc[-2]['close']-1)*100:.2f}%",
                "成交量": f"{latest['volume']/1e6:.2f}M",
                "阻力位": f"{latest['resistance']:.2f}" if not pd.isna(latest['resistance']) else "N/A",
                "MACD": f"{latest['MACD']:.3f} (Hist: {latest['MACD_hist']:.3f})",
                "信號": signal_str
            })
        
        st.subheader("所有股票總覽")
        summary_df = pd.DataFrame(summary_data)
        st.dataframe(summary_df.style.apply(
            lambda row: ['background-color: #d4edda' if '買入' in row['信號'] else 
                         'background-color: #f8d7da' if '賣出' in row['信號'] else '' 
                         for _ in row], axis=1),
            use_container_width=True)
        
        # 展開個股詳情
        st.subheader("個股詳情與圖表（點擊展開）")
        for sym, df in list(data_dict.items())[:max_stocks_per_page]:
            with st.expander(f"{sym} - 最新價 {df['close'].iloc[-1]:.2f}"):
                df_ind = calculate_indicators(df)
                if df_ind is not None:
                    signals = generate_signals(df_ind, sym)
                    if signals:
                        for sig in signals:
                            if "買入" in sig:
                                st.success(sig)
                            else:
                                st.warning(sig)
                    else:
                        st.info("目前無明確信號")
                    
                    # 簡化圖表
                    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
                    ax1.plot(df_ind['close'], label='Close', color='black')
                    ax1.plot(df_ind['EMA5'], label='EMA5')
                    ax1.plot(df_ind['EMA10'], label='EMA10')
                    ax1.plot(df_ind['EMA20'], label='EMA20')
                    ax1.plot(df_ind['resistance'], '--', label='Resistance', color='red')
                    ax1.legend()
                    ax1.set_title(f"{sym} 價格與 EMA/阻力")
                    
                    ax2.bar(df_ind.index, df_ind['MACD_hist'], label='Hist', color='gray', alpha=0.6)
                    ax2.plot(df_ind['MACD'], label='MACD')
                    ax2.plot(df_ind['MACD_signal'], label='Signal')
                    ax2.axhline(0, color='black', ls='--')
                    ax2.legend()
                    ax2.set_title("MACD")
                    
                    st.pyplot(fig)
                else:
                    st.warning("數據不足以計算指標")

st.caption("注意：此為教育/參考工具，非投資建議。股市有風險，數據來自 yfinance，可能有延遲。")

# 自動刷新邏輯
if auto_refresh:
    time.sleep(60)
    st.rerun()
