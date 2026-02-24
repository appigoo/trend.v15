import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go

# --- 頁面設定 ---
st.set_page_config(page_title="AI 股票趨勢掃描器", layout="wide")
st.title("📈 均線與 MACD 自動交易策略掃描器")

# --- 側邊欄：參數設定 ---
st.sidebar.header("設定參數")
ticker = st.sidebar.text_input("輸入股票代碼 (例如: AAPL, TSLA, 2330.TW)", value="AAPL")
interval = st.sidebar.selectbox("K線週期", ["5m", "15m", "1h", "1d"], index=0)
period = st.sidebar.selectbox("抓取時間範圍", ["5d", "1mo", "3mo", "1y"], index=0)

@st.cache_data
def load_data(ticker, period, interval):
    df = yf.download(ticker, period=period, interval=interval)
    if df.empty:
        return df
    
    # 確保欄位名稱為一維
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
        
    # 計算 EMA
    df['EMA5'] = df['Close'].ewm(span=5, adjust=False).mean()
    df['EMA10'] = df['Close'].ewm(span=10, adjust=False).mean()
    df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
    
    # 計算 MACD
    df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
    df['EMA26'] = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = df['EMA12'] - df['EMA26']
    df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['DIF'] - df['DEA']
    
    return df

df = load_data(ticker, period, interval)

if df.empty:
    st.warning("找不到該股票的數據，請確認代碼與週期是否支援。")
else:
    # --- 繪製技術線圖 ---
    fig = go.Figure()
    
    # K線圖
    fig.add_trace(go.Candlestick(x=df.index,
                open=df['Open'], high=df['High'],
                low=df['Low'], close=df['Close'],
                name='K線'))
    
    # 加入 EMA
    fig.add_trace(go.Scatter(x=df.index, y=df['EMA5'], line=dict(color='green', width=1.5), name='EMA5'))
    fig.add_trace(go.Scatter(x=df.index, y=df['EMA10'], line=dict(color='orange', width=1.5), name='EMA10'))
    fig.add_trace(go.Scatter(x=df.index, y=df['EMA20'], line=dict(color='blue', width=1.5), name='EMA20'))

    fig.update_layout(title=f"{ticker} 價格走勢與均線", xaxis_rangeslider_visible=False, height=500)
    st.plotly_chart(fig, use_container_width=True)

    # --- 策略掃描邏輯 ---
    st.subheader("🤖 最新交易信號判定")
    
    # 取得最新兩筆資料來判斷交叉
    last_row = df.iloc[-1]
    prev_row = df.iloc[-2]
    
    current_price = round(last_row['Close'], 2)
    
    # 多方條件：EMA5 金叉 EMA10 + DIF > DEA + 價格在 EMA20 之上
    buy_signal = (prev_row['EMA5'] <= prev_row['EMA10']) and (last_row['EMA5'] > last_row['EMA10']) and \
                 (last_row['DIF'] > last_row['DEA']) and (current_price > last_row['EMA20'])
                 
    # 空方條件：EMA5 死叉 EMA10 + DIF < DEA + 價格在 EMA20 之下
    sell_signal = (prev_row['EMA5'] >= prev_row['EMA10']) and (last_row['EMA5'] < last_row['EMA10']) and \
                  (last_row['DIF'] < last_row['DEA']) and (current_price < last_row['EMA20'])

    # --- 輸出結果 ---
    if buy_signal:
        stop_loss = round(current_price * 0.985, 2) # 1.5% 止損設定
        st.success(f"🟢 **強烈買入信號**\n\n出現買入信號！現在以 **${current_price}** 價買入 10 股，同時設定 **${stop_loss}** 價止損。")
    elif sell_signal:
        stop_loss = round(current_price * 1.015, 2) # 1.5% 止損設定
        st.error(f"🔴 **強烈賣出/做空信號**\n\n出現賣出信號！現在以 **${current_price}** 價賣出 10 股，同時設定 **${stop_loss}** 價止損。")
    else:
        st.info(f"⚪ **目前無強烈交易信號**\n\n目前最新價格為 **${current_price}**，均線與 MACD 未出現明確的共振交叉，建議持續觀望。")
        
    # 顯示原始數據供參考
    with st.expander("查看近期詳細數據"):
        st.dataframe(df[['Close', 'EMA5', 'EMA10', 'EMA20', 'DIF', 'DEA']].tail(10))
