import streamlit as st
import yfinance as yf
import pandas as pd
import ta

st.set_page_config(layout="wide")
st.title("📊 空頭趨勢三階段掃描系統")

symbol = st.text_input("股票代碼", "TSLA")
interval = st.selectbox("時間週期", ["5m","15m","30m"])
period = st.selectbox("資料期間", ["5d","1mo"])

if st.button("開始分析"):

    df = yf.download(symbol, interval=interval, period=period)

    if df.empty:
        st.error("無資料")
    else:

        # ===== 指標 =====
        df["EMA5"] = ta.trend.ema_indicator(df["Close"], 5)
        df["EMA10"] = ta.trend.ema_indicator(df["Close"], 10)
        df["EMA20"] = ta.trend.ema_indicator(df["Close"], 20)
        df["EMA60"] = ta.trend.ema_indicator(df["Close"], 60)

        macd = ta.trend.MACD(df["Close"])
        df["DIF"] = macd.macd()
        df["DEA"] = macd.macd_signal()
        df["MACD"] = macd.macd_diff()

        df["ATR"] = ta.volatility.average_true_range(
            df["High"], df["Low"], df["Close"], 14
        )

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        price = latest["Close"]

        # ===== 階段判斷 =====

        bearish_alignment = (
            latest["EMA5"] < latest["EMA10"] <
            latest["EMA20"] < latest["EMA60"]
        )

        rebound = (
            latest["EMA5"] > latest["EMA20"] and
            latest["DIF"] > prev["DIF"]
        )

        rejection = (
            price < latest["EMA60"] and
            latest["MACD"] < prev["MACD"]
        )

        stage = ""
        action = ""
        stop_loss = None

        if bearish_alignment and latest["DIF"] < 0:
            stage = "🔴 主跌段"
            action = f"現價 {round(price,2)} 賣出 10 股"
            stop_loss = price + 1.5 * latest["ATR"]

        elif rebound:
            stage = "🟡 空頭反彈"
            action = f"現價 {round(price,2)} 買入 10 股（短線）"
            stop_loss = price - 1.0 * latest["ATR"]

        elif rejection:
            stage = "🔴 反彈衰竭再轉空"
            action = f"現價 {round(price,2)} 賣出 10 股"
            stop_loss = price + 1.2 * latest["ATR"]

        else:
            stage = "⚪ 盤整"
            action = "觀望"

        # ===== 顯示 =====

        st.subheader("📍 當前市場階段")
        st.write(stage)

        st.subheader("📌 交易建議")
        st.write(action)

        if stop_loss:
            st.write("建議止損:", round(stop_loss,2))

        st.line_chart(df[["Close","EMA20","EMA60"]])
