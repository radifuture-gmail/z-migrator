import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import base64
import json
from datetime import datetime, timedelta

# ページ設定
st.set_page_config(page_title="Portfolio Migration Analyzer", layout="wide")

# --- ユーティリティ関数 ---
def decode_base64_to_json(b64_str):
    try:
        # URLエンコードされた%3Dなどをデコードしてからbase64復号
        padding = '=' * (4 - len(b64_str) % 4)
        json_str = base64.b64decode(b64_str + padding).decode('utf-8')
        return json.loads(json_str)
    except Exception as e:
        return None

def get_portfolio_tickers(config):
    if not config or "assets" not in config:
        return []
    return [asset["ticker"] for asset in config["assets"]]

# --- 1. 初期設定とデータ読み込み ---
st.title("🔄 ポートフォリオ移行タイミング判定 (Z-Score)")

# デフォルトのBase64（提示されたもの）
default_b64_before = "eyJ0b3RhbF9pbnZlc3RtZW50IjogMTAwMDAuMCwgInJpc2tfZnJlZV9yYXRlIjogMC4wLCAicmViYWxhbmNlX2ZyZXEiOiAiV2Vla2x5IiwgInN0YXJ0X2RhdGUiOiAiMjAyNS0wMi0yMyIsICJhc3NldHMiOiBbeyJ0aWNrZXIiOiAiU1BZIiwgInR5cGUiOiAiTG9uZyIsICJhbGxvY2F0aW9uX3BjdCI6IDUwLjAsICJtYXJnaW5fcmF0aW8iOiAxMDAuMH0sIHsidGlja2VyIjogIlRMVCIsICJ0eXBlIjogIkxvbmciLCAiYWxsb2NhdGlvbl9wY3QiOiAzMC4wLCAibWFyZ2luX3JhdGlvIjogMTAwLjB9XX0="
# サンプル用After（QQQとGLDの構成例）
default_b64_after = "eyJ0b3RhbF9pbnZlc3RtZW50IjogMTAwMDAuMCwgInJpc2tfZnJlZV9yYXRlIjogMC4wLCAicmViYWxhbmNlX2ZyZXEiOiAiV2Vla2x5IiwgInN0YXJ0X2RhdGUiOiAiMjAyNS0wMi0yMyIsICJhc3NldHMiOiBbeyJ0aWNrZXIiOiAiUVFRIiwgInR5cGUiOiAiTG9uZyIsICJhbGxvY2F0aW9uX3BjdCI6IDcwLjAsICJtYXJnaW5fcmF0aW8iOiAxMDAuMH0sIHsidGlja2VyIjogIkdMRCIsICJ0eXBlIjogIkxvbmciLCAiYWxsb2NhdGlvbl9wY3QiOiAzMC4wLCAibWFyZ2luX3JhdGlvIjogMTAwLjB9XX0="

with st.sidebar:
    st.header("⚙️ 設定")
    window = st.slider("分析期間 (移動平均日数)", 50, 300, 120)
    z_threshold = st.slider("移行判断しきい値 (Zスコア)", 0.5, 3.0, 1.0, 0.1)
    
    st.markdown("---")
    b64_before_input = st.text_area("Before ポートフォリオ (Base64)", default_b64_before, height=100)
    b64_after_input = st.text_area("After ポートフォリオ (Base64)", default_b64_after, height=100)

# デコード実行
config_before = decode_base64_to_json(b64_before_input)
config_after = decode_base64_to_json(b64_after_input)

if not config_before or not config_after:
    st.error("Base64データのデコードに失敗しました。正しい形式か確認してください。")
    st.stop()

# --- 2. データ取得とポートフォリオ指数の計算 ---
all_tickers = list(set(get_portfolio_tickers(config_before) + get_portfolio_tickers(config_after)))

@st.cache_data(ttl=3600)
def fetch_data(tickers):
    data = yf.download(tickers, period="2y", auto_adjust=True)['Close']
    return data

try:
    with st.spinner('市場データを取得中...'):
        price_df = fetch_data(all_tickers)

    # 各ポートフォリオの加重平均価格（指数）を算出
    def calc_portfolio_index(price_df, config):
        portfolio_price = pd.Series(0.0, index=price_df.index)
        for asset in config["assets"]:
            ticker = asset["ticker"]
            weight = asset["allocation_pct"] / 100.0
            # 初日の価格で標準化して、構成比率を掛ける
            normalized_series = price_df[ticker] / price_df[ticker].iloc[0]
            portfolio_price += normalized_series * weight
        return portfolio_price

    df_results = pd.DataFrame(index=price_df.index)
    df_results['Before_Index'] = calc_portfolio_index(price_df, config_before)
    df_results['After_Index'] = calc_portfolio_index(price_df, config_after)

    # --- 3. 移行判定ロジック (Z-Score) ---
    # Log Ratio: log(After) - log(Before) 
    # これがマイナスに振れる = AfterがBeforeに対して割安
    df_results['Log_Ratio'] = np.log(df_results['After_Index']) - np.log(df_results['Before_Index'])
    df_results['Mean'] = df_results['Log_Ratio'].rolling(window=window).mean()
    df_results['Std'] = df_results['Log_Ratio'].rolling(window=window).std()
    df_results['Z_Score'] = (df_results['Log_Ratio'] - df_results['Mean']) / df_results['Std']

    latest = df_results.iloc[-1]
    prev = df_results.iloc[-2]
    current_z = latest['Z_Score']

    # --- 4. メイン表示 ---
    st.subheader("分析結果")
    c1, c2, c3 = st.columns(3)
    
    with c1:
        st.metric("現在のZスコア", f"{current_z:.2f}", delta=f"{current_z - prev['Z_Score']:.2f}", delta_color="inverse")
        st.caption("マイナスが大きいほど『After』が相対的に割安")

    with c2:
        if current_z < -z_threshold:
            status, color, instruction = "✅ 移行推奨 (今すぐ)", "green", "Afterポートフォリオが相対的に割安です。移行の好機です。"
        elif current_z > z_threshold:
            status, color, instruction = "⚠️ 待機 (移行非推奨)", "red", "Afterが相対的に割高です。Before維持を推奨。"
        else:
            status, color, instruction = "☕ ニュートラル", "gray", "大きな乖離はありません。計画通りの移行を検討してください。"
        
        st.markdown(f"### 判定: :{color}[{status}]")
        st.write(instruction)

    with c3:
        # 構成銘柄の確認
        with st.expander("構成銘柄を確認"):
            st.write("**Before:**", ", ".join(get_portfolio_tickers(config_before)))
            st.write("**After:**", ", ".join(get_portfolio_tickers(config_after)))


    # --- ポートフォリオ構成の比較テーブル ---
    st.markdown("---")
    st.subheader("📋 ポートフォリオ構成の比較")

    col_table1, col_table2 = st.columns(2)

    with col_table1:
        st.markdown("**【Before】現在の構成**")
        df_before = pd.DataFrame(config_before["assets"])[["ticker", "allocation_pct"]]
        df_before.columns = ["銘柄", "配分 (%)"]
        st.table(df_before.set_index("銘柄"))
        st.info(f"合計投資額: ${config_before.get('total_investment', 0):,.2f}")

    with col_table2:
        st.markdown("**【After】目標の構成**")
        df_after = pd.DataFrame(config_after["assets"])[["ticker", "allocation_pct"]]
        df_after.columns = ["銘柄", "配分 (%)"]
        st.table(df_after.set_index("銘柄"))
        st.info(f"合計投資額: ${config_after.get('total_investment', 0):,.2f}")


    # --- 5. チャート表示 ---
    st.markdown("---")
    st.subheader("価格指数の比較 (開始日を1.0として正規化)")
    fig_price = go.Figure()
    fig_price.add_trace(go.Scatter(x=df_results.index, y=df_results['Before_Index'], name='Before Portfolio', line=dict(color='gray')))
    fig_price.add_trace(go.Scatter(x=df_results.index, y=df_results['After_Index'], name='After Portfolio', line=dict(color='blue')))
    fig_price.update_layout(height=400, margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(fig_price, use_container_width=True)

    st.subheader("移行タイミング指標 (Z-Score)")
    fig_z = go.Figure()
    fig_z.add_trace(go.Scatter(x=df_results.index, y=df_results['Z_Score'], name='Z-Score', fill='tozeroy'))
    fig_z.add_hline(y=-z_threshold, line_dash="dash", line_color="green", annotation_text="移行推奨ライン")
    fig_z.add_hline(y=z_threshold, line_dash="dash", line_color="red")
    fig_z.update_layout(height=300, margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(fig_z, use_container_width=True)

except Exception as e:
    st.error(f"分析中にエラーが発生しました: {e}")

# --- 6. リバランス/移行シミュレーター ---
st.markdown("---")
st.header("🧮 移行実行シミュレーター")

col_s1, col_s2 = st.columns(2)
with col_s1:
    current_value = st.number_input("現在の運用総額 (USD)", value=float(config_before.get("total_investment", 10000.0)))
    
with col_s2:
    st.info("移行後の目標構成（After）に基づく必要額を表示します。")

if st.button("移行に必要な売買を算出"):
    st.write("### 移行後の目標保有額")
    calc_cols = st.columns(len(config_after["assets"]))
    for i, asset in enumerate(config_after["assets"]):
        target_amt = current_value * (asset["allocation_pct"] / 100.0)
        with calc_cols[i]:
            st.metric(asset["ticker"], f"${target_amt:,.2f}")
            st.caption(f"配分: {asset['allocation_pct']}%")